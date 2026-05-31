#include "messaging/Conversation.h"
#include <utility>

Conversation::Conversation(std::string peer_username)
    : peer_{std::move(peer_username)} {}

void Conversation::add_message(Message msg) { messages_.push_back(std::move(msg)); }

const std::vector<Message>& Conversation::messages()      const { return messages_; }
const std::string&          Conversation::peer()          const { return peer_; }
const std::string&          Conversation::ratchet_state() const { return ratchet_state_; }
const std::string&          Conversation::associated_data() const { return associated_data_; }
const std::string&          Conversation::pinned_ik_pub() const { return pinned_ik_pub_; }

void Conversation::set_ratchet_state(std::string state)  { ratchet_state_   = std::move(state); }
void Conversation::set_associated_data(std::string ad)   { associated_data_ = std::move(ad); }
void Conversation::set_pinned_ik_pub(std::string ik_pub) { pinned_ik_pub_   = std::move(ik_pub); }
