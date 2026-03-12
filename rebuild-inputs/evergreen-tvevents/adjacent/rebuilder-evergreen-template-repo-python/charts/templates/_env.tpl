{{/*
ENVIRONMENT HELPERS

Provides centralized access to environment-specific configuration.

CONFIGURATION PATTERN - Two-Level Structure:

1. BASE CONFIG (deployments):
   - Deployment structure (ports, resources, probes)
   - Base environment variables (shared across all environments)
   - Typically in values-deployments.yaml
   
2. ENVIRONMENT OVERRIDES (environmentConfig):
   - Environment-specific values (replicas, SHA refs)
   - Environment variable overrides
   - Autoscaling configuration
   - Typically in values-env-configs.yaml

PRECEDENCE RULES:

  Environment Variables:
    - Can be defined in BOTH deployments.{app}.env AND environmentConfig.{env}.deployments.{app}.env
    - Values are merged in _container.tpl with environmentConfig winning on conflicts
  
  Environment-Specific Fields:
    - replicas, sha_ref, scaledObject
    - Only defined in environmentConfig.{env}.deployments.{app}
    - Not defined in base deployments (validation enforces this)
  
  Structural Fields:
    - port, resources, probes, portName, serviceAccountName, podDisruption
    - Only defined in deployments.{app}
    - Not defined in environmentConfig (validation enforces this)

VALIDATION ENFORCEMENT:
  Configuration placement is technically enforced via _validate.tpl.
  Deployment fails immediately if fields are in wrong location with clear error message.
  See _validate.tpl for implementation.

ENVIRONMENT VARIABLE MERGE:
  The ONLY field that merges from both sources is environment variables.
  This merge happens in the container.env helper (_container.tpl).
  
  Merge Process:
    1. Start with base env vars from deployments.{name}.env
    2. Override with env vars from environmentConfig.{env}.deployments.{name}.env
    3. Result: Merged dict where environmentConfig values win on conflicts
  
  Example:
    deployments.demo-app.env:
      SERVICE_NAME: "demo-app"  # Kept (no override)
      LOG_LEVEL: "INFO"         # Overridden in prod
    
    environmentConfig.prod.deployments.demo-app.env:
      LOG_LEVEL: "WARN"         # Overrides base
    
    Result in prod:
      SERVICE_NAME: "demo-app"  # From base
      LOG_LEVEL: "WARN"         # From environmentConfig (override)
  
  See _container.tpl for merge implementation.

EXAMPLE CONFIGURATION:

  # values-deployments.yaml (Base structure)
  deployments:
    demo-app:
      port: 8000
      resources: {...}
      probes: {...}
      env:
        SERVICE_NAME: "demo-app"  # Base env var
        LOG_LEVEL: "INFO"         # Base env var (can be overridden)

  # values-env-configs.yaml (Environment overrides)
  environmentConfig:
    dev:
      logLevel: "DEBUG"           # Environment-level config
      deployments:
        demo-app:
          sha_ref: "latest"        # Dev-specific SHA
          replicas: 1              # Dev-specific replica count
          env:
            LOG_LEVEL: "DEBUG"     # Override base LOG_LEVEL
    prod:
      logLevel: "WARN"
      deployments:
        demo-app:
          sha_ref: "v1.2.3"        # Prod-specific SHA
          replicas: 100            # Prod-specific replica count
          env:
            LOG_LEVEL: "WARN"      # Override base LOG_LEVEL
          scaledObject:            # Prod-specific autoscaling
            enabled: true
            minReplicaCount: 50
            maxReplicaCount: 200

RESULT IN PROD:
  - port: 8000 (from deployments - no override)
  - resources: {...} (from deployments - no override)
  - replicas: 100 (from environmentConfig.prod only)
  - sha_ref: "v1.2.3" (from environmentConfig.prod only)
  - env.SERVICE_NAME: "demo-app" (from deployments base)
  - env.LOG_LEVEL: "WARN" (from environmentConfig.prod - overrides base)

HELM INCLUDE LIMITATION:
  Helm's `include` function always returns strings, not dicts.
  - Use these helpers with `include` to get scalar values (strings/numbers)
  - For dict/object access, access .Values directly in templates

Helper Categories:
  1. Generic Getters: env.get, env.deploymentGet (returns scalar values)
  2. Specific Getters: env.shaRef, env.replicas, env.logLevel (returns scalar values)
  3. Environment Type: env.type, env.name, env.isDev, env.isWorkloadOrPR (returns strings)

For dict/object access (e.g., scaledObject config), use this pattern in templates:
  {{- $env := .Values.ciOptions.environment | default "dev" -}}
  {{- $envConfig := index .Values.environmentConfig $env | default dict -}}
  {{- $deployments := $envConfig.deployments | default dict -}}
  {{- $deployConfig := index $deployments "demo-app" | default dict -}}
  {{- if $deployConfig.scaledObject.enabled }}
*/}}

