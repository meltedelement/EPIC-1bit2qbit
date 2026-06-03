#include "messaging/MessageStore.h"

#include <sqlite3.h>
#include <stdexcept>

namespace {

void exec_or_throw(sqlite3* db, const char* sql) {
    char* err = nullptr;
    if (sqlite3_exec(db, sql, nullptr, nullptr, &err) != SQLITE_OK) {
        std::string msg = err ? err : "unknown sqlite error";
        sqlite3_free(err);
        throw std::runtime_error(std::string("MessageStore: ") + msg);
    }
}

struct Stmt {
    sqlite3_stmt* s{nullptr};
    ~Stmt() { sqlite3_finalize(s); }
};

Stmt prepare(sqlite3* db, const char* sql) {
    Stmt stmt;
    sqlite3_prepare_v2(db, sql, -1, &stmt.s, nullptr);
    return stmt;
}

}  // namespace

static constexpr const char* kSchema = R"(
    CREATE TABLE IF NOT EXISTS messages (
        id               INTEGER PRIMARY KEY,
        peer             TEXT    NOT NULL,
        sender           TEXT    NOT NULL DEFAULT '',
        recipient        TEXT    NOT NULL,
        timestamp_ms     INTEGER NOT NULL,
        type             INTEGER NOT NULL DEFAULT 0,
        body             TEXT    NOT NULL DEFAULT '',
        edited           INTEGER NOT NULL DEFAULT 0,
        deleted          INTEGER NOT NULL DEFAULT 0,
        target_id        INTEGER,
        wire_ciphertext  TEXT    NOT NULL DEFAULT '',
        mid              TEXT    NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS conversations (
        peer             TEXT PRIMARY KEY,
        ratchet_state    TEXT NOT NULL DEFAULT '',
        associated_data  TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS pinned_keys (
        username TEXT PRIMARY KEY,
        ik_pub   TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS key_store (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
)";

MessageStore::MessageStore(const std::string& db_path) : db_path_{db_path} {
    if (sqlite3_open(db_path.c_str(), &db_) != SQLITE_OK) {
        throw std::runtime_error(std::string("MessageStore: failed to open database: ") +
                                 sqlite3_errmsg(db_));
    }
    exec_or_throw(db_, kSchema);
    // Migrate existing databases: ADD COLUMN is a no-op if the column already
    // exists (SQLite returns an error we intentionally ignore here).
    sqlite3_exec(db_,
        "ALTER TABLE messages ADD COLUMN wire_ciphertext TEXT NOT NULL DEFAULT ''",
        nullptr, nullptr, nullptr);
    sqlite3_exec(db_,
        "ALTER TABLE messages ADD COLUMN edited INTEGER NOT NULL DEFAULT 0",
        nullptr, nullptr, nullptr);
    sqlite3_exec(db_,
        "ALTER TABLE messages ADD COLUMN mid TEXT NOT NULL DEFAULT ''",
        nullptr, nullptr, nullptr);
    sqlite3_exec(db_,
        "ALTER TABLE messages ADD COLUMN sender TEXT NOT NULL DEFAULT ''",
        nullptr, nullptr, nullptr);
    sqlite3_exec(db_,
        "ALTER TABLE messages ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0",
        nullptr, nullptr, nullptr);

    // If sender was added by ALTER TABLE it lands at the end. Recreate the table
    // with the correct column order (sender between peer and recipient) if needed.
    // The PRAGMA statement must be finalized before BEGIN, so it lives in its own scope.
    int sender_cid = -1;
    {
        auto check = prepare(db_, "PRAGMA table_info(messages)");
        while (sqlite3_step(check.s) == SQLITE_ROW) {
            if (std::string(reinterpret_cast<const char*>(
                    sqlite3_column_text(check.s, 1))) == "sender") {
                sender_cid = sqlite3_column_int(check.s, 0);
                break;
            }
        }
    }  // check finalized here — safe to open a transaction below
    // Column 0=id, 1=peer, 2=sender, 3=recipient — recreate only if wrong.
    if (sender_cid != 2) {
        exec_or_throw(db_, R"(
                BEGIN;
                CREATE TABLE messages_reordered (
                    id               INTEGER PRIMARY KEY,
                    peer             TEXT    NOT NULL,
                    sender           TEXT    NOT NULL DEFAULT '',
                    recipient        TEXT    NOT NULL,
                    timestamp_ms     INTEGER NOT NULL,
                    type             INTEGER NOT NULL DEFAULT 0,
                    body             TEXT    NOT NULL DEFAULT '',
                    edited           INTEGER NOT NULL DEFAULT 0,
                    target_id        INTEGER,
                    wire_ciphertext  TEXT    NOT NULL DEFAULT '',
                    mid              TEXT    NOT NULL DEFAULT ''
                );
                INSERT INTO messages_reordered
                    SELECT id, peer, sender, recipient, timestamp_ms, type, body,
                           edited, target_id, wire_ciphertext, mid
                    FROM messages;
                DROP TABLE messages;
                ALTER TABLE messages_reordered RENAME TO messages;
                COMMIT;
            )");
    }
}

MessageStore::~MessageStore() {
    if (db_) {
        sqlite3_close(db_);
        db_ = nullptr;
    }
}

uint64_t MessageStore::save_message(const Message& msg) {
    auto stmt = prepare(db_, R"(
        INSERT OR REPLACE INTO messages
            (id, peer, sender, recipient, timestamp_ms, type, body, edited, deleted, target_id, wire_ciphertext, mid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    )");
    if (msg.id == 0)
        sqlite3_bind_null(stmt.s, 1);
    else
        sqlite3_bind_int64(stmt.s, 1, static_cast<sqlite3_int64>(msg.id));
    sqlite3_bind_text (stmt.s, 2, msg.peer.c_str(),             -1, SQLITE_TRANSIENT);
    sqlite3_bind_text (stmt.s, 3, msg.sender.c_str(),           -1, SQLITE_TRANSIENT);
    sqlite3_bind_text (stmt.s, 4, msg.recipient.c_str(),        -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt.s, 5, msg.timestamp_ms);
    sqlite3_bind_int  (stmt.s, 6, static_cast<int>(msg.type));
    sqlite3_bind_text (stmt.s, 7, msg.body.c_str(),             -1, SQLITE_TRANSIENT);
    sqlite3_bind_int  (stmt.s, 8, msg.edited   ? 1 : 0);
    sqlite3_bind_int  (stmt.s, 9, msg.deleted  ? 1 : 0);
    if (msg.target_id.has_value())
        sqlite3_bind_int64(stmt.s, 10, static_cast<sqlite3_int64>(*msg.target_id));
    else
        sqlite3_bind_null(stmt.s, 10);
    sqlite3_bind_text(stmt.s, 11, msg.wire_ciphertext.c_str(),  -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.s, 12, msg.mid.c_str(),              -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
    return static_cast<uint64_t>(sqlite3_last_insert_rowid(db_));
}

void MessageStore::delete_message(uint64_t id) {
    auto stmt = prepare(db_, "DELETE FROM messages WHERE id = ?");
    sqlite3_bind_int64(stmt.s, 1, static_cast<sqlite3_int64>(id));
    sqlite3_step(stmt.s);
}

void MessageStore::update_message_body(uint64_t id, const std::string& encrypted_body) {
    auto stmt = prepare(db_, "UPDATE messages SET body = ?, edited = 1 WHERE id = ?");
    sqlite3_bind_text (stmt.s, 1, encrypted_body.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt.s, 2, static_cast<sqlite3_int64>(id));
    sqlite3_step(stmt.s);
}

void MessageStore::update_message_body_by_mid(const std::string& mid, const std::string& encrypted_body) {
    auto stmt = prepare(db_, "UPDATE messages SET body = ?, edited = 1 WHERE mid = ?");
    sqlite3_bind_text(stmt.s, 1, encrypted_body.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.s, 2, mid.c_str(),            -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
}

void MessageStore::mark_message_deleted(uint64_t id) {
    auto stmt = prepare(db_, "UPDATE messages SET deleted = 1, body = '' WHERE id = ?");
    sqlite3_bind_int64(stmt.s, 1, static_cast<sqlite3_int64>(id));
    sqlite3_step(stmt.s);
}

void MessageStore::mark_message_deleted_by_mid(const std::string& mid) {
    auto stmt = prepare(db_, "UPDATE messages SET deleted = 1, body = '' WHERE mid = ?");
    sqlite3_bind_text(stmt.s, 1, mid.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
}

std::optional<Conversation> MessageStore::load_conversation(const std::string& peer) const {
    auto stmt = prepare(db_, R"(
        SELECT id, peer, sender, recipient, timestamp_ms, type, body, edited, deleted, target_id, wire_ciphertext, mid
        FROM messages WHERE peer = ? ORDER BY timestamp_ms
    )");
    sqlite3_bind_text(stmt.s, 1, peer.c_str(), -1, SQLITE_TRANSIENT);

    Conversation conv{peer};
    bool found = false;
    while (sqlite3_step(stmt.s) == SQLITE_ROW) {
        found = true;
        Message m;
        m.id              = static_cast<uint64_t>(sqlite3_column_int64(stmt.s, 0));
        m.peer            = reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 1));
        if (auto* s = sqlite3_column_text(stmt.s, 2))
            m.sender      = reinterpret_cast<const char*>(s);
        m.recipient       = reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 3));
        m.timestamp_ms    = sqlite3_column_int64(stmt.s, 4);
        m.type            = static_cast<MessageType>(sqlite3_column_int(stmt.s, 5));
        m.body            = reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 6));
        m.edited          = sqlite3_column_int(stmt.s, 7) != 0;
        m.deleted         = sqlite3_column_int(stmt.s, 8) != 0;
        if (sqlite3_column_type(stmt.s, 9) != SQLITE_NULL)
            m.target_id   = static_cast<uint64_t>(sqlite3_column_int64(stmt.s, 9));
        if (auto* wc = sqlite3_column_text(stmt.s, 10))
            m.wire_ciphertext = reinterpret_cast<const char*>(wc);
        if (auto* mid = sqlite3_column_text(stmt.s, 11))
            m.mid = reinterpret_cast<const char*>(mid);
        conv.add_message(std::move(m));
    }
    if (!found) return std::nullopt;

    // Conversation crypto state
    {
        auto ms = prepare(db_,
            "SELECT ratchet_state, associated_data FROM conversations WHERE peer = ?");
        sqlite3_bind_text(ms.s, 1, peer.c_str(), -1, SQLITE_TRANSIENT);
        if (sqlite3_step(ms.s) == SQLITE_ROW) {
            auto* rs = sqlite3_column_text(ms.s, 0);
            auto* ad = sqlite3_column_text(ms.s, 1);
            if (rs) conv.set_ratchet_state(reinterpret_cast<const char*>(rs));
            if (ad) conv.set_associated_data(reinterpret_cast<const char*>(ad));
        }
    }

    // TOFU identity key
    if (auto ik = load_pinned_identity_key(peer))
        conv.set_pinned_ik_pub(*ik);

    return conv;
}

std::vector<std::string> MessageStore::list_peers() const {
    auto stmt = prepare(db_,
        "SELECT peer FROM messages GROUP BY peer ORDER BY MAX(timestamp_ms) DESC");
    std::vector<std::string> peers;
    while (sqlite3_step(stmt.s) == SQLITE_ROW)
        peers.emplace_back(reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 0)));
    return peers;
}

