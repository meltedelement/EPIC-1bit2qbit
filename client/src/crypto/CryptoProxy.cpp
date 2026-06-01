#include "crypto/CryptoProxy.h"

#include <csignal>
#include <cstring>
#include <stdexcept>

#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {
constexpr int kReadEnd  = 0;
constexpr int kWriteEnd = 1;
}  // namespace

CryptoProxy::CryptoProxy() = default;
CryptoProxy::~CryptoProxy() { stop(); }

void CryptoProxy::start(const std::string& script_path, const std::string& python_exe) {
    if (subprocess_pid_ > 0) {
        throw std::runtime_error("CryptoProxy::start called but subprocess is already running");
    }

    // Writing to a dead subprocess raises SIGPIPE by default, which would kill the
    // whole client. Ignore it process-wide so write() returns EPIPE instead.
    std::signal(SIGPIPE, SIG_IGN);

    int to_child[2];    // parent writes to_child[1] → child reads to_child[0] (stdin)
    int from_child[2];  // child writes from_child[1] → parent reads from_child[0] (stdout)
    if (pipe(to_child) != 0) {
        throw std::runtime_error(std::string("CryptoProxy: pipe() failed: ") + std::strerror(errno));
    }
    if (pipe(from_child) != 0) {
        close(to_child[kReadEnd]);
        close(to_child[kWriteEnd]);
        throw std::runtime_error(std::string("CryptoProxy: pipe() failed: ") + std::strerror(errno));
    }

    pid_t pid = fork();
    if (pid < 0) {
        close(to_child[kReadEnd]);
        close(to_child[kWriteEnd]);
        close(from_child[kReadEnd]);
        close(from_child[kWriteEnd]);
        throw std::runtime_error(std::string("CryptoProxy: fork() failed: ") + std::strerror(errno));
    }

    if (pid == 0) {
        // ── Child ──────────────────────────────────────────────────────────────
        // Redirect stdin/stdout onto the pipes; leave stderr attached to the
        // parent's so Python tracebacks remain visible for debugging.
        dup2(to_child[kReadEnd], STDIN_FILENO);
        dup2(from_child[kWriteEnd], STDOUT_FILENO);

        close(to_child[kReadEnd]);
        close(to_child[kWriteEnd]);
        close(from_child[kReadEnd]);
        close(from_child[kWriteEnd]);

        execlp(python_exe.c_str(), python_exe.c_str(), script_path.c_str(),
               static_cast<char*>(nullptr));
        // Only reached if exec failed.
        _exit(127);
    }

    // ── Parent ───────────────────────────────────────────────────────────────────
    close(to_child[kReadEnd]);
    close(from_child[kWriteEnd]);
    stdin_fd_       = to_child[kWriteEnd];
    stdout_fd_      = from_child[kReadEnd];
    subprocess_pid_ = pid;
}

void CryptoProxy::stop() {
    // Closing the child's stdin sends EOF, which ends its `for line in sys.stdin`
    // loop and lets it exit cleanly.
    if (stdin_fd_ >= 0) {
        close(stdin_fd_);
        stdin_fd_ = -1;
    }
    if (stdout_fd_ >= 0) {
        close(stdout_fd_);
        stdout_fd_ = -1;
    }
    if (subprocess_pid_ > 0) {
        kill(subprocess_pid_, SIGTERM);  // safety net in case it is stuck mid-call
        int status = 0;
        waitpid(subprocess_pid_, &status, 0);
        subprocess_pid_ = -1;
    }
    read_buf_.clear();
}

nlohmann::json CryptoProxy::call(const std::string& method, const nlohmann::json& params) {
    const nlohmann::json request = {{"method", method}, {"params", params}};
    const std::string    reply   = send_recv(request.dump() + "\n");

    nlohmann::json response;
    try {
        response = nlohmann::json::parse(reply);
    } catch (const nlohmann::json::parse_error& e) {
        throw std::runtime_error("CryptoProxy: malformed response from subprocess for method '" +
                                 method + "': " + e.what());
    }

    if (response.contains("error")) {
        throw std::runtime_error("CryptoProxy: subprocess error for method '" + method +
                                 "': " + response["error"].get<std::string>());
    }
    return response.value("result", nlohmann::json::object());
}

std::string CryptoProxy::send_recv(const std::string& line) {
    if (stdin_fd_ < 0 || stdout_fd_ < 0) {
        throw std::runtime_error("CryptoProxy::send_recv called before start()");
    }

    const char* data      = line.data();
    size_t      remaining = line.size();
    while (remaining > 0) {
        ssize_t n = write(stdin_fd_, data, remaining);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(std::string("CryptoProxy: write to subprocess failed: ") +
                                     std::strerror(errno));
        }
        data += n;
        remaining -= static_cast<size_t>(n);
    }
    return read_line();
}

