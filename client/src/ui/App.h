#pragma once
#include <atomic>
#include <cstdint>
#include <functional>
#include <string>
#include <thread>
#include <vector>
#include <ftxui/component/screen_interactive.hpp>
#include "messaging/Conversation.h"
#include "messaging/Message.h"

struct AppCallbacks {
    std::function<void(std::string, std::string, std::string)> on_register;  // (username, auth_password, key_pin)
    std::function<void(std::string, std::string, std::string)> on_login;     // (username, auth_password, key_pin)
    std::function<void(std::string, std::string)> on_send;      // (recipient, plaintext)
    std::function<void(uint64_t, bool)>           on_delete;    // (message_id, for_both)
    std::function<void(uint64_t, std::string)>    on_edit;      // (message_id, new_plaintext)
    std::function<void(std::string, std::string)> on_forward;   // (recipient, body)
    std::function<void()>                         on_logout;
};

class App {
public:
    explicit App(AppCallbacks cbs = {});
    void run();

    void push_status(std::string msg);
    void push_message(const Message& msg);
    void push_sent_message(const Message& msg);

    // Called by Client when a message body is edited locally.
    void update_message_body(uint64_t id, const std::string& new_body);
    void update_message_body_by_mid(const std::string& mid, const std::string& new_body);
    void mark_message_deleted(uint64_t id);
    void mark_message_deleted_by_mid(const std::string& mid);
    void remove_message(uint64_t id);

    // Called by Client on a wrong-PIN attempt.
    void start_lockout(int seconds);

    void set_conversations(std::vector<Conversation> convs);
    void advance_to_chat(std::string username);

    // Called by Client whenever the WebSocket connection state changes.
    void set_connected(bool connected);

    // Return to the login screen after a logout.
    void return_to_login();

private:
    void seed_placeholder_data();

    AppCallbacks cbs_;
    std::string  status_msg_;

    int         active_screen_{0};
    std::string local_username_;

    std::string login_username_;
    std::string login_password_;
    std::string login_key_pin_;

    ftxui::ScreenInteractive* screen_ptr_{nullptr};
    std::atomic<bool>         connected_{false};

    std::atomic<bool>         lockout_active_{false};
    std::atomic<int>          lockout_remaining_{0};
    std::atomic<bool>         lockout_quit_{false};
    std::thread               lockout_thread_;

    std::vector<Conversation> conversations_;
    std::vector<std::string>  conv_names_;
    int                       selected_conv_{0};
    std::string               compose_text_;
    std::string               new_peer_;

    // Message selection / options state
    int         selected_msg_{-1};
    bool        msg_options_open_{false};
    bool        editing_msg_{false};
    uint64_t    editing_msg_id_{0};
    bool        forwarding_msg_{false};
    std::string forwarding_body_;
};
