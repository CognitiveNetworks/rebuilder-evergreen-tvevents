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
  - name: Base resource name (e.g., "evergreen-tvevents")
  - global: Root context (.)
  - config: Optional resource config from values (for annotations/labels)
  - annotations: Optional additional annotations dict
  - extraLabels: Optional additional labels dict

Output: YAML metadata block with:
  name: {name}-{suffix}
  namespace: {namespace}
  annotations: (merged from config.annotations + annotations)
  labels: (merged from common.labels + config.labels + extraLabels)
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

