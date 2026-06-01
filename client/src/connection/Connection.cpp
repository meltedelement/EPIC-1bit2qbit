#include "connection/Connection.h"
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <openssl/err.h>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/sha.h>
#include <openssl/x509.h>

namespace {

// Upper bound on a single frame's payload and on a reassembled message, to stop
// an attacker-controlled length from forcing a huge allocation.
constexpr uint64_t kMaxFramePayload = 16 * 1024 * 1024;  // 16 MiB

// RFC 6455 §1.3 — the server must return base64(SHA1(client_key + GUID)).
std::string ws_compute_accept(const std::string& client_key) {
    static constexpr char kGuid[] = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    std::string input = client_key + kGuid;

    unsigned char digest[SHA_DIGEST_LENGTH];
    SHA1(reinterpret_cast<const unsigned char*>(input.data()), input.size(), digest);

    // base64 of 20 bytes: ceil(20/3)*4 = 28 chars + null terminator
    unsigned char out[29];
    EVP_EncodeBlock(out, digest, SHA_DIGEST_LENGTH);
    return std::string{reinterpret_cast<char*>(out), 28};
}

// Extract a header value by case-insensitive field name, trimming surrounding
// whitespace. Returns "" if the header is absent.
std::string ws_header_value(const std::string& response, const std::string& name) {
    std::string lower = response;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });

    size_t key = lower.find(name + ":");
    if (key == std::string::npos) return "";

    size_t start = key + name.size() + 1;
    size_t end   = response.find("\r\n", start);
    std::string value = response.substr(start, end - start);

    auto not_space = [](unsigned char c) { return !std::isspace(c); };
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), not_space));
    value.erase(std::find_if(value.rbegin(), value.rend(), not_space).base(), value.end());
    return value;
}

}  // namespace

// ─── Lifecycle ───────────────────────────────────────────────────────────────

Connection::Connection(const std::string& host, uint16_t port)
    : host_{host}, port_{port}, tcp_sock_{io_ctx_} {}

Connection::~Connection() { disconnect(); }

void Connection::connect(const std::string& pinned_fp) {
    tcp_connect();
    tls_handshake(pinned_fp);
    ws_handshake();
    connected_ = true;
    running_   = true;
    read_thread_ = std::thread{[this] { read_loop(); }};
}

void Connection::disconnect() {
    running_   = false;
    connected_ = false;

    // Close the TCP socket first: read_thread_ may be blocked in SSL_read, and the
    // SSL object is not safe for concurrent use. Closing the fd makes that SSL_read
    // fail so read_loop exits; we then join before touching ssl_. Freeing the SSL
    // before the reader has stopped would be a use-after-free / data race.
    if (tcp_sock_.is_open())
        tcp_sock_.close();

    if (read_thread_.joinable())
        read_thread_.join();

    // Now the reader is gone — safe to tear down the SSL object. The socket is
    // already closed, so this is an abrupt close (no close_notify); acceptable for
    // a client-initiated disconnect.
    if (ssl_) {
        SSL_free(ssl_);
        ssl_ = nullptr;
    }
}

bool        Connection::is_connected()    const { return connected_; }
std::string Connection::cert_fingerprint() const { return server_cert_fp_; }

void Connection::on_message(MessageCallback cb) { on_message_cb_ = std::move(cb); }
void Connection::on_disconnect(DisconnectCallback cb) { on_disconnect_cb_ = std::move(cb); }

// ─── TCP ─────────────────────────────────────────────────────────────────────

void Connection::tcp_connect() {
    boost::asio::ip::tcp::resolver resolver{io_ctx_};
    auto endpoints = resolver.resolve(host_, std::to_string(port_));
    boost::asio::connect(tcp_sock_, endpoints);
}

// ─── TLS ─────────────────────────────────────────────────────────────────────

void Connection::tls_handshake(const std::string& pinned_fp) {
    // Free any SSL from a previous (failed) attempt so connect() is retryable.
    if (ssl_) { SSL_free(ssl_); ssl_ = nullptr; }

    ssl_ = SSL_new(tls_ctx_.ctx());
    if (!ssl_) throw std::runtime_error{"SSL_new failed"};

    // SNI — tells the server which hostname we want so it picks the right cert
    if (SSL_set_tlsext_host_name(ssl_, host_.c_str()) != 1)
        throw std::runtime_error{"SSL_set_tlsext_host_name failed"};

    // Hostname verification — OpenSSL checks CN/SAN during SSL_connect
    if (SSL_set1_host(ssl_, host_.c_str()) != 1)
        throw std::runtime_error{"SSL_set1_host failed"};
    SSL_set_verify(ssl_, SSL_VERIFY_PEER, nullptr);

    SSL_set_fd(ssl_, static_cast<int>(tcp_sock_.native_handle()));

    if (SSL_connect(ssl_) != 1) {
        std::string msg = "SSL_connect failed";

        // A cert-verification failure leaves the ERR queue empty but records the
        // reason in the verify result — surface it explicitly.
        long verify = SSL_get_verify_result(ssl_);
        if (verify != X509_V_OK)
            msg += std::string{": "} + X509_verify_cert_error_string(verify);

        // Drain the whole OpenSSL error queue, not just the first entry.
        unsigned long err;
        while ((err = ERR_get_error()) != 0)
            msg += std::string{"; "} + ERR_error_string(err, nullptr);

        throw std::runtime_error{msg};
    }

    server_cert_fp_ = tls_ctx_.verify_and_pin(ssl_, host_, pinned_fp);
}

