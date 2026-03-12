{{/*
CONTAINER HELPERS
Container environment variable configuration
*/}}

{{/*
container.env - Builds environment variable list for container

Merges environment variables from multiple sources:
1. Base env vars from deployments.{name}.env (values.yaml)
2. Environment-specific overrides from environmentConfig.{env}.deployments.{name}.env

Precedence (later overrides earlier):
  1. deployments.{name}.env (base values - shared across all environments)
  2. environmentConfig.{env}.deployments.{name}.env (environment overrides)
*/}}
{{- define "container.env" -}}
{{- $otelServiceName := include "resource.serviceName" (dict "deployment" .config "global" .global) -}}

{{- /* STEP 1: Get environment-specific deployment config from environmentConfig */ -}}
{{- $env := (.global.Values.ciOptions).environment | default "dev" -}}
{{- $envConfig := index .global.Values.environmentConfig $env | default dict -}}
{{- $deployments := $envConfig.deployments | default dict -}}
{{- $deploymentEnvConfig := index $deployments .name | default dict -}}

{{- /* STEP 2: Merge base and environment-specific env vars */ -}}
{{- $merged := dict -}}

{{- /* Add base env vars from deployments.{name}.env */ -}}
{{- range $key, $value := .config.env }}
{{- $_ := set $merged $key $value -}}
{{- end }}

{{- /* Override with environment-specific vars from environmentConfig.{env}.deployments.{name}.env */ -}}
{{- if $deploymentEnvConfig.env }}
{{- range $key, $value := $deploymentEnvConfig.env }}
{{- $_ := set $merged $key $value -}}
{{- end }}
{{- end }}

{{- /* STEP 3: Output merged env vars as YAML */ -}}
{{- range $key, $value := $merged }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}

{{- /* STEP 4: Add secret/configmap references (not merged, just appended) */ -}}
{{- if .config.envFrom }}
{{- range .config.envFrom }}
{{- if .secretRef }}
- name: {{ .name }}
  valueFrom:
    secretKeyRef:
      name: {{ .secretRef.name }}
      key: {{ .secretRef.key }}
{{- else if .configMapRef }}
- name: {{ .name }}
  valueFrom:
    configMapKeyRef:
      name: {{ .configMapRef.name }}
      key: {{ .configMapRef.key }}
{{- end }}
{{- end }}
{{- end }}
{{- end }}

