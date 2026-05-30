#pragma once
#include <string>
#include <openssl/ssl.h>
#include <openssl/x509.h>

// Owns the SSL_CTX and implements TOFU certificate pinning.
// Pinned fingerprints are delegated to MessageStore; TlsContext only does
// the OpenSSL verification and fingerprint extraction.
class TlsContext {
public:
    TlsContext();
    ~TlsContext();

    TlsContext(const TlsContext&)            = delete;
    TlsContext& operator=(const TlsContext&) = delete;

    SSL_CTX* ctx() const;

    // Call after SSL_connect(). Returns true if cert is new (pinned now)
    // or matches the already-pinned fingerprint for this host.
    // Throws std::runtime_error on mismatch (possible MITM).
    bool verify_and_pin(SSL* ssl, const std::string& host,
                        const std::string& pinned_fp);

    static std::string cert_sha256_fingerprint(X509* cert);

private:
    SSL_CTX* ctx_{nullptr};
};
