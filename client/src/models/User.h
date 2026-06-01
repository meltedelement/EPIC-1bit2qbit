#pragma once
#include <string>

struct User {
    std::string username;
    std::string identity_key_fingerprint;  // SHA-256 hex; pinned on first contact (TOFU)
};
