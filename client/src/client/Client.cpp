#include "client/Client.h"

#include <array>
#include <chrono>
#include <exception>
#include <stdexcept>
#include <utility>

#include <openssl/err.h>
#include <openssl/x509.h>

#include <openssl/evp.h>
#include <openssl/rand.h>

#include "connection/Connection.h"
#include "connection/TlsContext.h"
#include "crypto/CryptoProxy.h"
#include "messaging/Message.h"
#include "messaging/MessageStore.h"
#include "ui/App.h"
#include "log.h"

namespace {

// ── One-shot HTTPS POST ───────────────────────────────────────────────────────
// Used for registration (a plain HTTP exchange, not a WebSocket session).

struct HttpResponse { int status; std::string body; };

HttpResponse https_post(const std::string& host, uint16_t port,
                        const std::string& path, const std::string& json_body) {
    boost::asio::io_context io;
    boost::asio::ip::tcp::socket sock{io};
    boost::asio::ip::tcp::resolver resolver{io};
    boost::asio::connect(sock, resolver.resolve(host, std::to_string(port)));

    TlsContext tls_ctx;
    SSL* ssl = SSL_new(tls_ctx.ctx());
    if (!ssl) throw std::runtime_error{"SSL_new failed"};
    struct SslGuard { SSL* s; ~SslGuard() { SSL_free(s); } } guard{ssl};

    SSL_set_tlsext_host_name(ssl, host.c_str());
    SSL_set1_host(ssl, host.c_str());
    SSL_set_verify(ssl, SSL_VERIFY_PEER, nullptr);
    SSL_set_fd(ssl, static_cast<int>(sock.native_handle()));

    if (SSL_connect(ssl) != 1) {
        std::string msg = "SSL_connect failed";
        long verify = SSL_get_verify_result(ssl);
        if (verify != X509_V_OK)
            msg += std::string{": "} + X509_verify_cert_error_string(verify);
        unsigned long err;
        while ((err = ERR_get_error()) != 0)
            msg += std::string{"; "} + ERR_error_string(err, nullptr);
        throw std::runtime_error{msg};
    }

    const std::string request =
        "POST " + path + " HTTP/1.1\r\n"
        "Host: " + host + "\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + std::to_string(json_body.size()) + "\r\n"
        "Connection: close\r\n"
        "\r\n" + json_body;

    size_t total = 0;
    while (total < request.size()) {
        int n = SSL_write(ssl, request.data() + total,
                          static_cast<int>(request.size() - total));
        if (n <= 0) throw std::runtime_error{"SSL_write failed during registration"};
        total += static_cast<size_t>(n);
    }

    std::string response;
    char buf[4096];
    while (true) {
        int n = SSL_read(ssl, buf, static_cast<int>(sizeof(buf)));
        if (n > 0) { response.append(buf, static_cast<size_t>(n)); continue; }
        int err = SSL_get_error(ssl, n);
        if (err == SSL_ERROR_ZERO_RETURN || err == SSL_ERROR_SYSCALL) break;
        throw std::runtime_error{"SSL_read failed during registration"};
    }

    // Parse "HTTP/1.1 NNN ..."
    const size_t sp1 = response.find(' ');
    const size_t sp2 = sp1 != std::string::npos ? response.find(' ', sp1 + 1) : std::string::npos;
    if (sp1 == std::string::npos || sp2 == std::string::npos)
        throw std::runtime_error{"malformed HTTP response from server"};
    const int status = std::stoi(response.substr(sp1 + 1, sp2 - sp1 - 1));

    const size_t body_start = response.find("\r\n\r\n");
    std::string body = (body_start != std::string::npos) ? response.substr(body_start + 4) : "";

    return {status, std::move(body)};
}

// base64 over OpenSSL's EVP codec — the same primitive Connection uses for the
// WebSocket key. Crypto material crosses the IPC boundary as base64 strings; the
// plaintext body we encrypt is wrapped the same way.
std::string b64_encode(const std::string& in) {
    if (in.empty()) return "";
    std::string out(4 * ((in.size() + 2) / 3), '\0');
    const int n = EVP_EncodeBlock(reinterpret_cast<unsigned char*>(out.data()),
                                  reinterpret_cast<const unsigned char*>(in.data()),
                                  static_cast<int>(in.size()));
    out.resize(static_cast<size_t>(n));
    return out;
}

std::string b64_decode(const std::string& in) {
    if (in.empty()) return "";
    std::string out(3 * (in.size() / 4), '\0');
    const int n = EVP_DecodeBlock(reinterpret_cast<unsigned char*>(out.data()),
                                  reinterpret_cast<const unsigned char*>(in.data()),
                                  static_cast<int>(in.size()));
    if (n < 0) throw std::runtime_error{"base64 decode failed"};
    // EVP_DecodeBlock always emits a multiple of 3 bytes; drop what the '=' padding
    // in the input stood for so the length matches the original plaintext.
    size_t pad = 0;
    if (in.size() >= 1 && in[in.size() - 1] == '=') ++pad;
    if (in.size() >= 2 && in[in.size() - 2] == '=') ++pad;
    out.resize(static_cast<size_t>(n) - pad);
    return out;
}

// The ratchet encrypts a serialized MessageContent, not the raw text — keeping the
// envelope ready for edit/delete/reply types later. For now only the Standard body
// travels; the field set matches messaging/Message.h.
std::string content_to_message(const std::string& plaintext) {
    const nlohmann::json content = {
        {"type", static_cast<int>(MessageType::Standard)},
        {"body", plaintext},
    };
    return b64_encode(content.dump());
}

std::string message_to_body(const std::string& plaintext_b64) {
    const nlohmann::json content = nlohmann::json::parse(b64_decode(plaintext_b64));
    return content.value("body", std::string{});
}

}  // namespace


