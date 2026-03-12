# ADR 006: Dependency Management — pip-compile over Flat Requirements

## Status

Accepted

## Context

The legacy evergreen-tvevents service manages dependencies through a flat `requirements.txt` file. Dependencies are listed with pinned versions but without hash verification. There is no separation between abstract dependency declarations (what the service needs) and concrete resolved dependency sets (exact versions with transitive dependencies). Builds are not fully reproducible: the same `requirements.txt` can produce different installed package sets depending on when `pip install` runs, because transitive dependencies are not pinned.

The lack of hash pinning means that a compromised or tampered package on PyPI would be installed without detection. Supply chain integrity is a growing concern for production services, and the legacy dependency workflow provides no protection against this class of attack.

The rebuilder-evergreen-template-repo-python establishes the canonical dependency management pattern: `pyproject.toml` declares abstract dependencies, `scripts/lock.sh` runs `pip-compile` to generate a fully pinned `requirements.txt` with hashes, and CI installs only from the hash-verified lockfile.

## Decision

Adopt the pip-compile workflow with hash pinning, following the template-repo-python pattern:

- `pyproject.toml` declares abstract dependencies with version constraints (e.g., `fastapi>=0.115.0`).
- `scripts/lock.sh` runs `pip-compile` to resolve all transitive dependencies and generate `requirements.txt` with hash digests for every package.
- CI and Docker builds install from the hash-verified `requirements.txt` using `pip install --require-hashes`.
- Development dependencies are declared separately and compiled into `requirements-dev.txt`.

Developers run `scripts/lock.sh` after modifying `pyproject.toml` to regenerate the lockfile. The lockfile is committed to version control.

## Alternatives Considered

**Keep flat requirements.txt.** This is the lowest-effort option but provides no hash pinning, no reproducible builds, and no separation between abstract and resolved dependencies. Supply chain integrity is unverifiable. Does not match the template pattern. Rejected.

**Poetry.** Poetry provides dependency resolution, lockfiles, and virtual environment management through `pyproject.toml` and `poetry.lock`. While Poetry's lockfile includes hashes, the lockfile format is Poetry-specific and less transparent than pip-compile's output (which is a standard `requirements.txt`). Poetry does not match the template pattern, and mixing Poetry-managed services with pip-compile-managed services in the same fleet creates tooling inconsistency. Rejected.

**PDM.** PDM is a modern Python package manager with PEP 582 support and lockfile generation. The same template mismatch concern applies: the fleet standard is pip-compile, and introducing a different dependency manager for one service fragments the tooling ecosystem. Rejected.

**pip-tools without hashes.** Using pip-compile to generate a pinned `requirements.txt` without the `--generate-hashes` flag provides reproducible builds but loses supply chain integrity verification. Since hash generation is a single flag with no runtime cost, omitting it sacrifices security for zero benefit. Rejected.

## Consequences

**Positive:**
- Reproducible builds: the same `requirements.txt` produces identical installs regardless of when or where `pip install` runs.
- Hash-verified installs detect tampered or compromised packages before they are installed.
- Clean separation between abstract dependencies (`pyproject.toml`) and resolved lockfile (`requirements.txt`) makes dependency updates explicit and reviewable in pull requests.
- Template alignment ensures consistent dependency management across the rebuilt service fleet.
- Standard `requirements.txt` output is compatible with all Python tooling (Docker, CI, IDE), unlike format-specific lockfiles.

**Negative:**
- Developers must run `scripts/lock.sh` after every dependency change. Forgetting this step results in a stale lockfile that CI will catch (hash mismatch or missing dependency), but the feedback loop is slower than automatic resolution.
- The two-file workflow (`pyproject.toml` + `requirements.txt`) requires developers to understand which file to edit. Abstract constraints go in `pyproject.toml`; the lockfile is generated, never manually edited.
- Hash pinning means that locally built or private packages without published hashes require additional pip-compile configuration.
