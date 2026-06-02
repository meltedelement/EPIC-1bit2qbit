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
        id           INTEGER PRIMARY KEY,
        peer         TEXT    NOT NULL,
        recipient    TEXT    NOT NULL,
        timestamp_ms INTEGER NOT NULL,
        type         INTEGER NOT NULL DEFAULT 0,
        body         TEXT    NOT NULL DEFAULT '',
        target_id    INTEGER
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
}

MessageStore::~MessageStore() {
    if (db_) {
        sqlite3_close(db_);
        db_ = nullptr;
    }
}

void MessageStore::save_message(const Message& msg) {
    auto stmt = prepare(db_, R"(
        INSERT OR REPLACE INTO messages (id, peer, recipient, timestamp_ms, type, body, target_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    )");
    sqlite3_bind_int64(stmt.s, 1, static_cast<sqlite3_int64>(msg.id));
    sqlite3_bind_text (stmt.s, 2, msg.peer.c_str(),      -1, SQLITE_TRANSIENT);
    sqlite3_bind_text (stmt.s, 3, msg.recipient.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt.s, 4, msg.timestamp_ms);
    sqlite3_bind_int  (stmt.s, 5, static_cast<int>(msg.type));
    sqlite3_bind_text (stmt.s, 6, msg.body.c_str(),      -1, SQLITE_TRANSIENT);
    if (msg.target_id.has_value())
        sqlite3_bind_int64(stmt.s, 7, static_cast<sqlite3_int64>(*msg.target_id));
    else
        sqlite3_bind_null(stmt.s, 7);
    sqlite3_step(stmt.s);
}

std::optional<Conversation> MessageStore::load_conversation(const std::string& peer) const {
    auto stmt = prepare(db_, R"(
        SELECT id, peer, recipient, timestamp_ms, type, body, target_id
        FROM messages WHERE peer = ? ORDER BY timestamp_ms
    )");
    sqlite3_bind_text(stmt.s, 1, peer.c_str(), -1, SQLITE_TRANSIENT);

    Conversation conv{peer};
    bool found = false;
    while (sqlite3_step(stmt.s) == SQLITE_ROW) {
        found = true;
        Message m;
        m.id           = static_cast<uint64_t>(sqlite3_column_int64(stmt.s, 0));
        m.peer         = reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 1));
        m.recipient    = reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 2));
        m.timestamp_ms = sqlite3_column_int64(stmt.s, 3);
        m.type         = static_cast<MessageType>(sqlite3_column_int(stmt.s, 4));
        m.body         = reinterpret_cast<const char*>(sqlite3_column_text(stmt.s, 5));
        if (sqlite3_column_type(stmt.s, 6) != SQLITE_NULL)
            m.target_id = static_cast<uint64_t>(sqlite3_column_int64(stmt.s, 6));
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