void MessageStore::save_ratchet_state(const std::string& peer, const std::string& state) {
    auto stmt = prepare(db_, R"(
        INSERT INTO conversations (peer, ratchet_state, associated_data) VALUES (?, ?, '')
        ON CONFLICT(peer) DO UPDATE SET ratchet_state = excluded.ratchet_state
    )");
    sqlite3_bind_text(stmt.s, 1, peer.c_str(),  -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.s, 2, state.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
}

void MessageStore::save_associated_data(const std::string& peer, const std::string& ad) {
    auto stmt = prepare(db_, R"(
        INSERT INTO conversations (peer, ratchet_state, associated_data) VALUES (?, '', ?)
        ON CONFLICT(peer) DO UPDATE SET associated_data = excluded.associated_data
    )");
    sqlite3_bind_text(stmt.s, 1, peer.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.s, 2, ad.c_str(),   -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
}

void MessageStore::pin_identity_key(const std::string& username, const std::string& ik_pub) {
    auto stmt = prepare(db_,
        "INSERT OR REPLACE INTO pinned_keys (username, ik_pub) VALUES (?, ?)");
    sqlite3_bind_text(stmt.s, 1, username.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.s, 2, ik_pub.c_str(),  -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
}

std::optional<std::string> MessageStore::load_pinned_identity_key(const std::string& username) const {
    auto stmt = prepare(db_,
        "SELECT ik_pub FROM pinned_keys WHERE username = ?");
    sqlite3_bind_text(stmt.s, 1, username.c_str(), -1, SQLITE_TRANSIENT);
    if (sqlite3_step(stmt.s) == SQLITE_ROW)
        return reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 0));
    return std::nullopt;
}

void MessageStore::save_dek(const std::string& username, const std::string& encrypted_dek_json) {
    auto stmt = prepare(db_,
        "INSERT OR REPLACE INTO key_store (key, value) VALUES (?, ?)");
    const std::string key = "dek:" + username;
    sqlite3_bind_text(stmt.s, 1, key.c_str(),                -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.s, 2, encrypted_dek_json.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
}

std::optional<std::string> MessageStore::load_dek(const std::string& username) const {
    auto stmt = prepare(db_,
        "SELECT value FROM key_store WHERE key = ?");
    const std::string key = "dek:" + username;
    sqlite3_bind_text(stmt.s, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    if (sqlite3_step(stmt.s) == SQLITE_ROW)
        return reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 0));
    return std::nullopt;
}

void MessageStore::save_encrypted_state(const std::string& username, const std::string& state_json) {
    auto stmt = prepare(db_,
        "INSERT OR REPLACE INTO key_store (key, value) VALUES (?, ?)");
    const std::string key = "state:" + username;
    sqlite3_bind_text(stmt.s, 1, key.c_str(),    -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.s, 2, state_json.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt.s);
}

std::optional<std::string> MessageStore::load_encrypted_state(const std::string& username) const {
    auto stmt = prepare(db_,
        "SELECT value FROM key_store WHERE key = ?");
    const std::string key = "state:" + username;
    sqlite3_bind_text(stmt.s, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    if (sqlite3_step(stmt.s) == SQLITE_ROW)
        return reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 0));
    return std::nullopt;
}
