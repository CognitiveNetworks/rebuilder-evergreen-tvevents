{{/*
METADATA HELPERS
Standard metadata structure for all Kubernetes resources.

Provides consistent metadata generation with:
- Environment-specific naming (name + suffix)
- Namespace assignment
- Annotations merging (config + custom)
- Labels merging (common + config + extra)

Used by: All Kubernetes resource templates (Deployment, Service, HTTPRoute, etc.)
*/}}

{{/*
metadata.standard
Generates complete metadata block for Kubernetes resources.

Input: Dict with keys:
  - name: Base resource name (e.g., "demo-app")
  - global: Root context (.)
  - config: Optional resource config from values (for annotations/labels)
  - annotations: Optional additional annotations dict
  - extraLabels: Optional additional labels dict

Output: YAML metadata block with:
  name: {name}-{suffix}
  namespace: {namespace}
  annotations: (merged from config.annotations + annotations)
  labels: (merged from common.labels + config.labels + extraLabels)

Example usage in templates:
  metadata:
    {{- include "metadata.standard" (dict "name" "demo-app" "config" .Values.deployment "global" .) | nindent 4 }}

Generated output:
  name: demo-app-dev-bryan-taylor
  namespace: demo-app-dev-bryan-taylor
  annotations:
    konghq.com/plugins: vpn-restriction
  labels:
    app: demo-app-dev-bryan-taylor
    version: "1.0.0"
    team: platform

Label Priority (later overrides earlier):
1. common.labels (app, version, team)
2. config.labels (from values)
3. extraLabels (template-specific)

Annotation Priority (later overrides earlier):
1. config.annotations (from values)
2. annotations (template-specific)
*/}}
{{- define "metadata.standard" -}}
{{- $suffix := include "resource.suffix" .global -}}
{{- $namespace := include "resource.namespace" .global -}}
name: {{ .name }}-{{ $suffix }}
namespace: {{ $namespace }}
annotations:
  {{- include "common.annotations" (dict "global" .global) | nindent 2 }}
  {{- if .config.annotations }}
  {{- toYaml .config.annotations | nindent 2 }}
  {{- end }}
  {{- if .annotations }}
  {{- toYaml .annotations | nindent 2 }}
  {{- end }}
labels:
  {{- include "common.labels" (dict "name" .name "global" .global) | nindent 2 }}
  {{- if .config.labels }}
  {{- toYaml .config.labels | nindent 2 }}
  {{- end }}
  {{- if .extraLabels }}
  {{- toYaml .extraLabels | nindent 2 }}
  {{- end }}
{{- end }}