Client::Client(const std::string& host, uint16_t port)
    : host_{host}, port_{port} {}

Client::~Client() = default;

void Client::run() {
    epic_log("Client::run start");
    // Build the crypto subprocess bridge, local store, and the UI.
    crypto_ = std::make_unique<CryptoProxy>();
    store_  = std::make_unique<MessageStore>("epic-client.db");

    AppCallbacks cbs;
    cbs.on_register = [this](std::string u, std::string p, std::string pin) { do_register(u, p, pin); };
    cbs.on_login    = [this](std::string u, std::string p, std::string pin) { do_login(u, p, pin); };
    cbs.on_send     = [this](std::string r, std::string t) { do_send(r, t); };
    cbs.on_delete   = [this](uint64_t id, bool both) { do_delete(id, both); };
    cbs.on_edit     = [this](uint64_t id, std::string t) { do_edit(id, t); };
    app_ = std::make_unique<App>(std::move(cbs));

    // Spawn client/subprocess_handler.py with its stdin/stdout piped to us. The
    // script path is resolved relative to the subprocess's working directory, so
    // epic-client must be launched from the client/ directory (or the default
    // path adjusted) for the crypto_functions package to import.
    crypto_->start();

    app_->run();  // blocking TUI loop; returns when the user quits

    if (connection_) connection_->disconnect();
    crypto_->stop();
}

// ── Outbound actions (called from UI) ────────────────────────────────────────────

void Client::do_register(const std::string& username, const std::string& auth_password,
                         const std::string& key_pin) {
    if (auth_password == key_pin) {
        app_->push_status("Registration failed: authentication password and Key PIN must be different.");
        return;
    }
    try {
        std::lock_guard<std::mutex> lk(mutex_);

        encrypted_dek_   = crypto_->create_dek(key_pin, username).at("encrypted_dek");
        encrypted_state_ = crypto_->create_state().at("encrypted_state");
        current_user_    = username;
        store_->save_dek(username, encrypted_dek_.dump());
        store_->save_encrypted_state(username, encrypted_state_.dump());

        const nlohmann::json reg_body = {{"username", username}, {"password", auth_password}};
        const auto resp = https_post(host_, port_, "/backend/register", reg_body.dump());
        if (resp.status == 409)
            throw std::runtime_error{"username already taken"};
        if (resp.status != 201)
            throw std::runtime_error{"server returned HTTP " + std::to_string(resp.status)};

        app_->push_status("Registered '" + username + "' — log in to open a session.");
    } catch (const std::exception& e) {
        app_->push_status(std::string("Registration failed: ") + e.what());
    }
}