{{/*
env.get - Generic getter for environment-level config values

Accesses top-level environmentConfig values (not deployment-specific).
These are environment-wide settings that apply to all deployments.

Source: environmentConfig[env][key]

Input: dict with "key" (config key), "default" (fallback), "global" (context)
Returns: Scalar value (string/number) from environmentConfig[env][key] or default

Common Use Cases:
  - logLevel: Environment-wide log level
  - karpenterNodeRole: IAM role for Karpenter nodes
  - region: AWS region for environment

Example:
  {{- include "env.get" (dict "key" "logLevel" "default" "INFO" "global" $) -}}
  → "DEBUG" (in dev with logLevel: "DEBUG" configured)
  → "INFO" (if logLevel not configured, uses default)
  
  {{- include "env.get" (dict "key" "karpenterNodeRole" "default" "" "global" $) -}}
  → "arn:aws:iam::123:role/dev-role" (configured role ARN)
  → "" (if karpenterNodeRole not configured)
*/}}
{{- define "env.get" -}}
{{- $env := (.global.Values.ciOptions).environment | default .global.Values.environment | default "dev" -}}
{{- $envConfig := index .global.Values.environmentConfig $env | default dict -}}
{{- index $envConfig .key | default .default -}}
{{- end }}

{{/*
env.deploymentGet - Generic getter for deployment-specific config values

Accesses deployment-specific values from environmentConfig.
These values are ONLY defined in environmentConfig, NOT in base deployments config.

Source: environmentConfig[env].deployments[deployment][key]
Precedence: environmentConfig ONLY (no base in deployments)

Input: dict with "deployment" (name), "key" (config key), "default" (fallback), "global" (context)
Returns: Scalar value (string/number) from environmentConfig[env].deployments[deployment][key] or default

Common Use Cases:
  - replicas: Number of pod replicas (environment-specific)
  - sha_ref: Git SHA for container image (changes per deployment)
  - Environment-specific resource overrides

NOTE: This does NOT access base deployments config. For values like port, resources, probes,
      access .Values.deployments directly in templates.

Example:
  {{- include "env.deploymentGet" (dict "deployment" "demo-app" "key" "replicas" "default" 1 "global" $) -}}
  → 100 (in prod with replicas: 100 configured in environmentConfig.prod.deployments.demo-app)
  → 1 (if replicas not configured in environmentConfig, uses default)
  
  {{- include "env.deploymentGet" (dict "deployment" "demo-app" "key" "sha_ref" "default" "latest" "global" $) -}}
  → "abc123" (configured SHA in environmentConfig)
  → "latest" (if sha_ref not configured in environmentConfig)
*/}}
{{- define "env.deploymentGet" -}}
{{- $env := (.global.Values.ciOptions).environment | default .global.Values.environment | default "dev" -}}
{{- $envConfig := index .global.Values.environmentConfig $env | default dict -}}
{{- $deployments := $envConfig.deployments | default dict -}}
{{- $deployConfig := index $deployments .deployment | default dict -}}
{{- index $deployConfig .key | default .default -}}
{{- end }}

{{/*
=== SPECIFIC VALUE GETTERS ===
Convenience helpers for commonly accessed config values.
Use these with `include` - they return scalar values (strings/numbers).
*/}}

{{/*
env.logLevel - Returns log level for current environment

Input: Global context (.)
Returns: String log level ("DEBUG", "INFO", "WARN", etc.)

Example:
  LOG_LEVEL: {{ include "env.logLevel" . }}
  → "DEBUG" in dev, "INFO" if not configured
*/}}
{{- define "env.logLevel" -}}
{{- include "env.get" (dict "key" "logLevel" "default" "INFO" "global" .) -}}
{{- end }}


{{/*
env.shaRef - Returns git SHA reference for deployment image

Source: environmentConfig[env].deployments[deployment].sha_ref
Precedence: environmentConfig ONLY (not in base deployments)

Input: dict with "deployment" (name, defaults to "demo-app") and "global" (context)
Returns: String git SHA (e.g., "abc123def456") or "latest" if not configured

Used for: Building container image tags that change per environment/deployment

Example:
  {{- $shaRef := include "env.shaRef" (dict "deployment" $deploymentName "global" $) -}}
  image: myrepo:{{ $shaRef }}
  → image: myrepo:abc123def456 (in prod with sha_ref: "abc123def456")
  → image: myrepo:latest (if sha_ref not configured)
*/}}
{{- define "env.shaRef" -}}
{{- include "env.deploymentGet" (dict "deployment" (.deployment | default "demo-app") "key" "sha_ref" "default" "latest" "global" .global) -}}
{{- end }}

