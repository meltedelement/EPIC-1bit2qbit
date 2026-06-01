#pragma once
#include <optional>
#include <string>
#include <vector>
#include "messaging/Conversation.h"
#include "messaging/Message.h"

// Local encrypted-at-rest storage for message history and TOFU identity key pins.
class MessageStore {
public:
    explicit MessageStore(const std::string& db_path);

    void save_message(const Message& msg);
    std::optional<Conversation> load_conversation(const std::string& peer) const;
    std::vector<std::string>    list_peers() const;

    void   pin_identity_key(const std::string& username, const std::string& ik_pub);
    std::optional<std::string> load_pinned_identity_key(const std::string& username) const;

private:
    std::string db_path_;
};
