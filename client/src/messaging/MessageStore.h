#pragma once
#include <optional>
#include <string>
#include <vector>
#include "messaging/Conversation.h"
#include "messaging/Message.h"

struct sqlite3;

// Local storage for message history, TOFU identity key pins, and the encrypted DEK.
class MessageStore {
public:
    explicit MessageStore(const std::string& db_path);
    ~MessageStore();

    MessageStore(const MessageStore&)            = delete;
    MessageStore& operator=(const MessageStore&) = delete;

    // ── Messages ───────────────────────────────────────────────────────────────
    uint64_t save_message(const Message& msg);   // returns DB-assigned rowid
    void     delete_message(uint64_t id);
    void     update_message_body(uint64_t id,         const std::string& encrypted_body);
    void     update_message_body_by_mid(const std::string& mid, const std::string& encrypted_body);
    void     mark_message_deleted(uint64_t id);
    void     mark_message_deleted_by_mid(const std::string& mid);
    std::optional<Conversation> load_conversation(const std::string& peer) const;
    std::vector<std::string>    list_peers() const;

    // ── Conversation crypto state ──────────────────────────────────────────────
    void save_ratchet_state(const std::string& peer, const std::string& state);
    void save_associated_data(const std::string& peer, const std::string& ad);

    // ── TOFU identity key pins ─────────────────────────────────────────────────
    void pin_identity_key(const std::string& username, const std::string& ik_pub);
    std::optional<std::string> load_pinned_identity_key(const std::string& username) const;

    // ── Encrypted DEK / X3DH state persistence ────────────────────────────────
    void save_dek(const std::string& username, const std::string& encrypted_dek_json);
    std::optional<std::string> load_dek(const std::string& username) const;

    void save_encrypted_state(const std::string& username, const std::string& state_json);
    std::optional<std::string> load_encrypted_state(const std::string& username) const;

private:
    std::string db_path_;
    sqlite3*    db_{nullptr};
};
