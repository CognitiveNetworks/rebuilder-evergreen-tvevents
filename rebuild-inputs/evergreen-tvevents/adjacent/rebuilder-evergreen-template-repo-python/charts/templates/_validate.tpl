{{/*
VALIDATION HELPERS

Enforces configuration placement rules to prevent misconfigurations.
These validators fail the Helm deployment if fields are in the wrong location.

VALIDATION RULES:
  - Structure fields (port, resources, probes) MUST be in deployments
  - Environment fields (replicas, sha_ref, scaledObject) MUST be in environmentConfig
  - Environment variables can be in BOTH (they merge)

WHEN VALIDATION RUNS:
  - At helm template time
  - At helm install/upgrade time
  - Before any resources are created

FAILURE BEHAVIOR:
  - Helm deployment fails immediately with clear error message
  - No resources are created
  - Error message shows exactly what's wrong and where it should go
*/}}

{{/*
validate.configPlacement - Validates fields are in correct locations

Enforces the single-source design pattern by failing deployment if:
  - Environment-specific fields (replicas, sha_ref, scaledObject) are in base deployments
  - Structure fields (port, resources, probes) are in environmentConfig

Input: Root context (.)
Output: Empty string on success, fails deployment on validation error

Usage: Call at the top of Deployment.yaml before rendering resources
  {{- include "validate.configPlacement" . }}
*/}}
{{- define "validate.configPlacement" -}}
{{- /* Validate base deployments - should NOT have environment-specific fields */ -}}
{{- range $deploymentName, $deployment := .Values.deployments }}
  {{- if hasKey $deployment "replicas" }}
    {{- fail (printf "❌ CONFIG ERROR: 'replicas' found in deployments.{app-name}\n   ➜ MUST be in: environmentConfig.{env}.deployments.{app-name}.replicas\n   ➜ REASON: replicas are environment-specific (dev=1, prod=100)") }}
  {{- end }}
  {{- if hasKey $deployment "sha_ref" }}
    {{- fail (printf "❌ CONFIG ERROR: 'sha_ref' found in deployments.{app-name}\n   ➜ MUST be in: environmentConfig.{env}.deployments.{app-name}.sha_ref\n   ➜ REASON: sha_ref changes per deployment/environment") }}
  {{- end }}
  {{- if hasKey $deployment "scaledObject" }}
    {{- fail (printf "❌ CONFIG ERROR: 'scaledObject' found in deployments.{app-name}\n   ➜ MUST be in: environmentConfig.{env}.deployments.{app-name}.scaledObject\n   ➜ REASON: autoscaling config is environment-specific") }}
  {{- end }}
{{- end }}

{{- /* Validate environmentConfig - should NOT have structure fields */ -}}
{{- range $envName, $envConfig := .Values.environmentConfig }}
  {{- if $envConfig.deployments }}
    {{- range $deploymentName, $deployConfig := $envConfig.deployments }}
      {{- if hasKey $deployConfig "port" }}
        {{- fail (printf "❌ CONFIG ERROR: 'port' found in environmentConfig.{env}.deployments.{app-name}\n   ➜ MUST be in: deployments.{app-name}.port\n   ➜ REASON: port is structural config (doesn't change per environment)") }}
      {{- end }}
      {{- if hasKey $deployConfig "resources" }}
        {{- fail (printf "❌ CONFIG ERROR: 'resources' found in environmentConfig.{env}.deployments.{app-name}\n   ➜ MUST be in: deployments.{app-name}.resources\n   ➜ REASON: resources are structural config (doesn't change per environment)") }}
      {{- end }}
      {{- if hasKey $deployConfig "probes" }}
        {{- fail (printf "❌ CONFIG ERROR: 'probes' found in environmentConfig.{env}.deployments.{app-name}\n   ➜ MUST be in: deployments.{app-name}.probes\n   ➜ REASON: probes are structural config (doesn't change per environment)") }}
      {{- end }}
      {{- if hasKey $deployConfig "portName" }}
        {{- fail (printf "❌ CONFIG ERROR: 'portName' found in environmentConfig.{env}.deployments.{app-name}\n   ➜ MUST be in: deployments.{app-name}.portName\n   ➜ REASON: portName is structural config (doesn't change per environment)") }}
      {{- end }}
      {{- if hasKey $deployConfig "serviceAccountName" }}
        {{- fail (printf "❌ CONFIG ERROR: 'serviceAccountName' found in environmentConfig.{env}.deployments.{app-name}\n   ➜ MUST be in: deployments.{app-name}.serviceAccountName\n   ➜ REASON: serviceAccountName is structural config (doesn't change per environment)") }}
      {{- end }}
      {{- if hasKey $deployConfig "podDisruption" }}
        {{- fail (printf "❌ CONFIG ERROR: 'podDisruption' found in environmentConfig.{env}.deployments.{app-name}\n   ➜ MUST be in: deployments.{app-name}.podDisruption\n   ➜ REASON: podDisruption is structural config (doesn't change per environment)") }}
      {{- end }}
    {{- end }}
  {{- end }}
{{- end }}
{{- end }}
