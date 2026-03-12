{{/*
COMMON HELPERS
Organizational standards applied to all resources

These helpers generate standard labels and annotations that must be present
on all Kubernetes resources to meet organizational compliance requirements.

Used by: metadata.standard helper in _metadata.tpl
*/}}

{{/*
common.labels
Generates standard labels for all resources.

Input: Dict with keys:
  - name: Resource name (e.g., "evergreen-tvevents")
  - global: Root context

Output: YAML labels block

Labels (Required):
- app: {name}-{suffix} (for selector matching)
- environment: Environment name (dev/qa/staging/prod)
- team: Team with vested interest
- function: Business function/operation group
- service: Distinct software component
- cost-unit: Demand driver for cloud spend

Labels (Optional):
- version: Application version

Configuration: global.labels in values.yaml

Used by: All Kubernetes resources via metadata.standard
*/}}
{{- define "common.labels" -}}
{{- $suffix := include "resource.suffix" .global -}}
app: {{ .name }}-{{ $suffix }}
{{- if .global.Values.global.labels.environment }}
environment: {{ .global.Values.global.labels.environment }}
{{- end }}
{{- if .global.Values.global.labels.team }}
team: {{ .global.Values.global.labels.team }}
{{- end }}
{{- if .global.Values.global.labels.function }}
function: {{ .global.Values.global.labels.function }}
{{- end }}
{{- if .global.Values.global.labels.service }}
service: {{ .global.Values.global.labels.service }}
{{- end }}
{{- if index .global.Values.global.labels "cost-unit" }}
"cost-unit": {{ index .global.Values.global.labels "cost-unit" | quote }}
{{- end }}
{{- if .global.Values.global.labels.version }}
version: {{ .global.Values.global.labels.version }}
{{- end }}
{{- end }}

{{/*
common.annotations
Generates standard annotations for all resources.

Input: Dict with keys:
  - global: Root context

Output: YAML annotations block

Annotations (Required):
- repo: GitHub org/repo
- created-by: Resource creation method

Annotations (Optional):
- cost-center: WorkDay cost center (numeric as string)

Configuration: global.annotations in values.yaml

Used by: All Kubernetes resources via metadata.standard
*/}}
{{- define "common.annotations" -}}
{{- if .global.Values.global.annotations.repo }}
repo: {{ .global.Values.global.annotations.repo }}
{{- end }}
{{- if index .global.Values.global.annotations "created-by" }}
created-by: {{ index .global.Values.global.annotations "created-by" }}
{{- end }}
{{- if index .global.Values.global.annotations "cost-center" }}
cost-center: {{ index .global.Values.global.annotations "cost-center" | quote }}
{{- end }}
{{- end }}

