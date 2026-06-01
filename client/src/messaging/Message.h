#pragma once
#include <cstdint>
#include <optional>
#include <string>

constexpr int64_t EDIT_WINDOW_MS = 15LL * 60 * 1000;

// Matches subprocess_handler _serialize_ratchet_message
struct RatchetHeader {
    std::string ratchet_pub;
    uint32_t    sending_chain_length{0};
    uint32_t    previous_sending_chain_length{0};
};

// Matches subprocess_handler _serialize_x3dh_header — only on first message to a peer
struct X3DHHeader {
    std::string                identity_key;    // base64 sender IK — authenticates sender
    std::string                ephemeral_key;   // base64
    std::string                signed_pre_key;  // base64 recipient SPK used
    std::optional<std::string> pre_key;         // base64 OPK used, or nullopt
};

enum class MessageType {
    Standard,
    Edit,
    Delete,
    Forward,
    ReadReceipt,
    DeliveryReceipt,
    TamperWarning,
    Reply,             // tentative
};

// Plaintext content — serialized to JSON and encrypted into EncryptedPayload::ciphertext.
// target_id: Edit/Delete/Reply/ReadReceipt/DeliveryReceipt reference the affected message.
struct MessageContent {
    MessageType              type{MessageType::Standard};
    std::string              body;
    std::optional<uint64_t>  target_id;
};

// Wire payload — forwarded opaquely by the server.
// x3dh_header present only on the first message of a new conversation.
struct EncryptedPayload {
    RatchetHeader             ratchet_header;
    std::string               ciphertext;   // base64 DR ciphertext of serialized MessageContent
    std::optional<X3DHHeader> x3dh_header;
};

// Routing envelope — only recipient is set by the sender; id and timestamp_ms
// are assigned by the server on receipt.
struct MessageEnvelope {
    uint64_t         id{0};
    std::string      recipient;
    int64_t          timestamp_ms{0};
    EncryptedPayload payload;
};

// Decrypted view stored locally and rendered in the TUI.
// Direction is derived at render time: recipient == local username → received, else sent.
struct Message {
    uint64_t                id{0};
    std::string             peer;       // the other party in the conversation
    std::string             recipient;  // from envelope
    int64_t                 timestamp_ms{0};
    MessageType             type{MessageType::Standard};
    std::string             body;
    std::optional<uint64_t> target_id;
};

inline bool is_editable(int64_t message_timestamp_ms, int64_t now_ms) {
    // Guard against future-dated timestamps (clock skew): a negative delta would
    // otherwise be < EDIT_WINDOW_MS and wrongly report the message as editable.
    return now_ms >= message_timestamp_ms &&
           (now_ms - message_timestamp_ms) < EDIT_WINDOW_MS;
}
