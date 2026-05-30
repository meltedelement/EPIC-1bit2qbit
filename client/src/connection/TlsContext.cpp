#include "connection/TlsContext.h"
#include <stdexcept>
#include <openssl/err.h>
#include <openssl/evp.h>

TlsContext::TlsContext() {
    SSL_library_init();
    SSL_load_error_strings();
    ctx_ = SSL_CTX_new(TLS_client_method());
    if (!ctx_) throw std::runtime_error{"SSL_CTX_new failed"};

    // Require TLS 1.3 minimum
    SSL_CTX_set_min_proto_version(ctx_, TLS1_3_VERSION);

    // Load system CA bundle for initial certificate chain validation
    if (SSL_CTX_set_default_verify_paths(ctx_) != 1)
        throw std::runtime_error{"SSL_CTX_set_default_verify_paths failed"};
}

TlsContext::~TlsContext() {
    if (ctx_) SSL_CTX_free(ctx_);
}

SSL_CTX* TlsContext::ctx() const { return ctx_; }

bool TlsContext::verify_and_pin(SSL* ssl, const std::string& host,
                                const std::string& pinned_fp) {
    // TODO: implement TOFU pinning
    (void)ssl; (void)host; (void)pinned_fp;
    return true;
}

std::string TlsContext::cert_sha256_fingerprint(X509* /*cert*/) {
    // TODO: EVP_Digest over DER-encoded cert, return hex string
    return {};
}
