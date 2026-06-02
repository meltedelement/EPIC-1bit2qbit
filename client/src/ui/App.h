#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include "messaging/Conversation.h"

struct AppCallbacks {
    std::function<void(std::string, std::string)> on_register;  // (username, password)
    std::function<void(std::string, std::string)> on_login;     // (username, password)
    std::function<void(std::string, std::string)> on_send;      // (recipient, plaintext)
    std::function<void(uint64_t, bool)>           on_delete;    // (message_id, for_both_parties)
    std::function<void(uint64_t, std::string)>    on_edit;      // (message_id, new_plaintext)
};

class App {
public:
    explicit App(AppCallbacks cbs = {});
    void run();

    // Show a transient status line (e.g. "Login failed: bad PIN").
    // Must be called from the FTXUI event-loop thread.
    // TODO: thread-safe variant via ScreenInteractive::Post() once Connection fires callbacks.
    void push_status(std::string msg);

    // Switch to the chat screen after a successful login.
    // Called by Client once the DEK is unlocked (and later, the WS session is live).
    void advance_to_chat(std::string username);

private:
    void seed_placeholder_data();

    AppCallbacks cbs_;
    std::string  status_msg_;

    int         screen_{0};        // 0=login, 1=chat
    std::string local_username_;

    std::string login_username_;
    std::string login_pin_;

    std::vector<Conversation> conversations_;
    int                       selected_conv_{0};
    std::string               compose_text_;
};
