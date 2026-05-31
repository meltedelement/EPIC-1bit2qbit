#include "connection/TlsContext.h"
#include <stdexcept>
#include <openssl/err.h>
#include <openssl/evp.h>
#include <openssl/x509.h>

TlsContext::TlsContext() {
    ctx_ = SSL_CTX_new(TLS_client_method());
    if (!ctx_) throw std::runtime_error{"SSL_CTX_new failed"};

    SSL_CTX_set_min_proto_version(ctx_, TLS1_3_VERSION);

    if (SSL_CTX_set_default_verify_paths(ctx_) != 1)
        throw std::runtime_error{"SSL_CTX_set_default_verify_paths failed"};
}

TlsContext::~TlsContext() {
    if (ctx_) SSL_CTX_free(ctx_);
}

SSL_CTX* TlsContext::ctx() const { return ctx_; }

std::string TlsContext::cert_sha256_fingerprint(X509* cert) {
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int len = 0;
    if (X509_digest(cert, EVP_sha256(), digest, &len) != 1)
        throw std::runtime_error{"X509_digest failed"};

    static constexpr char hex[] = "0123456789abcdef";
    std::string fp;
    fp.reserve(len * 2);
    for (unsigned i = 0; i < len; ++i) {
        fp += hex[(digest[i] >> 4) & 0xf];
        fp += hex[digest[i] & 0xf];
    }
    return fp;
}

std::string TlsContext::verify_and_pin(SSL* ssl, const std::string& host,
                                       const std::string& pinned_fp) {
    long result = SSL_get_verify_result(ssl);
    if (result != X509_V_OK)
        throw std::runtime_error{std::string{"cert verify failed: "}
                                 + X509_verify_cert_error_string(result)};

    X509* cert = SSL_get1_peer_certificate(ssl);
    if (!cert) throw std::runtime_error{"no peer certificate from " + host};
    struct Guard { X509* c; ~Guard() { X509_free(c); } } g{cert};

    std::string fp = cert_sha256_fingerprint(cert);

    if (!pinned_fp.empty() && fp != pinned_fp)
        throw std::runtime_error{"TOFU pin mismatch for " + host
                                 + " — cert changed, possible MITM"};
    return fp;
}
