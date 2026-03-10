# ADR 006: Inline HMAC Security Module (Replacing cnlib.token_hash)

## Status

Accepted

## Context

The legacy tvevents-k8s service uses `cnlib.token_hash.security_hash_match()` for HMAC-based request validation. This function is part of the `cnlib` git submodule — a shared library with 31 files, of which only 3 functions are used by this service. The legacy assessment identified a security vulnerability: `security_hash_match()` uses `==` for hash comparison instead of constant-time `hmac.compare_digest()`, making it vulnerable to timing attacks. The cnlib submodule is being eliminated as part of this rebuild.

## Decision

Create an inline `security.py` module in `src/tvevents/domain/` that replaces `cnlib.token_hash`. Implement `security_hash_token()` and `security_hash_match()` with `hmac.compare_digest()` for constant-time comparison. Preserve region-based hash algorithm selection (MD5 for US, SHA-256 for EU via `AWS_REGION == eu-west-1`). The module uses only Python standard library (`hashlib`, `hmac`, `os`).

## Alternatives Considered

- **Keep cnlib submodule** — Rejected. cnlib creates tight coupling, build friction (`setup.py install` during Docker build), and contains the `==` timing vulnerability. The service uses only 3 of 31+ files.
- **Fork cnlib as a standalone package** — Rejected. Over-engineering. The service uses 2 functions from `token_hash.py` — a ~20 line inline module is simpler and eliminates the dependency entirely.
- **Use a third-party HMAC library** — Rejected. Python's standard library `hashlib` and `hmac` modules provide everything needed. No external dependency required.

## Consequences

- **Positive:** Eliminates cnlib submodule dependency. Fixes timing attack vulnerability with `hmac.compare_digest()`. Reduces Docker build complexity (no `setup.py install`). Module is ~30 lines with zero external dependencies.
- **Negative:** Must verify hash output is identical to legacy `cnlib.token_hash` for backward compatibility with TV firmware. Two functions to maintain instead of importing from a shared library.
- **Mitigation:** Unit tests with known tvid/salt/hash triples verify identical output. The module is trivially small — maintenance burden is negligible.
