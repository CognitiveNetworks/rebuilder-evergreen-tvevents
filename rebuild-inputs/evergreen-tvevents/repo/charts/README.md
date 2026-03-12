# TV Events Helm Chart

Chart to deploy tvevents.

## Description
Helm chart for deploying a tvevents application in Kubernetes environments.

## Configuration

The following deployment modes are supported:

### Cluster Deployment
For production/staging environments with:
- External secrets integration
- Auto-scaling via KEDA
- Zone-aware pod scheduling
- Monitoring and observability

### Local Development
Development environment with:
- Local secrets
- Single instance deployment
- Direct database access

## Values

Key configuration options values.yaml:

```yaml
# Deployment Mode
localDev:
  enabled: false # Set to true for local development

# Application
replicaCount: 3
cpuScalingThreshold: 50
minReplicaCount: 12

# Service Configuration  
service:
  type: ClusterIP
  port: 80
  targetPort: 8000

# Secrets Management
secretKey: dev/tvevents/tvcdb-development.cognet.tv
secretStore: tve-secret-store
secretName: tve-secret
```