std::string CryptoProxy::read_line() {
    for (;;) {
        const auto newline = read_buf_.find('\n');
        if (newline != std::string::npos) {
            std::string line = read_buf_.substr(0, newline);
            read_buf_.erase(0, newline + 1);
            return line;
        }

        char    buf[4096];
        ssize_t n = read(stdout_fd_, buf, sizeof(buf));
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(std::string("CryptoProxy: read from subprocess failed: ") +
                                     std::strerror(errno));
        }
        if (n == 0) {
            // EOF: the subprocess closed stdout (crashed or exited). Surface any
            // trailing partial line, otherwise report the broken pipe.
            if (!read_buf_.empty()) {
                std::string line = read_buf_;
                read_buf_.clear();
                return line;
            }
            throw std::runtime_error(
                "CryptoProxy: subprocess closed the pipe before sending a response");
        }
        read_buf_.append(buf, static_cast<size_t>(n));
    }
}

// ── DEK lifecycle ──────────────────────────────────────────────────────────────

nlohmann::json CryptoProxy::create_dek(const std::string& pin, const std::string& username) {
    return call("create_dek", {{"pin", pin}, {"username", username}});
}

void CryptoProxy::unlock_dek(const std::string& pin, const std::string& username,
                             const nlohmann::json& encrypted_dek) {
    call("unlock_dek", {{"pin", pin}, {"username", username}, {"encrypted_dek", encrypted_dek}});
}

nlohmann::json CryptoProxy::rotate_dek(const std::string& old_pin, const std::string& new_pin,
                                       const std::string&    username,
                                       const nlohmann::json& encrypted_dek) {
    return call("rotate_dek", {{"old_pin", old_pin},
                               {"new_pin", new_pin},
                               {"username", username},
                               {"encrypted_dek", encrypted_dek}});
}

// ── X3DH state ───────────────────────────────────────────────────────────────────

nlohmann::json CryptoProxy::create_state() {
    return call("create_state");
}

nlohmann::json CryptoProxy::get_bundle(const nlohmann::json& encrypted_state) {
    return call("get_bundle", {{"encrypted_state", encrypted_state}});
}

nlohmann::json CryptoProxy::generate_pre_keys(const nlohmann::json& encrypted_state, int count) {
    return call("generate_pre_keys", {{"encrypted_state", encrypted_state}, {"count", count}});
}

nlohmann::json CryptoProxy::rotate_signed_pre_key(const nlohmann::json& encrypted_state) {
    return call("rotate_signed_pre_key", {{"encrypted_state", encrypted_state}});
}

int CryptoProxy::get_num_pre_keys(const nlohmann::json& encrypted_state) {
    return call("get_num_pre_keys", {{"encrypted_state", encrypted_state}})
        .at("num_pre_keys")
        .get<int>();
}

nlohmann::json CryptoProxy::get_shared_secret_active(const nlohmann::json& encrypted_state,
                                                     const nlohmann::json& bob_bundle) {
    return call("get_shared_secret_active",
                {{"encrypted_state", encrypted_state}, {"bob_bundle", bob_bundle}});
}

nlohmann::json CryptoProxy::get_shared_secret_passive(const nlohmann::json& encrypted_state,
                                                      const nlohmann::json& header) {
    return call("get_shared_secret_passive",
                {{"encrypted_state", encrypted_state}, {"header", header}});
}

nlohmann::json CryptoProxy::delete_hidden_pre_keys(const nlohmann::json& encrypted_state) {
    return call("delete_hidden_pre_keys", {{"encrypted_state", encrypted_state}});
}

// ── Double Ratchet ───────────────────────────────────────────────────────────────

nlohmann::json CryptoProxy::encrypt_initial_message(const std::string& shared_secret,
                                                    const std::string& recipient_ratchet_pub,
                                                    const std::string& message,
                                                    const std::string& associated_data) {
    return call("encrypt_initial_message", {{"shared_secret", shared_secret},
                                            {"recipient_ratchet_pub", recipient_ratchet_pub},
                                            {"message", message},
                                            {"associated_data", associated_data}});
}

nlohmann::json CryptoProxy::decrypt_initial_message(const std::string&    shared_secret,
                                                    const std::string&    own_ratchet_priv,
                                                    const nlohmann::json& encrypted_message,
                                                    const std::string&    associated_data) {
    return call("decrypt_initial_message", {{"shared_secret", shared_secret},
                                            {"own_ratchet_priv", own_ratchet_priv},
                                            {"encrypted_message", encrypted_message},
                                            {"associated_data", associated_data}});
}

nlohmann::json CryptoProxy::encrypt_message(const nlohmann::json& ratchet_state,
                                            const std::string& message,
                                            const std::string& associated_data) {
    return call("encrypt_message", {{"ratchet_state", ratchet_state},
                                    {"message", message},
                                    {"associated_data", associated_data}});
}

nlohmann::json CryptoProxy::decrypt_message(const nlohmann::json& ratchet_state,
                                            const nlohmann::json& encrypted_message,
                                            const std::string& associated_data) {
    return call("decrypt_message", {{"ratchet_state", ratchet_state},
                                    {"encrypted_message", encrypted_message},
                                    {"associated_data", associated_data}});
}
