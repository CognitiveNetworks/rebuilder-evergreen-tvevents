{{/*
ENVIRONMENT HELPERS

Provides centralized access to environment-specific configuration.

CONFIGURATION PATTERN - Two-Level Structure:

1. BASE CONFIG (deployments):
   - Deployment structure (ports, resources, probes)
   - Base environment variables (shared across all environments)
   
2. ENVIRONMENT OVERRIDES (environmentConfig):
   - Environment-specific values (replicas, SHA refs)
   - Environment variable overrides
   - Autoscaling configuration

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
*/}}

{{/*
env.get - Generic getter for environment-level config values

Source: environmentConfig[env][key]

Input: dict with "key" (config key), "default" (fallback), "global" (context)
Returns: Scalar value (string/number) from environmentConfig[env][key] or default
*/}}
{{- define "env.get" -}}
{{- $env := (.global.Values.ciOptions).environment | default .global.Values.environment | default "dev" -}}
{{- $envConfig := index .global.Values.environmentConfig $env | default dict -}}
{{- index $envConfig .key | default .default -}}
{{- end }}

{{/*
env.deploymentGet - Generic getter for deployment-specific config values

Source: environmentConfig[env].deployments[deployment][key]

Input: dict with "deployment" (name), "key" (config key), "default" (fallback), "global" (context)
Returns: Scalar value from environmentConfig[env].deployments[deployment][key] or default
*/}}
{{- define "env.deploymentGet" -}}
{{- $env := (.global.Values.ciOptions).environment | default .global.Values.environment | default "dev" -}}
{{- $envConfig := index .global.Values.environmentConfig $env | default dict -}}
{{- $deployments := $envConfig.deployments | default dict -}}
{{- $deployConfig := index $deployments .deployment | default dict -}}
{{- index $deployConfig .key | default .default -}}
{{- end }}

{{/*
env.logLevel - Returns log level for current environment
*/}}
{{- define "env.logLevel" -}}
{{- include "env.get" (dict "key" "logLevel" "default" "INFO" "global" .) -}}
{{- end }}

{{/*
env.shaRef - Returns git SHA reference for deployment image
*/}}
{{- define "env.shaRef" -}}
{{- include "env.deploymentGet" (dict "deployment" (.deployment | default "evergreen-tvevents") "key" "sha_ref" "default" "latest" "global" .global) -}}
{{- end }}

{{/*
env.replicas - Returns replica count for deployment
*/}}
{{- define "env.replicas" -}}
{{- include "env.deploymentGet" (dict "deployment" (.deployment | default "evergreen-tvevents") "key" "replicas" "default" 1 "global" .global) -}}
{{- end }}

{{/*
=== ENVIRONMENT TYPE HELPERS ===
*/}}

{{/*
env.type - Returns environment type based on ciOptions
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
*/}}
{{- define "env.name" -}}
{{ (.Values.ciOptions).environment | default "dev" }}
{{- end }}

{{/*
env.isDev - Returns "true" if dev environment, "false" otherwise
*/}}
{{- define "env.isDev" -}}
{{- $envType := include "env.type" . -}}
{{- eq $envType "dev" -}}
{{- end }}

{{/*
env.isWorkloadOrPR - Returns "true" if workload_env or pr_env, "false" otherwise
*/}}
{{- define "env.isWorkloadOrPR" -}}
{{- $envType := include "env.type" . -}}
{{- or (eq $envType "workload_env") (eq $envType "pr_env") -}}
{{- end }}

{{/*
env.ecrEnv - Returns base environment name for ECR repository
*/}}
{{- define "env.ecrEnv" -}}
{{- $envType := include "env.type" . -}}
{{- if eq $envType "pr_env" -}}
dev
{{- else -}}
{{- include "env.name" . -}}
{{- end -}}
{{- end }}
