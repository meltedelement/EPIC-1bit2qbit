#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

struct AppCallbacks {
    std::function<void(std::string username, std::string password)> on_register;
    std::function<void(std::string username, std::string password)> on_login;
    std::function<void(std::string recipient, std::string plaintext)> on_send;
    std::function<void(uint64_t id, bool for_both)>                   on_delete;
    std::function<void(uint64_t id, std::string new_text)>            on_edit;
};

// FTXUI terminal UI. Drives the screen loop; calls back into Client for actions.
class App {
public:
    explicit App(AppCallbacks cbs);

    void run();  // blocking — takes over the terminal

    // Thread-safe: called from the Connection read loop to append to the chat log
    void push_message(const std::string& from, const std::string& text);
    void push_status(const std::string& text);

private:
    AppCallbacks             cbs_;
    std::vector<std::string> chat_log_;
    std::vector<std::string> status_log_;
};
