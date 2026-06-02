#include "client/Client.h"

#include <exception>
#include <utility>

#include "connection/Connection.h"
#include "crypto/CryptoProxy.h"
#include "messaging/MessageStore.h"
#include "ui/App.h"

static constexpr const char* kDbPath = "epic.db";

Client::Client(const std::string& host, uint16_t port)
    : host_{host}, port_{port} {}

Client::~Client() = default;

void Client::run() {
    // Build the crypto subprocess bridge and the UI. The Connection (network) is
    // wired in a later step; this stage brings up the crypto link only.
    crypto_ = std::make_unique<CryptoProxy>();
    store_  = std::make_unique<MessageStore>(kDbPath);

    AppCallbacks cbs;
    cbs.on_register = [this](std::string u, std::string p) { do_register(u, p); };
    cbs.on_login    = [this](std::string u, std::string p) { do_login(u, p); };
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

    crypto_->stop();
}

// ── Outbound actions (called from UI) ────────────────────────────────────────────

void Client::do_register(const std::string& username, const std::string& password) {
    try {
        const nlohmann::json result = crypto_->create_dek(password, username);
        encrypted_dek_ = result.at("encrypted_dek");
        current_user_  = username;
        store_->save_dek(username, encrypted_dek_.dump());
        // TODO(network): create_state() + publish key bundle via POST /register.
        app_->push_status("Registered '" + username + "' — DEK created and unlocked.");
    } catch (const std::exception& e) {
        app_->push_status(std::string("Registration failed: ") + e.what());
    }
}

void Client::do_login(const std::string& username, const std::string& password) {
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
        crypto_->unlock_dek(password, username, encrypted_dek_);
        current_user_ = username;
        app_->advance_to_chat(username);
        // TODO(network): open the WSS connection and send the login frame.
        app_->push_status("Logged in as '" + username + "' — DEK unlocked.");
    } catch (const std::exception& e) {
        app_->push_status(std::string("Login failed: ") + e.what());
    }
}

void Client::do_send(const std::string& /*recipient*/, const std::string& /*plaintext*/) {}
void Client::do_delete(uint64_t /*message_id*/, bool /*for_both_parties*/) {}
void Client::do_edit(uint64_t /*message_id*/, const std::string& /*new_plaintext*/) {}

// ── Inbound (called from Connection read loop) ───────────────────────────────────

void Client::handle_ws_frame(const std::string& /*json_frame*/) {}
