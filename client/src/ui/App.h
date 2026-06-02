#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include <ftxui/component/screen_interactive.hpp>
#include "messaging/Conversation.h"

struct AppCallbacks {
    std::function<void(std::string, std::string, std::string)> on_register;  // (username, auth_password, key_pin)
    std::function<void(std::string, std::string, std::string)> on_login;  // (username, auth_password, key_pin)
    std::function<void(std::string, std::string)> on_send;      // (recipient, plaintext)
    std::function<void(uint64_t, bool)>           on_delete;    // (message_id, for_both_parties)
    std::function<void(uint64_t, std::string)>    on_edit;      // (message_id, new_plaintext)
};

class App {
public:
    explicit App(AppCallbacks cbs = {});
    void run();

    void push_status(std::string msg);
    void push_message(const std::string& sender, const std::string& body);
    void push_sent_message(const std::string& recipient, const std::string& body);

    // Called by Client on a wrong-PIN attempt. Disables the login button and
    // shows a countdown for `seconds` seconds before re-enabling it.
    void start_lockout(int seconds);

    // Pre-populate conversation history before switching to the chat screen.
    // Must be called before advance_to_chat().
    void set_conversations(std::vector<Conversation> convs);

    // Switch to the chat screen after a successful login.
    // Called by Client once the DEK is unlocked (and later, the WS session is live).
    void advance_to_chat(std::string username);

private:
    void seed_placeholder_data();

    AppCallbacks cbs_;
    std::string  status_msg_;

    int         active_screen_{0};  // 0=login, 1=chat
    std::string local_username_;

    std::string login_username_;
    std::string login_password_;   // server auth password
    std::string login_key_pin_;    // DEK key PIN (registration only)

    ftxui::ScreenInteractive* screen_ptr_{nullptr};

    std::atomic<bool>         lockout_active_{false};
    std::atomic<int>          lockout_remaining_{0};
    std::atomic<bool>         lockout_quit_{false};
    std::thread               lockout_thread_;

    std::vector<Conversation> conversations_;
    std::vector<std::string>  conv_names_;    // kept in sync with conversations_
    int                       selected_conv_{0};
    std::string               compose_text_;
    std::string               new_peer_;
};
