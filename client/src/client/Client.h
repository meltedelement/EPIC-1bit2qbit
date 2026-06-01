#pragma once
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "messaging/Conversation.h"

class Connection;
class CryptoProxy;
class MessageStore;
class App;

// Main orchestrator. Owns all subsystems and wires them together.
class Client {
public:
    Client(const std::string& host, uint16_t port);
    ~Client();

    // Blocking — starts the TUI event loop; returns when the user quits.
    void run();

private:
    // Outbound actions (called from UI)
    void do_register(const std::string& username, const std::string& password);
    void do_login(const std::string& username, const std::string& password);
    void do_send(const std::string& recipient, const std::string& plaintext);
    void do_delete(uint64_t message_id, bool for_both_parties);
    void do_edit(uint64_t message_id, const std::string& new_plaintext);

    // Inbound (called from the Connection read loop, on its own thread)
    void handle_ws_frame(const std::string& json_frame);
    void on_deliver_message(const nlohmann::json& frame);
    void on_key_bundle_response(const nlohmann::json& frame);

    // Network helpers
    void send_login_frame(const std::string& username, const std::string& password);
    void publish_key_bundle();
    // Sends a publish_key_bundle frame for an already-fetched bundle. Does not lock
    // or call crypto_, so it is safe to invoke while mutex_ is held (e.g. from the
    // read thread after a passive X3DH consumes a one-time pre key).
    void send_key_bundle(const nlohmann::json& bundle);

    // Crypto/session helpers. All assume mutex_ is held by the caller, since they
    // touch crypto_ (not thread-safe) and the conversation/state maps.
    void           encrypt_and_send(Conversation& conv, const std::string& plaintext);
    void           start_session_and_send(const std::string& peer, const nlohmann::json& bundle,
                                          const std::string& plaintext);
    void           send_chat_frame(const std::string& recipient, const nlohmann::json& dr_message,
                                   const nlohmann::json* x3dh_header);
    static std::string new_mid();

    std::string                    host_;
    uint16_t                       port_;
    std::string                    current_user_;

    // The DEK is never held in C++ — the crypto subprocess keeps the raw key in
    // memory after create/unlock. We only retain the encrypted_dek blob
    // ({salt, nonce, ciphertext}) needed to unlock it again.
    // TODO(persistence): this belongs in MessageStore / the local key store so it
    // survives across runs; for now it lives only for the session.
    nlohmann::json                 encrypted_dek_;

    // DEK-wrapped X3DH state (own identity key, signed pre-key, one-time pre-keys).
    // Created at registration, published over WS after login, and consumed when
    // establishing sessions. Opaque to C++. TODO(persistence): also session-only.
    nlohmann::json                 encrypted_state_;

    // Server TLS certificate fingerprint, pinned on first connect (TOFU). Empty
    // until the first handshake. TODO(persistence): MessageStore has no server-cert
    // slot yet, so this only pins for the lifetime of the process.
    std::string                    server_cert_pin_;

    // mutex_ guards crypto_ access (the subprocess is single-threaded and the
    // CryptoProxy is explicitly not thread-safe) plus the conversation/pending
    // state below, all of which are reached from both the UI thread (do_*) and the
    // Connection read thread (handle_ws_frame).
    std::mutex                          mutex_;
    std::map<std::string, Conversation> conversations_;        // peer → live session
    std::map<std::string, std::vector<std::string>> pending_sends_;  // peer → plaintext awaiting bundle

    std::unique_ptr<Connection>    connection_;
    std::unique_ptr<CryptoProxy>   crypto_;
    std::unique_ptr<MessageStore>  store_;
    std::unique_ptr<App>           app_;
};
