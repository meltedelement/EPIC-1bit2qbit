#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <boost/asio.hpp>
#include <openssl/ssl.h>
#include "connection/TlsContext.h"

using MessageCallback = std::function<void(std::string)>;

// Manages the full connection pipeline: TCP (Boost.Asio) → TLS (raw OpenSSL)
// → WebSocket upgrade → framed message I/O.
class Connection {
public:
    Connection(const std::string& host, uint16_t port);
    ~Connection();

    Connection(const Connection&)            = delete;
    Connection& operator=(const Connection&) = delete;

    // Blocking: TCP connect → TLS handshake + TOFU pin → WS upgrade
    void connect(const std::string& pinned_fp = "");
    void disconnect();

    void send_text(const std::string& payload);  // sends a WS text frame
    void on_message(MessageCallback cb);

    bool is_connected() const;

private:
    void        tcp_connect();
    void        tls_handshake(const std::string& pinned_fp);
    void        ws_handshake();
    void        read_loop();

    std::string ws_encode_frame(const std::string& payload);
    std::string ws_decode_frame();
    std::string ws_key_base64();  // random 16-byte nonce, base64

    std::string                       host_;
    uint16_t                          port_;
    TlsContext                        tls_ctx_;
    boost::asio::io_context           io_ctx_;
    boost::asio::ip::tcp::socket      tcp_sock_;
    SSL*                              ssl_{nullptr};
    MessageCallback                   on_message_cb_;
    bool                              connected_{false};
};
