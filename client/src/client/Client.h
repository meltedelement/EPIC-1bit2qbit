#pragma once
#include <atomic>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

#include "messaging/Conversation.h"
#include "messaging/Message.h"


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
    void do_register(const std::string& username, const std::string& auth_password,
                     const std::string& key_pin);
    void do_login(const std::string& username, const std::string& auth_password,
                  const std::string& key_pin);
    void do_send(const std::string& recipient, const std::string& plaintext);
    void do_forward(const std::string& recipient, const std::string& body);
    void do_delete(uint64_t message_id, bool for_both_parties);
    void do_edit(uint64_t message_id, const std::string& new_plaintext);
    void do_logout();

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
    void           encrypt_and_send_typed(Conversation& conv, const std::string& plaintext,
                                          MessageType type);
    // Encrypt and send a pre-serialised content blob — no DB/UI side-effects.
    void           send_ratchet_control(Conversation& conv, const std::string& content_b64);
    void           start_session_and_send(const std::string& peer, const nlohmann::json& bundle,
                                          const std::string& plaintext);
    void           send_chat_frame(const std::string& recipient, const nlohmann::json& dr_message,
                                   const nlohmann::json* x3dh_header, const std::string& mid);
    std::string new_mid(const std::string& recipient) const;

    // Encrypt/decrypt a string for local DB storage using the DEK.
    // Must be called with mutex_ held (uses crypto_).
    // decrypt_from_storage gracefully returns the input unchanged if it is not
    // an encrypted blob, so existing plaintext rows survive a DB migration.
    std::string storage_encrypt(const std::string& plaintext);
    std::string storage_decrypt(const std::string& data);

    std::string                    host_;
    uint16_t                       port_;
    std::string                    current_user_;
    int                            pin_fail_count_{0};

    std::atomic<bool>              quit_{false};

    // The DEK is never held in C++ — the crypto subprocess keeps the raw key in
    // memory after create/unlock. We only retain the encrypted_dek blob
    // ({salt, nonce, ciphertext}) needed to unlock it again; it is persisted in
    // MessageStore's key_store (save_dek/load_dek) and survives across runs.
    nlohmann::json                 encrypted_dek_;

    // DEK-wrapped X3DH state (own identity key, signed pre-key, one-time pre-keys).
    // Created at registration, published over WS after login, and consumed when
    // establishing sessions. Opaque to C++. Persisted via MessageStore
    // (save_encrypted_state/load_encrypted_state).
    nlohmann::json                 encrypted_state_;

    // Server TLS certificate fingerprint, pinned on first connect (TOFU). Empty
    // until the first handshake, then persisted per-host in MessageStore
    // (save_server_cert/load_server_cert) so the pin survives restarts.
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
