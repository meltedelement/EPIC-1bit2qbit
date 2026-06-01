#pragma once
#include <string>
#include <vector>
#include "messaging/Conversation.h"

class App {
public:
    void run();

private:
    void seed_placeholder_data();

    int         screen_{0};         // 0=login, 1=chat
    std::string local_username_;

    std::string login_username_;
    std::string login_pin_;

    std::vector<Conversation> conversations_;
    int                       selected_conv_{0};
    std::string               compose_text_;
};
