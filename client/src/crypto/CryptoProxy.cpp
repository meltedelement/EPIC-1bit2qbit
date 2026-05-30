#include "crypto/CryptoProxy.h"
#include <stdexcept>

CryptoProxy::CryptoProxy() = default;
CryptoProxy::~CryptoProxy() { stop(); }

void CryptoProxy::start(const std::string& script_path) {
    // TODO: generate socket_path_ (e.g. /tmp/epic-crypto-<pid>.sock)
    //       fork() → execvp("python3", {script_path, socket_path_}) in child
    //       connect Unix domain socket in parent
    (void)script_path;
}

void CryptoProxy::stop() {
    if (sockfd_ >= 0) { close(sockfd_); sockfd_ = -1; }
    if (subprocess_pid_ > 0) { kill(subprocess_pid_, SIGTERM); subprocess_pid_ = -1; }
}

nlohmann::json CryptoProxy::call(const nlohmann::json& request) {
    auto line    = request.dump() + "\n";
    auto reply   = send_recv(line);
    return nlohmann::json::parse(reply);
}

nlohmann::json CryptoProxy::pqxdh_init_sender(const nlohmann::json& recipient_bundle) {
    return call({{"method", "pqxdh_init_sender"}, {"bundle", recipient_bundle}});
}

nlohmann::json CryptoProxy::ratchet_encrypt(const std::string& plaintext,
                                             const std::string& session_id) {
    return call({{"method", "ratchet_encrypt"},
                 {"session_id", session_id},
                 {"plaintext", plaintext}});
}

nlohmann::json CryptoProxy::ratchet_decrypt(const nlohmann::json& ciphertext_envelope,
                                             const std::string& session_id) {
    return call({{"method", "ratchet_decrypt"},
                 {"session_id", session_id},
                 {"envelope", ciphertext_envelope}});
}

std::string CryptoProxy::send_recv(const std::string& line) {
    // TODO: write(sockfd_, line), read response line, return
    (void)line;
    return "{}";
}
