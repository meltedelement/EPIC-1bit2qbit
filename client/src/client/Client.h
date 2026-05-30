#pragma once
#include <cstdint>
#include <memory>
#include <string>

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
    std::unique_ptr<Connection>    connection_;
    std::unique_ptr<CryptoProxy>   crypto_;
    std::unique_ptr<MessageStore>  store_;
    std::unique_ptr<App>           app_;
};