// ─── Raw SSL I/O ─────────────────────────────────────────────────────────────

std::string Connection::ssl_read_exact(size_t n) {
    std::string buf(n, '\0');
    size_t total = 0;
    while (total < n) {
        int got = SSL_read(ssl_, buf.data() + total, static_cast<int>(n - total));
        if (got <= 0) {
            int err = SSL_get_error(ssl_, got);
            throw std::runtime_error{"SSL_read failed: error code " + std::to_string(err)};
        }
        total += static_cast<size_t>(got);
    }
    return buf;
}

void Connection::ssl_write_all(const std::string& data) {
    size_t total = 0;
    while (total < data.size()) {
        int written = SSL_write(ssl_, data.data() + total,
                                static_cast<int>(data.size() - total));
        if (written <= 0) {
            int err = SSL_get_error(ssl_, written);
            throw std::runtime_error{"SSL_write failed: error code " + std::to_string(err)};
        }
        total += static_cast<size_t>(written);
    }
}

// ─── WebSocket handshake ─────────────────────────────────────────────────────

std::string Connection::ws_key_base64() {
    unsigned char buf[16];
    if (RAND_bytes(buf, sizeof(buf)) != 1)
        throw std::runtime_error{"RAND_bytes failed generating WS key"};
    // EVP_EncodeBlock output: ceil(16/3)*4 = 24 chars + null terminator
    unsigned char out[25];
    EVP_EncodeBlock(out, buf, sizeof(buf));
    return std::string{reinterpret_cast<char*>(out), 24};
}

void Connection::ws_handshake() {
    std::string key = ws_key_base64();
    std::string request =
        "GET / HTTP/1.1\r\n"
        "Host: "                  + host_               + "\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: "     + key                 + "\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n";

    ssl_write_all(request);

    // Read the server response until we see the end-of-headers marker
    std::string response;
    while (response.size() < 4
           || response.substr(response.size() - 4) != "\r\n\r\n") {
        char c;
        int got = SSL_read(ssl_, &c, 1);
        if (got <= 0) throw std::runtime_error{"ws_handshake: connection closed during upgrade"};
        response += c;
        if (response.size() > 8192)
            throw std::runtime_error{"ws_handshake: response header too large"};
    }

    std::string status_line = response.substr(0, response.find("\r\n"));
    if (status_line.rfind("HTTP/1.1 101", 0) != 0)
        throw std::runtime_error{"ws_handshake: expected 101 Switching Protocols, got: "
                                 + status_line};

    if (ws_header_value(response, "sec-websocket-accept") != ws_compute_accept(key))
        throw std::runtime_error{"ws_handshake: invalid Sec-WebSocket-Accept"};
}

// ─── WebSocket framing ───────────────────────────────────────────────────────

// RFC 6455 §5.2 — client frames MUST be masked.
std::string Connection::ws_encode_frame(uint8_t opcode, const std::string& payload) {
    std::string frame;
    frame.reserve(2 + 8 + 4 + payload.size());

    // Byte 0: FIN=1, RSV=0, opcode
    frame += static_cast<char>(0x80 | (opcode & 0x0f));

    // Byte 1+: MASK=1, payload length
    size_t len = payload.size();
    if (len < 126) {
        frame += static_cast<char>(0x80 | len);
    } else if (len < 65536) {
        frame += static_cast<char>(0x80 | 126);
        frame += static_cast<char>((len >> 8) & 0xff);
        frame += static_cast<char>(len & 0xff);
    } else {
        frame += static_cast<char>(0x80 | 127);
        for (int i = 7; i >= 0; --i)
            frame += static_cast<char>((len >> (8 * i)) & 0xff);
    }

    // 4-byte masking key
    unsigned char mask[4];
    if (RAND_bytes(mask, sizeof(mask)) != 1)
        throw std::runtime_error{"RAND_bytes failed generating WS mask"};
    frame.append(reinterpret_cast<char*>(mask), 4);

    // Masked payload
    for (size_t i = 0; i < payload.size(); ++i)
        frame += static_cast<char>(static_cast<unsigned char>(payload[i]) ^ mask[i % 4]);

    return frame;
}

