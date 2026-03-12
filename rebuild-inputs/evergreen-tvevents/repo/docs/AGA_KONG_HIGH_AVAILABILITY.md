# AWS Global Accelerator Kong High Availability

## Overview

This document describes the high availability setup for tvevents-k8s using AWS Global Accelerator (AGA) with Kong Gateway for traffic routing and health checking in PR environments.

## Architecture

```
AWS Global Accelerator → NLB → Kong Gateway → HTTPRoute → tvevents-k8s pods
                          ↑                      ↓
                    Health Check ←── Kong Plugin ←─┘
```

## Kong Upstream Policy

The `KongUpstreamPolicy` is applied only to PR environments and configures health checking for upstream services:

```yaml
apiVersion: configuration.konghq.com/v1beta1
kind: KongUpstreamPolicy
metadata:
  name: {{ .Release.Name }}
spec:
  healthchecks:
    threshold: 30  # Minimum percentage that must be `healthy`
    active:
      healthy:
        interval: 10
        successes: 3
      httpPath: /status
      timeout: 1
      type: http
      unhealthy:
        interval: 10
        httpFailures: 1
        timeouts: 1
    passive:
      unhealthy:
        httpFailures: 3
```

### Configuration Details

- **threshold**: 30% - Minimum percentage of healthy upstreams required
- **active.healthy.interval**: 10s - Health check frequency for healthy upstreams
- **active.healthy.successes**: 3 - Consecutive successes to mark as healthy
- **active.unhealthy.interval**: 10s - Health check frequency for unhealthy upstreams
- **active.unhealthy.httpFailures**: 1 - Single failure marks upstream as unhealthy
- **passive.unhealthy.httpFailures**: 3 - Failures during normal traffic to mark unhealthy

## Kong Health Check Plugin

The platform cluster provides a Kong plugin that translates health checks from the NLB to the HTTPRoute:

```yaml
apiVersion: configuration.konghq.com/v1
config:
  access:
  - |
    return function()
      kong.service.request.enable_buffering()
      kong.service.request.set_path("/upstreams/httproute.tvevents-pr-244.tve-us-east-1-pr-244-http-route.0/health")
      kong.service.request.set_query({balancer_health = 1})
      kong.service.request.set_scheme("http")
    end
  header_filter:
  - |
    return function()
      local body = kong.service.response.get_body()
      health = body.data["balancer_health"]
      if health == "UNHEALTHY" then
        kong.response.exit(503)
      else
        kong.response.exit(200)
      end
    end
kind: KongPlugin
metadata:
  annotations:
    kubectl.kubernetes.io/last-applied-configuration: |
      {"apiVersion":"configuration.konghq.com/v1","config":{"access":["return function()\n  kong.service.request.enable_buffering()\n  kong.service.request.set_path(\"/upstreams/httproute.tvevents-pr-244.tve-us-east-1-pr-244-http-route.0/health\")\n  kong.service.request.set_query({balancer_health = 1})\n  kong.service.request.set_scheme(\"http\")\nend\n"],"header_filter":["return function()\n  local body = kong.service.response.get_body()\n  health = body.data[\"balancer_health\"]\n  if health == \"UNHEALTHY\" then\n    kong.response.exit(503)\n  else\n    kong.response.exit(200)\n  end\nend\n"]},"kind":"KongPlugin","metadata":{"annotations":{},"name":"tvevents-health","namespace":"cluster-gateway"},"plugin":"pre-function"}
  creationTimestamp: "2025-10-23T16:35:02Z"
  generation: 4
  name: tvevents-health
  namespace: cluster-gateway
  resourceVersion: "207384199"
  uid: cce9defb-0299-4990-9ccf-99353365e0e2
plugin: pre-functio
    end
```

### Plugin Functionality

1. **Access Phase**: 
   - Rewrites incoming health check requests to Kong's upstream health endpoint
   - Sets the path to `/upstreams/{httproute-name}/health`
   - Adds `balancer_health=1` query parameter

2. **Header Filter Phase**:
   - Parses the upstream health response
   - Returns HTTP 503 if upstream is UNHEALTHY
   - Returns HTTP 200 if upstream is HEALTHY

## Health Check Flow

1. **NLB Health Check**: AWS NLB performs health checks on Kong Gateway endpoints
2. **Kong Plugin**: Intercepts health check requests and queries upstream health
3. **HTTPRoute Health**: Plugin checks the health of the HTTPRoute pointing to tvevents-k8s pods
4. **Response Translation**: Plugin translates Kong's upstream health status to HTTP status codes
5. **NLB Decision**: NLB routes traffic based on health check responses

## Benefits

- **Automatic Failover**: Unhealthy upstreams are automatically removed from load balancing
- **Fast Detection**: 10-second intervals with single failure detection
- **Graceful Recovery**: 3 consecutive successes required before marking healthy
- **Passive Monitoring**: Additional failure detection during normal traffic flow
- **AGA Integration**: Works seamlessly with AWS Global Accelerator for multi-region failover

## Usage

The Kong upstream policy is automatically applied to workload environments only (dev, qa, staging, prod) when `workload_env` is set passed from Argo to Helm. No manual configuration is required - the platform cluster provides the necessary Kong plugin configuration.

## Monitoring

Monitor health check status through:
- Kong Admin API: `/upstreams/{name}/health`
- AWS NLB Target Health in AWS Console
- New Relic APM for upstream health metrics
- Kubernetes events for pod health changes

## Testing Strategy
