{{/*
POD HELPERS
Helpers for pod template configuration (annotations, labels, etc.)
*/}}

{{/*
Generate pod template annotations from multiple sources
Input: dict with "name", "deployment", "global" keys
Returns: merged annotations from:
  1. deployment.podAnnotations (explicit pod-level annotations)
  2. daprComponents[name].annotations (Dapr sidecar config)
  3. Future: Add more sources as needed (Prometheus, Linkerd, etc.)
*/}}
{{- define "pod.annotations" -}}
{{- $annotations := dict -}}

{{/* 1. Explicit pod annotations */}}
{{- if .deployment.podAnnotations -}}
{{- $annotations = merge $annotations .deployment.podAnnotations -}}
{{- end -}}

{{/* 2. Dapr annotations */}}
{{- if hasKey .global.Values "daprComponents" -}}
{{- $daprConfig := index .global.Values.daprComponents .name -}}
{{- if and $daprConfig $daprConfig.enabled $daprConfig.annotations -}}
{{- $annotations = merge $annotations $daprConfig.annotations -}}
{{- end -}}
{{- end -}}

{{/* Output */}}
{{- if $annotations -}}
{{- toYaml $annotations -}}
{{- end -}}
{{- end }}

