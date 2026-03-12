# Helm Unit Tests

Unit tests for Helm chart templates using [helm-unittest](https://github.com/helm-unittest/helm-unittest).

## Installation

```bash
helm plugin install https://github.com/helm-unittest/helm-unittest
```

## Running Tests

```bash
# Run all tests
helm unittest charts

# Run with verbose output
helm unittest -3 charts

# Run specific test file
helm unittest -f 'tests/deployment_test.yaml' charts

# Run with color output
helm unittest --color charts
```

## Test Files

- **deployment_test.yaml** - Validates deployment image path generation
- **poddisruptionbudget_test.yaml** - Validates PDB configuration
- **service_test.yaml** - Validates service configuration

## Test Structure

Each test file follows this structure:

```yaml
suite: test name
templates:
  - TemplateName.yaml
tests:
  - it: should do something
    set:
      # Values to set
    asserts:
      - assertion
```

## Common Assertions

- `isKind: {of: Kind}` - Check resource kind
- `equal: {path: spec.field, value: expected}` - Check exact value
- `matchRegex: {path: spec.field, pattern: regex}` - Check pattern match
- `isNull: {path: spec.field}` - Check field is null/absent
- `hasDocuments: {count: N}` - Check number of documents rendered

## CI Integration

Add to GitHub Actions workflow:

```yaml
- name: Run Helm Unit Tests
  run: |
    helm plugin install https://github.com/helm-unittest/helm-unittest
    helm unittest charts
```
