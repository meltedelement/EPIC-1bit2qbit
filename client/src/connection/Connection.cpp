#include "connection/Connection.h"
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <openssl/err.h>
#include <openssl/evp.h>
#include <openssl/rand.h>

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

// ─── TCP ─────────────────────────────────────────────────────────────────────

void Connection::tcp_connect() {
    boost::asio::ip::tcp::resolver resolver{io_ctx_};
    auto endpoints = resolver.resolve(host_, std::to_string(port_));
    boost::asio::connect(tcp_sock_, endpoints);
}

// ─── TLS ─────────────────────────────────────────────────────────────────────

void Connection::tls_handshake(const std::string& pinned_fp) {
    ssl_ = SSL_new(tls_ctx_.ctx());
    if (!ssl_) throw std::runtime_error{"SSL_new failed"};

    // SNI — tells the server which hostname we want so it picks the right cert
    SSL_set_tlsext_host_name(ssl_, host_.c_str());

    // Hostname verification — OpenSSL checks CN/SAN during SSL_connect
    SSL_set1_host(ssl_, host_.c_str());
    SSL_set_verify(ssl_, SSL_VERIFY_PEER, nullptr);

    SSL_set_fd(ssl_, static_cast<int>(tcp_sock_.native_handle()));

    if (SSL_connect(ssl_) != 1) {
        unsigned long err = ERR_get_error();
        throw std::runtime_error{std::string{"SSL_connect failed: "}
                                 + ERR_error_string(err, nullptr)};
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
    RAND_bytes(buf, sizeof(buf));
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

    if (response.find("101") == std::string::npos)
        throw std::runtime_error{"ws_handshake: expected 101 Switching Protocols, got: "
                                 + response.substr(0, response.find('\r'))};
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
    RAND_bytes(mask, sizeof(mask));
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
// Handles ping (sends pong) and close frames internally; returns data payload.
std::string Connection::ws_decode_frame() {
    while (true) {
        std::string hdr = ssl_read_exact(2);
        uint8_t opcode      = static_cast<uint8_t>(hdr[0]) & 0x0f;
        bool    server_mask = (static_cast<uint8_t>(hdr[1]) & 0x80) != 0;
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

        // Server masking is forbidden by the spec; skip mask bytes if present anyway
        std::string mask_bytes;
        if (server_mask) mask_bytes = ssl_read_exact(4);

        std::string payload = ssl_read_exact(static_cast<size_t>(payload_len));
        if (server_mask) {
            for (size_t i = 0; i < payload.size(); ++i)
                payload[i] ^= mask_bytes[i % 4];
        }

        if (opcode == 0x08) throw std::runtime_error{"ws: server sent close frame"};
        if (opcode == 0x09) { ws_send_frame(0x0a, payload); continue; }  // ping → pong
        if (opcode == 0x01 || opcode == 0x02) return payload;
        // continuation / unknown control frames: ignore
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
        } catch (const std::exception&) {
            // Connection closed or error — exit loop and mark disconnected
            connected_ = false;
            running_   = false;
        }
    }
}
