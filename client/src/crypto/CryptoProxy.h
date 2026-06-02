#pragma once
#include <cstdint>
#include <string>
#include <sys/types.h>
#include <nlohmann/json.hpp>

// IPC bridge to the Python crypto subprocess (client/subprocess_handler.py).
//
// Transport: the subprocess is spawned with its stdin and stdout wired to a pair
// of pipes owned by this process. Requests and responses are newline-delimited
// JSON objects — exactly one request line in, one response line out. All binary
// fields are base64-encoded strings inside the JSON, so they round-trip as plain
// nlohmann::json values that the C++ layer stores and forwards without ever
// interpreting the crypto material.
//
// Wire protocol (see subprocess_handler.py):
//     request  : {"method": "<name>", "params": { ... }}
//     response : {"result": { ... }}   on success
//                {"error":  "<msg>"}   on failure
//
// The subprocess is single-threaded and strictly request/response; call() blocks
// until the matching reply line arrives. This class is NOT thread-safe — callers
// must serialize access if invoking from multiple threads.
class CryptoProxy {
public:
    CryptoProxy();
    ~CryptoProxy();

    CryptoProxy(const CryptoProxy&)            = delete;
    CryptoProxy& operator=(const CryptoProxy&) = delete;

    // Spawns `python_exe script_path` with its stdin/stdout piped to this process.
    // script_path is resolved relative to the subprocess's working directory; its
    // parent directory must contain the crypto_functions package (Python adds the
    // script's own directory to sys.path, so pointing at client/subprocess_handler.py
    // is sufficient). Throws std::runtime_error on fork/pipe failure.
    void start(const std::string& script_path = "subprocess_handler.py",
               const std::string& python_exe  = "python3");

    // Closes the pipes and reaps the subprocess. Safe to call more than once.
    void stop();

    // Core IPC entry point: sends {"method", "params"}, blocks for the reply, and
    // returns the unwrapped "result" object. Throws std::runtime_error if the
    // subprocess answers with {"error": ...} or the pipe closes unexpectedly.
    nlohmann::json call(const std::string&    method,
                        const nlohmann::json& params = nlohmann::json::object());

    // ── DEK lifecycle ──────────────────────────────────────────────────────────
    // The subprocess holds the raw DEK in memory after create/unlock. encrypted_dek
    // blobs are {salt, nonce, ciphertext} the C++ layer persists in the key store.
    nlohmann::json create_dek(const std::string& pin, const std::string& username);
    void           unlock_dek(const std::string& pin, const std::string& username,
                              const nlohmann::json& encrypted_dek);
    nlohmann::json rotate_dek(const std::string& old_pin, const std::string& new_pin,
                              const std::string& username, const nlohmann::json& encrypted_dek);

    // ── X3DH state ─────────────────────────────────────────────────────────────
    // encrypted_state is an opaque {nonce, ciphertext} blob wrapped under the DEK;
    // bundle/header are structured JSON the C++ layer ships to the server or peer.
    nlohmann::json create_state();
    nlohmann::json get_bundle(const nlohmann::json& encrypted_state);
    nlohmann::json generate_pre_keys(const nlohmann::json& encrypted_state, int count);
    nlohmann::json rotate_signed_pre_key(const nlohmann::json& encrypted_state);
    int            get_num_pre_keys(const nlohmann::json& encrypted_state);
    nlohmann::json get_shared_secret_active(const nlohmann::json& encrypted_state,
                                            const nlohmann::json& bob_bundle);
    nlohmann::json get_shared_secret_passive(const nlohmann::json& encrypted_state,
                                             const nlohmann::json& header);
    nlohmann::json delete_hidden_pre_keys(const nlohmann::json& encrypted_state);

    // ── Double Ratchet ─────────────────────────────────────────────────────────
    // message / associated_data / shared_secret / *_ratchet_* are base64 strings,
    // matching what subprocess_handler.py base64-decodes on the way in. ratchet_state
    // and encrypted_message are opaque JSON the C++ layer persists between calls.
    nlohmann::json encrypt_initial_message(const std::string& shared_secret,
                                           const std::string& recipient_ratchet_pub,
                                           const std::string& message,
                                           const std::string& associated_data);
    nlohmann::json decrypt_initial_message(const std::string&    shared_secret,
                                           const std::string&    own_ratchet_priv,
                                           const nlohmann::json& encrypted_message,
                                           const std::string&    associated_data);
    nlohmann::json encrypt_message(const nlohmann::json& ratchet_state,
                                   const std::string& message,
                                   const std::string& associated_data);
    nlohmann::json decrypt_message(const nlohmann::json& ratchet_state,
                                   const nlohmann::json& encrypted_message,
                                   const std::string& associated_data);

private:
    std::string send_recv(const std::string& line);  // write request line, read reply line
    std::string read_line();                          // buffered readline from the subprocess

    int         stdin_fd_{-1};         // we write  → subprocess stdin
    int         stdout_fd_{-1};        // we read   ← subprocess stdout
    pid_t       subprocess_pid_{-1};
    std::string read_buf_;             // holds bytes read past the current line
};