void Client::do_login(const std::string& username, const std::string& auth_password,
                      const std::string& key_pin) {
    epic_log("do_login: user=" + username);
    try {
        // Load the persisted DEK blob if we don't have it in memory already.
        if (encrypted_dek_.is_null()) {
            auto stored = store_->load_dek(username);
            if (!stored) {
                app_->push_status("No local key material for '" + username +
                                  "'. Register on this device first.");
                return;
            }
            encrypted_dek_ = nlohmann::json::parse(*stored);
        }
        {
            std::lock_guard<std::mutex> lk(mutex_);
            crypto_->unlock_dek(key_pin, username, encrypted_dek_);
        }

        // Load persisted X3DH state (needed to establish new sessions after restart).
        if (encrypted_state_.is_null()) {
            if (auto stored = store_->load_encrypted_state(username))
                encrypted_state_ = nlohmann::json::parse(*stored);
        }

        // Restore conversation history — populate both the Client's crypto map
        // (needed for ratchet state on inbound messages) and the UI.
        {
            std::vector<Conversation> convs;
            for (const auto& peer : store_->list_peers()) {
                if (auto conv = store_->load_conversation(peer)) {
                    conversations_.insert_or_assign(peer, *conv);
                    convs.push_back(std::move(*conv));
                }
            }
            if (!convs.empty())
                app_->set_conversations(std::move(convs));
        }

        current_user_ = username;

        // Bring up the network. Callbacks must be set BEFORE connect(): the read
        // thread starts inside connect() and may fire on_message immediately.
        connection_ = std::make_unique<Connection>(host_, port_, port_ == 443);
        connection_->on_message([this](std::string frame) { handle_ws_frame(frame); });
        connection_->on_disconnect(
            [this](std::string reason) { app_->push_status("Disconnected: " + reason); });

        connection_->connect(server_cert_pin_);
        if (server_cert_pin_.empty()) server_cert_pin_ = connection_->cert_fingerprint();

        // First WS frame is the login (no tokens — the connection is the session).
        send_login_frame(username, auth_password);
        publish_key_bundle();

        app_->advance_to_chat(username);
        app_->push_status("Logged in as '" + username + "' — session open.");
    } catch (const std::exception& e) {
        epic_log("do_login: exception: " + std::string(e.what()));
        app_->push_status(std::string("Login failed: ") + e.what());
        connection_.reset();
    }
}

void Client::do_send(const std::string& recipient, const std::string& plaintext) {
    epic_log("do_send: to=" + recipient + " text=" + plaintext);
    if (!connection_ || !connection_->is_connected()) {
        epic_log("do_send: not connected");
        app_->push_status("Not connected — log in first.");
        return;
    }
    try {
        std::lock_guard<std::mutex> lk(mutex_);
        auto it = conversations_.find(recipient);
        if (it != conversations_.end() && !it->second.ratchet_state().empty()) {
            epic_log("do_send: established session, calling encrypt_and_send");
            encrypt_and_send(it->second, plaintext);
        } else {
            epic_log("do_send: no session yet, requesting key bundle for " + recipient);
            pending_sends_[recipient].push_back(plaintext);
            const nlohmann::json frame = {
                {"type", "request_key_bundle"},
                {"target_username", recipient},
            };
            connection_->send_text(frame.dump());
        }
    } catch (const std::exception& e) {
        epic_log("do_send: exception: " + std::string(e.what()));
        app_->push_status(std::string("Send failed: ") + e.what());
    }
}

void Client::do_delete(uint64_t /*message_id*/, bool /*for_both_parties*/) {}
void Client::do_edit(uint64_t /*message_id*/, const std::string& /*new_plaintext*/) {}

// ── Network helpers ──────────────────────────────────────────────────────────────

void Client::send_login_frame(const std::string& username, const std::string& password) {
    const nlohmann::json frame = {{"username", username}, {"password", password}};
    connection_->send_text(frame.dump());
}

void Client::publish_key_bundle() {
    nlohmann::json bundle;
    {
        std::lock_guard<std::mutex> lk(mutex_);
        if (encrypted_state_.is_null()) return;  // registered on another device
        bundle = crypto_->get_bundle(encrypted_state_);
    }
    send_key_bundle(bundle);
}

void Client::send_key_bundle(const nlohmann::json& bundle) {
    const nlohmann::json& otpks = bundle.at("pre_keys");
    if (otpks.empty()) return;  // server requires at least one one-time pre-key

    const nlohmann::json frame = {
        {"type", "publish_key_bundle"},
        {"identity_key", bundle.at("identity_key")},
        {"signed_pre_key", bundle.at("signed_pre_key")},
        {"signed_pre_key_sig", bundle.at("signed_pre_key_sig")},
        {"one_time_pre_keys", otpks},
    };
    connection_->send_text(frame.dump());
}

// ── Inbound (Connection read thread) ─────────────────────────────────────────────

