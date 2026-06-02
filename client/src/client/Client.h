#pragma once
#include <cstdint>
#include <memory>
#include <string>

#include <nlohmann/json.hpp>

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

    // Inbound (called from Connection read loop)
    void handle_ws_frame(const std::string& json_frame);

    std::string                    host_;
    uint16_t                       port_;
    std::string                    current_user_;

    // The DEK is never held in C++ — the crypto subprocess keeps the raw key in
    // memory after create/unlock. We only retain the encrypted_dek blob
    // ({salt, nonce, ciphertext}) needed to unlock it again.
    // TODO(persistence): this belongs in MessageStore / the local key store so it
    // survives across runs; for now it lives only for the session.
    nlohmann::json                 encrypted_dek_;

    std::unique_ptr<Connection>    connection_;
    std::unique_ptr<CryptoProxy>   crypto_;
    std::unique_ptr<MessageStore>  store_;
    std::unique_ptr<App>           app_;
};
