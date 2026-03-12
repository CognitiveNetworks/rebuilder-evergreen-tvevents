---
marp: true
theme: corporate-clean
paginate: true
---

## The Power Trio: Skaffold + PR Environments + Dapr

<div class="columns">
<div>

### 🚀 Skaffold: Local Dev Automation
```bash
skaffold dev --profile mvp
```
- Watches code → rebuilds → deploys
- 5-second feedback loop
- No manual Docker/ECR/Helm

</div>
<div>

### 🌐 PR Environments: Ephemeral Preview
```yaml
generators:
- pullRequest:
    github: {owner: org, repo: app}
template:
  name: 'app-pr-{{number}}'
  namespace: 'app-pr-{{number}}'
```
- Isolated K8s namespace per PR
- URL: `app-pr-123.evergreen.cognet.tv`
- Includes Locust load testing
- Auto-destroys on merge

</div>
<div>

### ☁️ Dapr: Multi-Cloud Portability
```yaml
daprComponents:
  app:
    components:
      - name: "storage"
        aws: {type: "bindings.aws.s3"}
        gcp: {type: "bindings.gcp.bucket"}
```
```python
requests.post(
    f"{DAPR_URL}/v1.0/bindings/storage",
    json={"operation": "create", "data": file}
)
```
- Same code, any cloud
- Config-driven switching
- No vendor lock-in

</div>
</div>

**Result:** Local dev in 5 sec → PR preview in 5 min → Multi-cloud production