{{/*
env.replicas - Returns replica count for deployment

Source: environmentConfig[env].deployments[deployment].replicas
Precedence: environmentConfig ONLY (not in base deployments)

Input: dict with "deployment" (name, defaults to "demo-app") and "global" (context)
Returns: Integer replica count from environmentConfig or 1 if not configured

Used for: Setting initial replica count (before autoscaling takes over)

NOTE: If scaledObject is enabled, KEDA will manage replicas dynamically.
      This value sets the initial state only.

Example:
  replicas: {{ include "env.replicas" (dict "global" $ "deployment" $deploymentName) }}
  → replicas: 100 (in prod with replicas: 100 in environmentConfig.prod.deployments.demo-app)
  → replicas: 1 (if replicas not configured in environmentConfig, uses default)
*/}}
{{- define "env.replicas" -}}
{{- include "env.deploymentGet" (dict "deployment" (.deployment | default "demo-app") "key" "replicas" "default" 1 "global" .global) -}}
{{- end }}


{{/*
=== ENVIRONMENT TYPE HELPERS ===
Determine deployment environment type and provide boolean checks.
*/}}

{{/*
env.type - Returns environment type based on ciOptions

Input: Global context (.)
Returns: String "pr_env", "workload_env", or "dev"

Logic:
  - "pr_env": PR deployments (ciOptions.pr_number is set)
  - "workload_env": CI/CD managed environments (ciOptions.workload_env is true)
  - "dev": Skaffold/local development (default)

Example:
  {{- $envType := include "env.type" . -}}
  {{- if eq $envType "pr_env" }}
  → true for PR environments
*/}}
{{- define "env.type" -}}
{{- if and .Values.ciOptions (hasKey .Values.ciOptions "pr_number") .Values.ciOptions.pr_number -}}
pr_env
{{- else if and .Values.ciOptions (hasKey .Values.ciOptions "workload_env") .Values.ciOptions.workload_env -}}
workload_env
{{- else -}}
dev
{{- end -}}
{{- end }}

{{/*
env.name - Returns environment name

Input: Global context (.)
Returns: String environment name ("dev", "qa", "staging", "prod") or "dev" if not configured

Used for:
  - Looking up environmentConfig[env]
  - Building resource names/namespaces
  - Selecting appropriate secrets

Example:
  key: {{ include "env.name" $ }}/secrets/app
  → key: dev/secrets/app
*/}}
{{- define "env.name" -}}
{{ (.Values.ciOptions).environment | default "dev" }}
{{- end }}

{{/*
env.isDev - Returns "true" if dev environment, "false" otherwise

Input: Global context (.)
Returns: String "true" or "false" (use with string comparison)

Example:
  {{- $isDev := include "env.isDev" .global -}}
  {{- if eq $isDev "true" }}
    # Dev-only config
  {{- end }}
  → true when env.type returns "dev"
*/}}
{{- define "env.isDev" -}}
{{- $envType := include "env.type" . -}}
{{- eq $envType "dev" -}}
{{- end }}

{{/*
env.isWorkloadOrPR - Returns "true" if workload_env or pr_env, "false" otherwise

Input: Global context (.)
Returns: String "true" or "false" (use with string comparison)

Use this for:
  - Conditional resources that only exist in CI/CD managed environments
  - Git clone init containers (not needed in dev with Skaffold file sync)
  - Production-specific configurations

Example:
  {{- $isManaged := include "env.isWorkloadOrPR" . -}}
  {{- if eq $isManaged "true" }}
    # CI/CD only resources
  {{- end }}
  → true when env.type returns "workload_env" or "pr_env"
*/}}
{{- define "env.isWorkloadOrPR" -}}
{{- $envType := include "env.type" . -}}
{{- or (eq $envType "workload_env") (eq $envType "pr_env") -}}
{{- end }}

{{/*
env.ecrEnv - Returns base environment name for ECR repository

Input: Global context (.)
Returns: String environment name for ECR repo ("dev", "qa", "staging", "prod")

Logic:
  - PR environments → "dev" (PRs use dev ECR repos)
  - All other environments → actual environment name

Used for: Building ECR repository names that don't have PR-specific repos

Example:
  {{- $ecrEnv := include "env.ecrEnv" . -}}
  image: account.dkr.ecr.region.amazonaws.com/inscape-infra-{{ $ecrEnv }}-app
  → inscape-infra-dev-app (for PR environments)
  → inscape-infra-prod-app (for prod environment)
*/}}
{{- define "env.ecrEnv" -}}
{{- $envType := include "env.type" . -}}
{{- if eq $envType "pr_env" -}}
dev
{{- else -}}
{{- include "env.name" . -}}
{{- end -}}
{{- end }}
