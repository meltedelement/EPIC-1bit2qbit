#pragma once
#include <cstdint>
#include <string>

constexpr int64_t EDIT_WINDOW_MS = 15LL * 60 * 1000;

// Plaintext content — serialized to JSON, then encrypted into EncryptedPayload
struct MessageContent {
    std::string sender_id;
    std::string body;
};

// Opaque blob the server forwards but cannot read
struct EncryptedPayload {
    std::string ciphertext;  // base64 AES-256-GCM ciphertext of serialized MessageContent
    std::string nonce;       // base64 96-bit GCM nonce
};

// Server-visible routing envelope
struct MessageEnvelope {
    uint64_t         id{0};
    std::string      recipient;
    int64_t          timestamp_ms{0};  // server-assigned on receipt
    EncryptedPayload payload;
};

// Client-side decrypted view, populated after CryptoProxy processes an envelope
struct Message {
    uint64_t    id{0};
    std::string sender_id;
    int64_t     timestamp_ms{0};
    std::string body;
};

inline bool is_editable(int64_t message_timestamp_ms, int64_t now_ms) {
    return (now_ms - message_timestamp_ms) < EDIT_WINDOW_MS;
}