// Encode + send under the write mutex (safe to call from main thread while
// read_loop runs in read_thread_).
void Connection::ws_send_frame(uint8_t opcode, const std::string& payload) {
    std::lock_guard<std::mutex> lock{write_mutex_};
    ssl_write_all(ws_encode_frame(opcode, payload));
}

void Connection::send_text(const std::string& payload) {
    if (!connected_) throw std::runtime_error{"not connected"};
    ws_send_frame(0x01, payload);  // opcode 0x1 = text frame
}

// RFC 6455 §5.2 — server frames MUST NOT be masked.
// Handles ping (sends pong), pong, and close internally; reassembles fragmented
// messages (FIN bit + continuation frames) and returns the complete payload.
std::string Connection::ws_decode_frame() {
    std::string message;
    bool        assembling = false;
    while (true) {
        std::string hdr = ssl_read_exact(2);
        bool     fin         = (static_cast<uint8_t>(hdr[0]) & 0x80) != 0;
        uint8_t  opcode      = static_cast<uint8_t>(hdr[0]) & 0x0f;
        bool     server_mask = (static_cast<uint8_t>(hdr[1]) & 0x80) != 0;
        uint64_t payload_len = static_cast<uint8_t>(hdr[1]) & 0x7f;

        if (payload_len == 126) {
            std::string ext = ssl_read_exact(2);
            payload_len = (static_cast<uint8_t>(ext[0]) << 8)
                        |  static_cast<uint8_t>(ext[1]);
        } else if (payload_len == 127) {
            std::string ext = ssl_read_exact(8);
            payload_len = 0;
            for (int i = 0; i < 8; ++i)
                payload_len = (payload_len << 8) | static_cast<uint8_t>(ext[i]);
        }

        if (payload_len > kMaxFramePayload)
            throw std::runtime_error{"ws: frame payload exceeds limit"};

        // Server masking is forbidden by the spec; skip mask bytes if present anyway
        std::string mask_bytes;
        if (server_mask) mask_bytes = ssl_read_exact(4);

        std::string payload = ssl_read_exact(static_cast<size_t>(payload_len));
        if (server_mask) {
            for (size_t i = 0; i < payload.size(); ++i)
                payload[i] ^= mask_bytes[i % 4];
        }

        // Control frames are never fragmented and may interleave data fragments.
        if (opcode == 0x08) throw std::runtime_error{"ws: server sent close frame"};
        if (opcode == 0x09) { ws_send_frame(0x0a, payload); continue; }  // ping → pong
        if (opcode == 0x0a) continue;                                    // pong → ignore

        // Data (0x1 text / 0x2 binary) and continuation (0x0) frames.
        if (opcode == 0x01 || opcode == 0x02) {
            if (assembling)
                throw std::runtime_error{"ws: new data frame during fragmented message"};
            if (fin) return payload;              // unfragmented — fast path
            message    = std::move(payload);
            assembling = true;
        } else if (opcode == 0x00) {
            if (!assembling)
                throw std::runtime_error{"ws: continuation frame with no message in progress"};
            if (message.size() + payload.size() > kMaxFramePayload)
                throw std::runtime_error{"ws: reassembled message exceeds limit"};
            message += payload;
            if (fin) return message;
        } else {
            throw std::runtime_error{"ws: unknown opcode"};
        }
    }
}

// ─── Read loop ───────────────────────────────────────────────────────────────

// Threading note: read_loop() calls SSL_read on read_thread_ while send_text()
// calls SSL_write on the main thread. OpenSSL permits one concurrent reader and
// one concurrent writer on the same SSL* in steady state. The one exception is a
// read that must internally write: TLS 1.2 renegotiation (impossible here — we
// pin to TLS 1.3 in TlsContext) and a TLS 1.3 KeyUpdate from the server, which
// can race the main-thread SSL_write. Only the authenticated server can trigger
// this, the window is microseconds, and the typical outcome is a dropped
// connection. The full fix (single-threaded non-blocking I/O) is tracked
// separately; until then this constraint is accepted deliberately.
void Connection::read_loop() {
    while (running_) {
        try {
            std::string msg = ws_decode_frame();
            if (on_message_cb_) on_message_cb_(std::move(msg));
        } catch (const std::exception& e) {
            // Connection closed or error — exit loop and mark disconnected.
            // exchange() distinguishes an unexpected drop (running_ was still
            // true) from a caller-initiated disconnect() (already set false);
            // only the former notifies. The callback runs on this read thread.
            connected_ = false;
            if (running_.exchange(false) && on_disconnect_cb_)
                on_disconnect_cb_(e.what());
        }
    }
}
