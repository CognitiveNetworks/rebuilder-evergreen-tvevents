{{/*
Common labels
*/}}
{{- define "tvevents.labels" -}}
    {{- $labels := dict "app" .Release.Name "environment" .Values.environment }}

    {{- if .Values.labels }}
        {{- $_ := merge $labels .Values.labels }}
    {{- end }}

    {{- toYaml $labels }}
{{- end }}

{{/*
Common annotations
*/}}
{{- define "tvevents.annotations" -}}
    {{- with .Values.annotations }}
        {{- toYaml . }}
    {{- end }}
{{- end }}

{{/*
Define secrets manager path
*/}}
{{- define "secretPath" -}}
    {{- $env := include "environment" . }}
    {{- printf "/tvevents/%s/database" $env }}
{{- end }}

{{/*
Define secret name
*/}}
{{- define "secretName" -}}
    {{- $env := include "environment" . }}
    {{- printf "%s-%s-credentials" .Release.Name $env }}
{{- end }}

{{/*
Get log level by environment
*/}}
{{- define "tvevents.logLevel" -}}
    {{- if or (eq .Values.environment "dev") (eq .Values.environment "qa") (eq .Values.environment "staging") -}}
        {{ .Values.env.LOG_LEVEL }}
    {{- else if eq .Values.environment "prod" -}}
        INFO
    {{- else -}}
        {{ .Values.env.LOG_LEVEL | default "DEBUG" }}
    {{- end -}}
{{- end }}

{{/*
Get tvevents debug by environment
*/}}
{{- define "tvevents.tvEventsDebug" -}}
    {{- if or (eq .Values.environment "dev") (eq .Values.environment "qa") (eq .Values.environment "staging") -}}
        {{ .Values.env.TVEVENTS_DEBUG }}
    {{- else if eq .Values.environment "prod" -}}
        false
    {{- else -}}
        {{ .Values.env.TVEVENTS_DEBUG | default "true" }}
    {{- end -}}
{{- end }}

{{/*
Allow PR envs to spin up fewer pods by default.
*/}}
{{- define "tvevents.minReplicas" -}}
    {{ if not .Values.workload_env }}
        1
    {{- else if .Values.workload_env -}}
        {{ .Values.minReplicaCount }}
    {{- else -}}
        {{ .Values.minReplicaCount }}
    {{- end -}}
{{- end }}

{{/*
Make service name unique if its in a PR env
*/}}
{{- define "tvevents.serviceName" -}}
    {{ if not .Values.workload_env }}
        {{ .Values.env.SERVICE_NAME }}-pr-{{default 0 .Values.pr_number}}-{{ .Values.cloud_region }}
    {{- else if .Values.workload_env -}}
        {{ .Values.env.SERVICE_NAME }}-{{ .Values.environment }}-{{ .Values.cloud_region }}
    {{- else -}}
        {{ .Values.env.SERVICE_NAME }}-{{ .Values.environment }}-{{ .Values.cloud_region }}
    {{- end -}}
{{- end }}
