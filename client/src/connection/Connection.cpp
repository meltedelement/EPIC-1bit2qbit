#include "connection/Connection.h"
#include <stdexcept>

Connection::Connection(const std::string& host, uint16_t port)
    : host_{host}, port_{port}, tcp_sock_{io_ctx_} {}

Connection::~Connection() { disconnect(); }

void Connection::connect(const std::string& pinned_fp) {
    tcp_connect();
    tls_handshake(pinned_fp);
    ws_handshake();
    connected_ = true;
}

void Connection::disconnect() {
    connected_ = false;
    if (ssl_) { SSL_shutdown(ssl_); SSL_free(ssl_); ssl_ = nullptr; }
    if (tcp_sock_.is_open()) tcp_sock_.close();
}

void Connection::send_text(const std::string& payload) {
    if (!connected_) throw std::runtime_error{"not connected"};
    auto frame = ws_encode_frame(payload);
    // TODO: SSL_write(ssl_, frame.data(), frame.size())
    (void)frame;
}

void Connection::on_message(MessageCallback cb) { on_message_cb_ = std::move(cb); }
bool Connection::is_connected() const { return connected_; }

void Connection::tcp_connect() {
    // TODO: Boost.Asio resolve + connect
}

void Connection::tls_handshake(const std::string& pinned_fp) {
    // TODO: SSL_new, SSL_set_fd, SSL_connect, then TlsContext::verify_and_pin
    (void)pinned_fp;
}

void Connection::ws_handshake() {
    // TODO: send HTTP Upgrade request over SSL_write, read 101 response
}

void Connection::read_loop() {
    // TODO: SSL_read loop, decode WS frames, call on_message_cb_
}

std::string Connection::ws_encode_frame(const std::string& /*payload*/) {
    // TODO: RFC 6455 frame encoding (FIN=1, opcode=0x1, mask=1, payload)
    return {};
}

std::string Connection::ws_decode_frame() {
    // TODO: RFC 6455 frame decoding
    return {};
}

std::string Connection::ws_key_base64() {
    // TODO: RAND_bytes(16) → base64
    return {};
}