void Client::handle_ws_frame(const std::string& json_frame) {
    epic_log("handle_ws_frame: raw=" + json_frame.substr(0, 120));
    nlohmann::json frame;
    try {
        frame = nlohmann::json::parse(json_frame);
    } catch (const std::exception&) {
        epic_log("handle_ws_frame: parse failed");
        app_->push_status("Received malformed frame from server.");
        return;
    }

    const std::string type = frame.value("type", std::string{});
    epic_log("handle_ws_frame: type=" + type);
    if (type == "deliver_message") {
        on_deliver_message(frame);
    } else if (type == "key_bundle_response") {
        on_key_bundle_response(frame);
    } else if (type == "error") {
        app_->push_status("Server error [" + frame.value("code", std::string{}) + "]: " +
                          frame.value("detail", std::string{}));
    } else {
        app_->push_status("Unknown frame type from server: " + type);
    }
}

void Client::on_deliver_message(const nlohmann::json& frame) {
    const std::string sender = frame.value("sender", std::string{});
    epic_log("on_deliver_message: from=" + sender);
    try {
        const nlohmann::json env = nlohmann::json::parse(frame.at("ciphertext").get<std::string>());
        const nlohmann::json& dr = env.at("dr");
        const bool has_x3dh      = env.contains("x3dh") && !env.at("x3dh").is_null();

        std::lock_guard<std::mutex> lk(mutex_);
        Conversation& conv =
            conversations_.try_emplace(sender, Conversation{sender}).first->second;

        std::string plaintext_b64;
        if (conv.ratchet_state().empty() && has_x3dh) {
            // First message from this peer — passive X3DH derives the shared secret
            // and our ratchet private key from the embedded X3DH header.
            const nlohmann::json& x3dh = env.at("x3dh");
            const std::string peer_ik  = x3dh.value("identity_key", std::string{});
            if (!conv.pinned_ik_pub().empty() && conv.pinned_ik_pub() != peer_ik) {
                app_->push_status("WARNING: identity key for '" + sender +
                                  "' changed — possible impersonation. Message dropped.");
                return;
            }

            const nlohmann::json ss = crypto_->get_shared_secret_passive(encrypted_state_, x3dh);
            encrypted_state_ = ss.at("encrypted_state");
            // The passive agreement consumed one of our one-time pre keys; re-publish
            // the refreshed bundle so the server drops the spent key and sees the refill.
            if (ss.contains("bundle")) send_key_bundle(ss.at("bundle"));
            const nlohmann::json dec = crypto_->decrypt_initial_message(
                ss.at("shared_secret").get<std::string>(),
                ss.at("own_ratchet_priv").get<std::string>(), dr,
                ss.at("associated_data").get<std::string>());

            conv.set_associated_data(ss.at("associated_data").get<std::string>());
            conv.set_ratchet_state(dec.at("ratchet_state").dump());
            conv.set_pinned_ik_pub(peer_ik);
            store_->pin_identity_key(sender, peer_ik);
            store_->save_associated_data(sender, conv.associated_data());
            store_->save_ratchet_state(sender, conv.ratchet_state());
            store_->save_encrypted_state(current_user_, encrypted_state_.dump());
            plaintext_b64 = dec.at("plaintext").get<std::string>();
        } else if (!conv.ratchet_state().empty()) {
            // Established session — decrypt with the stored ratchet state.
            nlohmann::json rstate    = nlohmann::json::parse(conv.ratchet_state());
            const nlohmann::json dec = crypto_->decrypt_message(rstate, dr, conv.associated_data());
            conv.set_ratchet_state(dec.at("ratchet_state").dump());
            store_->save_ratchet_state(sender, conv.ratchet_state());
            plaintext_b64 = dec.at("plaintext").get<std::string>();
        } else {
            app_->push_status("Dropped message from '" + sender +
                              "': no session and no X3DH header.");
            return;
        }

        const std::string body = message_to_body(plaintext_b64);
        epic_log("on_deliver_message: decrypted body=" + body);
        Message msg;
        msg.peer      = sender;
        msg.recipient = current_user_;
        msg.body      = body;
        conv.add_message(msg);
        store_->save_message(msg);
        epic_log("on_deliver_message: calling push_message");
        app_->push_message(sender, body);
    } catch (const std::exception& e) {
        app_->push_status("Failed to decrypt message from '" + sender + "': " + e.what());
    }
}

