{{/*
RESOURCE HELPERS
Resource naming, namespaces, hostnames, and service names
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
*/}}
{{- define "resource.hostname" -}}
{{- $envType := include "env.type" .global -}}
{{- $isDev := include "env.isDev" .global -}}
{{- if eq $envType "workload_env" -}}
  {{- $env := .global.Values.ciOptions.environment | default "dev" -}}
  {{- if and .workloadHostnames (hasKey .workloadHostnames $env) -}}
    {{- $envHostnames := index .workloadHostnames $env -}}
    {{- if kindIs "slice" $envHostnames -}}
{{- toYaml $envHostnames -}}
    {{- else -}}
{{ $envHostnames }}
    {{- end -}}
  {{- else -}}
{{ .global.Values.global.hostPrefix }}-{{ $env }}.{{ .baseDomain }}
  {{- end -}}
{{- else if eq $envType "pr_env" -}}
{{ .global.Values.global.hostPrefix }}-pr-{{ .global.Values.ciOptions.pr_number | default "0" }}.dev.{{ .baseDomain }}
{{- else -}}
  {{- $devSubdomain := (.global.Values.ciOptions).devSubdomain | default "loop" -}}
{{ ((.global.Values.ciOptions).user | default "local") | sha256sum | trunc 8 }}.{{ .global.Values.global.appName }}.{{ $devSubdomain }}.dev.{{ .baseDomain }}
{{- end -}}
{{- end }}

{{/*
resource.serviceName
Generates full service name with environment suffix.
*/}}
{{- define "resource.serviceName" -}}
{{ .global.Values.global.serviceName }}-{{ include "resource.suffix" .global }}
{{- end }}

