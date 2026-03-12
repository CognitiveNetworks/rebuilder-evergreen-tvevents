{{/*
HTTPROUTE HELPERS
HTTPRoute specifications and hostname resolution

HTTPRoute Hostname Patterns:
- Workload (dev/qa/staging/prod): Uses explicit workloadHostnames from values or falls back to {hostPrefix}-{env}.{baseDomain}
- PR environments: {hostPrefix}-pr-{number}.dev.{baseDomain}
- Loop dev (local): {hash}.{appName}.loop.dev.{baseDomain}

Example hostnames:
- Workload dev: demo-app-dev.evergreen.cognet.tv
- PR #123: demo-app-pr-123.dev.evergreen.cognet.tv
- Loop dev: 5f8d73a6.demo-app.loop.dev.evergreen.cognet.tv
*/}}

{{- define "httproute.spec" -}}
{{- /* Initialize hostnames variable */ -}}
{{- $hostnames := list -}}
{{- /* Check if explicit hostnames are provided in route config */ -}}
{{- if .route.hostnames -}}
  {{- /* Use explicit hostnames directly */ -}}
  {{- $hostnames = .route.hostnames -}}
{{- else -}}
  {{- /* Generate hostname(s) for this route */ -}}
  {{- $hostname := include "resource.hostname" (dict "baseDomain" .baseDomain "workloadHostnames" .route.workloadHostnames "global" .global) -}}
  {{- if contains "\n" $hostname -}}
    {{- /* Multiple hostnames returned as YAML list */ -}}
    {{- $hostnames = $hostname | fromYaml -}}
  {{- else -}}
    {{- /* Single hostname returned as string */ -}}
    {{- $hostnames = list $hostname -}}
  {{- end -}}
{{- end -}}
{{- /* Deep copy route config to avoid mutating original */ -}}
{{- $routeConfig := deepCopy .route -}}
{{- $_ := set $routeConfig "hostnames" $hostnames -}}
{{- /* Update backend service names with environment suffix */ -}}
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

