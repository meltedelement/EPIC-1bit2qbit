#pragma once
#include <atomic>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
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

    // Blocking: TCP connect → TLS handshake + TOFU pin → WS upgrade.
    // pinned_fp: pass the stored fingerprint from MessageStore, or "" for first use.
    // After connect(), call cert_fingerprint() to get the observed fingerprint;
    // if pinned_fp was empty, save it to MessageStore.
    void connect(const std::string& pinned_fp = "");
    void disconnect();

    void send_text(const std::string& payload);
    void on_message(MessageCallback cb);

    bool        is_connected() const;
    std::string cert_fingerprint() const;  // observed server cert fingerprint

private:
    void tcp_connect();
    void tls_handshake(const std::string& pinned_fp);
    void ws_handshake();
    void read_loop();

    // Raw SSL I/O
    std::string ssl_read_exact(size_t n);
    void        ssl_write_all(const std::string& data);

    // WebSocket framing
    void        ws_send_frame(uint8_t opcode, const std::string& payload);
    std::string ws_encode_frame(uint8_t opcode, const std::string& payload);
    std::string ws_decode_frame();
    std::string ws_key_base64();

    std::string                       host_;
    uint16_t                          port_;
    TlsContext                        tls_ctx_;
    boost::asio::io_context           io_ctx_;
    boost::asio::ip::tcp::socket      tcp_sock_;
    SSL*                              ssl_{nullptr};
    std::string                       server_cert_fp_;
    MessageCallback                   on_message_cb_;
    std::atomic<bool>                 connected_{false};
    std::atomic<bool>                 running_{false};
    std::thread                       read_thread_;
    std::mutex                        write_mutex_;
};
