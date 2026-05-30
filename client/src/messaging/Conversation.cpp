#include "messaging/Conversation.h"
#include <utility>

Conversation::Conversation(std::string peer_username)
    : peer_{std::move(peer_username)} {}

void Conversation::add_message(Message msg) { messages_.push_back(std::move(msg)); }
const std::vector<Message>& Conversation::messages() const { return messages_; }
const std::string&          Conversation::peer()     const { return peer_; }
