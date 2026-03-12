{{/*
CONTAINER HELPERS
Container environment variable configuration
*/}}

{{/*
container.env - Builds environment variable list for container

This is the ONLY place where base deployments config and environmentConfig are merged.
All other fields use single-source precedence (see _env.tpl for details).

Merges environment variables from multiple sources:
1. Base env vars from deployments.{name}.env (values-deployments.yaml)
2. Environment-specific overrides from environmentConfig.{env}.deployments.{name}.env (values-env-configs.yaml)
3. Secret/ConfigMap references from envFrom

Input: Dict with keys:
  - config: Deployment configuration from .Values.deployments.{name}
  - name: Deployment name (e.g., "demo-app")
  - global: Root context

Output: YAML array of env vars

Precedence (later overrides earlier):
  1. deployments.{name}.env (base values - shared across all environments)
  2. environmentConfig.{env}.deployments.{name}.env (environment overrides)

Merge Logic:
  - Creates a dict with all base env vars
  - Overlays environment-specific env vars (overwriting on key conflicts)
  - Environment overrides win on conflicts

Example:
  # values-deployments.yaml
  deployments:
    demo-app:
      env:
        SERVICE_NAME: "demo-app"  # Shared across all envs
        LOG_LEVEL: "INFO"         # Base default
        AWS_REGION: "us-east-1"   # Shared across all envs
  
  # values-env-configs.yaml
  environmentConfig:
    dev:
      deployments:
        demo-app:
          env:
            LOG_LEVEL: "DEBUG"     # Override for dev
    prod:
      deployments:
        demo-app:
          env:
            LOG_LEVEL: "WARN"      # Override for prod
  
  Result in dev:
    SERVICE_NAME: "demo-app"  # From base (no override)
    LOG_LEVEL: "DEBUG"        # From environmentConfig.dev (override)
    AWS_REGION: "us-east-1"   # From base (no override)
  
  Result in prod:
    SERVICE_NAME: "demo-app"  # From base (no override)
    LOG_LEVEL: "WARN"         # From environmentConfig.prod (override)
    AWS_REGION: "us-east-1"   # From base (no override)
*/}}
{{- define "container.env" -}}
{{- $otelServiceName := include "resource.serviceName" (dict "deployment" .config "global" .global) -}}

{{- /* STEP 1: Get environment-specific deployment config from environmentConfig */ -}}
{{- $env := (.global.Values.ciOptions).environment | default "dev" -}}
{{- $envConfig := index .global.Values.environmentConfig $env | default dict -}}
{{- $deployments := $envConfig.deployments | default dict -}}
{{- $deploymentEnvConfig := index $deployments .name | default dict -}}

{{- /* STEP 2: Merge base and environment-specific env vars */ -}}
{{- /* This is the ONLY merge in the entire chart - all other fields use single-source */ -}}
{{- $merged := dict -}}

{{- /* Add base env vars from deployments.{name}.env */ -}}
{{- range $key, $value := .config.env }}
{{- $_ := set $merged $key $value -}}
{{- end }}

{{- /* Override with environment-specific vars from environmentConfig.{env}.deployments.{name}.env */ -}}
{{- if $deploymentEnvConfig.env }}
{{- range $key, $value := $deploymentEnvConfig.env }}
{{- $_ := set $merged $key $value -}}  {{- /* This overwrites base values on conflict */ -}}
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

