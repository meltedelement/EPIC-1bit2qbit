#include "client/Client.h"
#include "connection/Connection.h"
#include "crypto/CryptoProxy.h"
#include "messaging/MessageStore.h"
#include "ui/App.h"

Client::Client(const std::string& host, uint16_t port)
    : host_{host}, port_{port} {}

Client::~Client() = default;

void Client::run() {
    // TODO: wire up subsystems and start the TUI
}

void Client::do_register(const std::string& /*username*/, const std::string& /*password*/) {}
void Client::do_login(const std::string& /*username*/, const std::string& /*password*/) {}
void Client::do_send(const std::string& /*recipient*/, const std::string& /*plaintext*/) {}
void Client::do_delete(uint64_t /*message_id*/, bool /*for_both_parties*/) {}
void Client::do_edit(uint64_t /*message_id*/, const std::string& /*new_plaintext*/) {}
void Client::handle_ws_frame(const std::string& /*json_frame*/) {}
