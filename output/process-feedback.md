# Process Feedback Capture — tvevents-k8s Rebuild

## Manual Corrections Required During Build

### 1. Python 3.9 Type Hint Incompatibility

**What happened:** Generated code used `X | None` union syntax and `dict[str, Any]` lowercase generics, which are Python 3.10+ features. The build environment runs Python 3.9.

**Why the process didn't handle it:** IDEATION_PROCESS.md does not require checking the build environment's Python version before code generation. ADR-001 specifies Python 3.12 as the target, but the local development machine runs 3.9.

**Proposed fix:** Add to IDEATION_PROCESS.md Step 12 (or a new pre-build step): "Before generating code, verify the local Python version. If the local version is older than the target version, add `from __future__ import annotations` to all Python files and use `typing` module generics (`Optional[X]`, `Dict`, `List`) in runtime positions."

### 2. Circular Import / Mock Patch Path Issues

**What happened:** Singleton functions (`get_rds_client`, `get_blacklist_cache`) were defined in `main.py` and imported lazily inside route/ops handler functions. Tests could not patch these because `unittest.mock.patch` requires the symbol to exist as an attribute of the module being patched. Lazy imports inside functions create local variables, not module-level attributes.

**Why the process didn't handle it:** The process does not specify a pattern for dependency injection or singleton management. The generated code used lazy imports to avoid circular dependencies between `main.py` and `routes.py`/`ops.py`, but this pattern is incompatible with standard Python mocking.

**Proposed fix:** Add to developer-agent skill.md Coding Practices: "Use a dedicated `deps.py` module for singleton holders. Import from `deps.py` at the top level of consumer modules. Never use lazy imports inside functions for dependencies that need to be mocked in tests. Patch targets must be the importing module, not the defining module."

### 3. Test Fixture Data Not Matching Flattened Output Structure

**What happened:** Test fixtures used `programdata_starttime` as a key inside nested `programData` dict, but the flatten function adds the parent key as prefix — so `programData.starttime` becomes `programdata_starttime`. The fixture should have used `starttime` inside the nested dict. Similarly, obfuscation tests expected `channelid` as a top-level key but the flattened output produces `channeldata_channelid`.

**Why the process didn't handle it:** The process does not require running a "fixture validation" step where test data is traced through the actual transform pipeline before writing assertions. Step 13a (Domain-Realistic Test Scenarios) focuses on naming and realism but not on structural correctness of flattened output.

**Proposed fix:** Add to IDEATION_PROCESS.md Step 13a: "After writing test fixtures, trace at least one fixture through the actual transform/flatten pipeline to verify that assertion keys match the real output structure. Do not assume key names — verify them."

### 4. Edit Tool Not Persisting Changes

**What happened:** The IDE edit tool reported successful edits to `ops.py` multiple times, but `grep` on the actual file showed the changes were not applied. Required falling back to shell `cat >` to overwrite the file.

**Why the process didn't handle it:** This is a tooling issue, not a process gap. The edit tool may have conflicts when multiple rapid edits target the same file regions.

**Proposed fix:** No process change needed. When edits fail to persist, verify with `grep` and fall back to file rewrite.

## Summary

| # | Issue | Root Cause | Process Gap |
|---|-------|-----------|-------------|
| 1 | Python 3.9 type hint syntax | Build env != target version | No pre-build Python version check |
| 2 | Unpatchable lazy imports | No DI pattern specified | No singleton management guidance |
| 3 | Wrong flattened key names in fixtures | No fixture-through-pipeline validation | Step 13a missing structural verification |
| 4 | Edit tool not persisting | Tooling issue | N/A |