void Client::on_key_bundle_response(const nlohmann::json& frame) {
    const std::string peer = frame.value("username", std::string{});
    epic_log("on_key_bundle_response: peer=" + peer);
    std::lock_guard<std::mutex> lk(mutex_);

    auto pending = pending_sends_.find(peer);
    if (pending == pending_sends_.end()) {
        epic_log("on_key_bundle_response: no pending sends for " + peer);
        return;
    }
    std::vector<std::string> texts = std::move(pending->second);
    pending_sends_.erase(pending);

    try {
        for (const std::string& text : texts) {
            auto it = conversations_.find(peer);
            if (it != conversations_.end() && !it->second.ratchet_state().empty()) {
                // The first queued message established the session; the rest ride
                // the now-live ratchet.
                encrypt_and_send(it->second, text);
            } else {
                start_session_and_send(peer, frame, text);
            }
        }
    } catch (const std::exception& e) {
        app_->push_status("Failed to start session with '" + peer + "': " + e.what());
    }
}

// ── Crypto/session helpers (mutex_ held by caller) ───────────────────────────────

void Client::encrypt_and_send(Conversation& conv, const std::string& plaintext) {
    epic_log("encrypt_and_send: peer=" + conv.peer());
    nlohmann::json rstate    = nlohmann::json::parse(conv.ratchet_state());
    const nlohmann::json enc = crypto_->encrypt_message(rstate, content_to_message(plaintext),
                                                        conv.associated_data());
    conv.set_ratchet_state(enc.at("ratchet_state").dump());
    store_->save_ratchet_state(conv.peer(), conv.ratchet_state());
    send_chat_frame(conv.peer(), enc.at("encrypted_message"), nullptr);
    epic_log("encrypt_and_send: frame sent, pushing to UI");
    app_->push_sent_message(conv.peer(), plaintext);
}

void Client::start_session_and_send(const std::string& peer, const nlohmann::json& bundle,
                                    const std::string& plaintext) {
    const std::string peer_ik = bundle.value("identity_key", std::string{});

    // Adapt the server's key_bundle_response (a single one_time_pre_key, possibly
    // null) to the bob_bundle shape the subprocess's X3DH expects (a pre_keys list).
    nlohmann::json otpks = nlohmann::json::array();
    if (bundle.contains("one_time_pre_key") && !bundle.at("one_time_pre_key").is_null())
        otpks.push_back(bundle.at("one_time_pre_key"));
    const nlohmann::json bob_bundle = {
        {"identity_key", peer_ik},
        {"signed_pre_key", bundle.at("signed_pre_key")},
        {"signed_pre_key_sig", bundle.at("signed_pre_key_sig")},
        {"pre_keys", otpks},
    };

    const nlohmann::json ss = crypto_->get_shared_secret_active(encrypted_state_, bob_bundle);
    encrypted_state_ = ss.at("encrypted_state");
    const nlohmann::json enc = crypto_->encrypt_initial_message(
        ss.at("shared_secret").get<std::string>(),
        ss.at("bob_initial_ratchet_pub").get<std::string>(), content_to_message(plaintext),
        ss.at("associated_data").get<std::string>());

    Conversation& conv = conversations_.try_emplace(peer, Conversation{peer}).first->second;
    conv.set_associated_data(ss.at("associated_data").get<std::string>());
    conv.set_ratchet_state(enc.at("ratchet_state").dump());
    conv.set_pinned_ik_pub(peer_ik);
    store_->pin_identity_key(peer, peer_ik);
    store_->save_associated_data(peer, conv.associated_data());
    store_->save_ratchet_state(peer, conv.ratchet_state());
    store_->save_encrypted_state(current_user_, encrypted_state_.dump());

    const nlohmann::json header = ss.at("header");
    send_chat_frame(peer, enc.at("encrypted_message"), &header);
    app_->push_sent_message(peer, plaintext);
}

void Client::send_chat_frame(const std::string& recipient, const nlohmann::json& dr_message,
                             const nlohmann::json* x3dh_header) {
    nlohmann::json env;
    env["dr"]   = dr_message;
    env["x3dh"] = x3dh_header ? *x3dh_header : nlohmann::json(nullptr);

    const nlohmann::json frame = {
        {"type", "send_message"},
        {"recipient", recipient},
        {"ciphertext", env.dump()},
        {"mid", new_mid(recipient)},
    };
    connection_->send_text(frame.dump());
}

std::string Client::new_mid(const std::string& recipient) const {
    const auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    return current_user_ + ":" + recipient + ":" + std::to_string(now_ms);
}
