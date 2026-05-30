#pragma once
#include <string>
#include <nlohmann/json.hpp>
#include <sys/types.h>

// IPC bridge to the Python crypto subprocess (crypto_functions/).
// Communicates over a Unix domain socket using newline-delimited JSON.
// All blocking I/O; the subprocess is single-threaded request/response.
class CryptoProxy {
public:
    CryptoProxy();
    ~CryptoProxy();

    CryptoProxy(const CryptoProxy&)            = delete;
    CryptoProxy& operator=(const CryptoProxy&) = delete;

    // Spawns the Python subprocess and connects to its Unix socket.
    void start(const std::string& script_path = "crypto_functions/main.py");
    void stop();

    // Raw JSON call — sends {"method": ..., ...} and returns the response object.
    nlohmann::json call(const nlohmann::json& request);

    // Convenience wrappers around call()
    nlohmann::json pqxdh_init_sender(const nlohmann::json& recipient_bundle);
    nlohmann::json ratchet_encrypt(const std::string& plaintext, const std::string& session_id);
    nlohmann::json ratchet_decrypt(const nlohmann::json& ciphertext_envelope, const std::string& session_id);

private:
    std::string send_recv(const std::string& line);

    std::string socket_path_;
    int         sockfd_{-1};
    pid_t       subprocess_pid_{-1};
};
