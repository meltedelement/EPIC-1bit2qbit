#pragma once
#include <optional>
#include <string>
#include <vector>
#include "messaging/Conversation.h"
#include "messaging/Message.h"

// Local encrypted-at-rest storage for message history and pinned key fingerprints.
class MessageStore {
public:
    explicit MessageStore(const std::string& db_path);

    void save_message(const Message& msg);
    std::optional<Conversation> load_conversation(const std::string& peer) const;
    std::vector<std::string>    list_peers() const;

    void   save_pinned_key(const std::string& username, const std::string& fingerprint);
    std::optional<std::string> load_pinned_key(const std::string& username) const;

private:
    std::string db_path_;
};
