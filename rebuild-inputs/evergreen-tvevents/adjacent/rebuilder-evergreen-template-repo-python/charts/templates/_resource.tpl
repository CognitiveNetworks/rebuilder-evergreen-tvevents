{{/*
RESOURCE HELPERS
Resource naming, namespaces, hostnames, and service names

These helpers generate environment-specific resource identifiers used throughout
the Helm chart to ensure proper isolation and routing across different deployment
environments (workload, PR, dev).

Hostname Patterns:
- Workload: {hostPrefix}-{env}.{baseDomain} or explicit workloadHostnames
  Example: demo-app-dev.evergreen.cognet.tv
- PR: {hostPrefix}-pr-{number}.dev.{baseDomain}
  Example: demo-app-pr-123.dev.evergreen.cognet.tv
- Dev: {hash}.{appName}.{devSubdomain}.dev.{baseDomain}
  Example: 5f8d73a6.demo-app.loop.dev.evergreen.cognet.tv
  - devSubdomain defaults to "loop" but can be overridden via ciOptions.devSubdomain
  - hash is first 8 chars of SHA256 of username for uniqueness

Resource Suffix Patterns:
- PR: pr-{number}
  Example: pr-123
- Workload: {environment}-{region}
  Example: dev-us-east-1
- Dev: dev-{user}
  Example: dev-bryan-taylor

Namespace Patterns:
- Uses Release.Namespace if set, otherwise: {appName}-{suffix}
  Example: demo-app-dev-bryan-taylor

Service Name Patterns:
- {serviceName}-{suffix}
  Example: demo-app-service-dev-bryan-taylor
*/}}

{{/*
resource.suffix
Generates environment-specific suffix for resource names.

Input: Root context (.)
Output: String suffix based on environment type

Used by: Deployments, Services, ConfigMaps, Secrets, etc.
*/}}
{{- define "resource.suffix" -}}
{{- $envType := include "env.type" . -}}
{{- if eq $envType "pr_env" -}}
pr-{{ .Values.ciOptions.pr_number | default "0" }}
{{- else if eq $envType "workload_env" -}}
{{ .Values.ciOptions.environment | default "dev" }}-{{ .Values.ciOptions.cloud_region | default "us-east-1" }}
{{- else -}}
dev-{{ (.Values.ciOptions).user | default "local" }}
{{- end -}}
{{- end }}

{{/*
resource.namespace
Generates namespace for resources.

Input: Root context (.)
Output: Namespace string

Priority:
1. Release.Namespace if explicitly set (e.g., via helm --namespace)
2. Generated: {appName}-{suffix}

Used by: All Kubernetes resources
*/}}
{{- define "resource.namespace" -}}
{{- .Release.Namespace | default (printf "%s-%s" .Values.global.appName (include "resource.suffix" .)) -}}
{{- end }}

{{/*
resource.hostname
Generates hostname(s) for HTTPRoute ingress.

Input: Dict with keys:
  - baseDomain: Base domain (e.g., "evergreen.cognet.tv")
  - workloadHostnames: Optional map of env -> hostname(s) from values
  - global: Root context

Output: Single hostname string OR YAML list of hostnames

Logic:
1. Workload environments:
   - Check for explicit workloadHostnames[env] in values
   - Fall back to {hostPrefix}-{env}.{baseDomain}
2. PR environments:
   - Always {hostPrefix}-pr-{number}.dev.{baseDomain}
3. Dev environments:
   - {userHash}.{appName}.{devSubdomain}.dev.{baseDomain}
   - userHash = first 8 chars of SHA256(username)
   - devSubdomain defaults to "loop"

Used by: HTTPRoute template via httproute.spec
*/}}
{{- define "resource.hostname" -}}
{{- $envType := include "env.type" .global -}}
{{- $isDev := include "env.isDev" .global -}}
{{- if eq $envType "workload_env" -}}
  {{- $env := .global.Values.ciOptions.environment | default "dev" -}}
  {{- if and .workloadHostnames (hasKey .workloadHostnames $env) -}}
    {{- /* Use explicit workloadHostnames from values if defined */ -}}
    {{- $envHostnames := index .workloadHostnames $env -}}
    {{- if kindIs "slice" $envHostnames -}}
{{- toYaml $envHostnames -}}
    {{- else -}}
{{ $envHostnames }}
    {{- end -}}
  {{- else -}}
    {{- /* Fallback: {hostPrefix}-{env}.{baseDomain} */ -}}
{{ .global.Values.global.hostPrefix }}-{{ $env }}.{{ .baseDomain }}
  {{- end -}}
{{- else if eq $envType "pr_env" -}}
  {{- /* PR environments: {hostPrefix}-pr-{number}.dev.{baseDomain} */ -}}
{{ .global.Values.global.hostPrefix }}-pr-{{ .global.Values.ciOptions.pr_number | default "0" }}.dev.{{ .baseDomain }}
{{- else -}}
  {{- /* Dev environments: {hash}.{appName}.{devSubdomain}.dev.{baseDomain} */ -}}
  {{- $devSubdomain := (.global.Values.ciOptions).devSubdomain | default "loop" -}}
{{ ((.global.Values.ciOptions).user | default "local") | sha256sum | trunc 8 }}.{{ .global.Values.global.appName }}.{{ $devSubdomain }}.dev.{{ .baseDomain }}
{{- end -}}
{{- end }}

{{/*
resource.serviceName
Generates full service name with environment suffix.

Input: Dict with key "global" (root context)
Output: {serviceName}-{suffix}

Example: demo-app-service-dev-bryan-taylor

Used by: Service resources, HTTPRoute backend refs
*/}}
{{- define "resource.serviceName" -}}
{{ .global.Values.global.serviceName }}-{{ include "resource.suffix" .global }}
{{- end }}

