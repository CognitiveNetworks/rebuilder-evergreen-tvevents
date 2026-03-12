{{/*
HTTPROUTE HELPERS
HTTPRoute specifications and hostname resolution
*/}}

{{- define "httproute.spec" -}}
{{- $hostnames := list -}}
{{- if .route.hostnames -}}
  {{- $hostnames = .route.hostnames -}}
{{- else -}}
  {{- $hostname := include "resource.hostname" (dict "baseDomain" .baseDomain "workloadHostnames" .route.workloadHostnames "global" .global) -}}
  {{- if contains "\n" $hostname -}}
    {{- $hostnames = $hostname | fromYaml -}}
  {{- else -}}
    {{- $hostnames = list $hostname -}}
  {{- end -}}
{{- end -}}
{{- $routeConfig := deepCopy .route -}}
{{- $_ := set $routeConfig "hostnames" $hostnames -}}
{{- $suffix := include "resource.suffix" .global -}}
{{- range $ruleIdx, $rule := $routeConfig.rules -}}
  {{- if $rule.backendRefs -}}
    {{- $updatedBackends := list -}}
    {{- range $backend := $rule.backendRefs -}}
      {{- $fullServiceName := printf "%s-%s" $backend.name $suffix -}}
      {{- $updatedBackend := dict "group" (default "" $backend.group) "name" $fullServiceName "kind" (default "Service" $backend.kind) "port" $backend.port "weight" (default 1 $backend.weight) -}}
      {{- $updatedBackends = append $updatedBackends $updatedBackend -}}
    {{- end -}}
    {{- $_ := set (index $routeConfig.rules $ruleIdx) "backendRefs" $updatedBackends -}}
  {{- end -}}
{{- end -}}
hostnames:
{{- toYaml $routeConfig.hostnames | nindent 2 }}
parentRefs:
{{- toYaml $routeConfig.parentRefs | nindent 2 }}
rules:
{{- toYaml $routeConfig.rules | nindent 2 }}
{{- end }}

{{- define "httproute.hostnames" -}}
{{- toYaml .hostnames -}}
{{- end }}

{{- define "httproute.parentRefs" -}}
{{- toYaml .parentRefs -}}
{{- end }}

{{- define "httproute.rules" -}}
{{- toYaml .rules -}}
{{- end }}

