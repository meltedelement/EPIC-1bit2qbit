#pragma once
#include <cstdint>
#include <string>

struct Message {
    uint64_t    id{0};
    std::string sender;
    std::string recipient;
    std::string ciphertext;   // base64-encoded AES-256-GCM ciphertext
    std::string nonce;        // base64-encoded 96-bit GCM nonce
    int64_t     timestamp_ms{0};
    bool        editable{true};  // false once the edit window closes
};
