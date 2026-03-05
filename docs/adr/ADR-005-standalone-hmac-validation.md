# ADR 005: Standalone HMAC Validation

## Status
Accepted

## Context
The legacy service authenticates every TV request using HMAC validation, delegating to `cnlib.token_hash.security_hash_match()`. The `cnlib` library is being decommissioned, so this dependency must be removed. Additionally, it is unclear whether `cnlib`'s implementation uses constant-time comparison — a security requirement for HMAC validation to prevent timing attacks. This function is security-critical: it is the sole authentication mechanism for every inbound TV event request.

## Decision
Reimplement HMAC validation using Python's standard library **`hmac`** and **`hashlib`** modules. Use **`hmac.compare_digest()`** for constant-time comparison to prevent timing-based side-channel attacks.

## Alternatives Considered
- **Extract `token_hash` from `cnlib`** — Rejected. Extracting a single module from `cnlib` still requires maintaining the `cnlib` package structure, build tooling, and transitive dependencies. It does not cleanly remove the `cnlib` dependency.
- **Switch to JWT** — Rejected. TV devices authenticate using a pre-shared HMAC scheme. TVs cannot update their authentication mechanism via firmware or configuration push. Changing the auth protocol would break all existing deployed devices.

## Consequences
- **Constant-time comparison** — `hmac.compare_digest()` is guaranteed to run in constant time regardless of input, preventing timing attacks. This is a security improvement if the legacy `cnlib` implementation did not use constant-time comparison.
- **Zero `cnlib` dependency** — HMAC validation is fully self-contained using Python standard library modules. No external packages required.
- **Risk: behavioral parity** — The reimplemented HMAC validation must produce identical results to `cnlib.token_hash.security_hash_match()` for all valid inputs. The hash algorithm, salt processing, string encoding, and comparison logic must be verified against production data before cutover. A mismatch would reject legitimate TV requests or accept invalid ones.
