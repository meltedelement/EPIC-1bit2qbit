#include "messaging/MessageStore.h"

MessageStore::MessageStore(const std::string& db_path) : db_path_{db_path} {
    // TODO: open SQLite (or SQLCipher) database, run schema migrations
}

void MessageStore::save_message(const Message& /*msg*/) {
    // TODO: INSERT INTO messages
}

std::optional<Conversation> MessageStore::load_conversation(const std::string& peer) const {
    // TODO: SELECT from messages WHERE sender=peer OR recipient=peer, ORDER BY timestamp
    (void)peer;
    return std::nullopt;
}

std::vector<std::string> MessageStore::list_peers() const {
    // TODO: SELECT DISTINCT peer from messages
    return {};
}

void MessageStore::pin_identity_key(const std::string& /*username*/,
                                    const std::string& /*ik_pub*/) {
    // TODO: UPSERT into pinned_keys (ik_pub is raw public key bytes, base64-encoded)
}

std::optional<std::string> MessageStore::load_pinned_identity_key(const std::string& /*username*/) const {
    // TODO: SELECT ik_pub FROM pinned_keys WHERE username = ?
    return std::nullopt;
}
