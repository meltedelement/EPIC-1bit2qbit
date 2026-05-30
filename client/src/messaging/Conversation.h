#pragma once
#include <string>
#include <vector>
#include "messaging/Message.h"

class Conversation {
public:
    explicit Conversation(std::string peer_username);

    void add_message(Message msg);

    const std::vector<Message>& messages() const;
    const std::string&          peer() const;

private:
    std::string          peer_;
    std::vector<Message> messages_;
};
