#pragma once
#include <string>
#include <openssl/ssl.h>
#include <openssl/x509.h>

// Owns the SSL_CTX and implements CA-verified certificate pinning.
// The peer cert must chain to a system-trusted CA (X509_V_OK) before the pin
// is checked — self-signed certs are rejected. The pin is layered on top of
// CA verification, so this is stronger than pure TOFU, not a substitute.
// Pinned fingerprints are delegated to MessageStore; TlsContext only does
// the OpenSSL verification and fingerprint extraction.
class TlsContext {
public:
    TlsContext();
    ~TlsContext();

    TlsContext(const TlsContext&)            = delete;
    TlsContext& operator=(const TlsContext&) = delete;

    SSL_CTX* ctx() const;

    // Call after SSL_connect(). Validates the cert chain + hostname (must be
    // X509_V_OK), then checks the pin: if pinned_fp is non-empty, throws on
    // mismatch (possible MITM).
    // Returns the observed SHA-256 fingerprint; caller saves it if pinned_fp was empty.
    std::string verify_and_pin(SSL* ssl, const std::string& host,
                               const std::string& pinned_fp);

    static std::string cert_sha256_fingerprint(X509* cert);

private:
    SSL_CTX* ctx_{nullptr};
};
