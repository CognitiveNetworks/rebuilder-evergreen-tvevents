# tvevents-k8s
Containerized tvevents application

## Setup
Required installations
- [Helm](https://helm.sh/docs/intro/quickstart/)
- [Minikube](https://minikube.sigs.k8s.io/docs/start/?arch=%2Fmacos%2Farm64%2Fstable%2Fbinary+download)
- [Docker](https://docs.docker.com/get-started/introduction/get-docker-desktop/)

### CVE tooling
- [Docker scount extension](https://scout.docker.com/)
- [vexctl](http://github.com/openvex/vexctl) `brew install vexctl`

Run the following CLI command to view existing CVEs inside the container that have a remediation path. We purposely
ignore vulnerabilities that are LOW or UNDEFINED severity ratings. We use
[VEX](https://www.aquasec.com/cloud-native-academy/vulnerability-management/vulnerability-exploitability-exchange/)
as a CVE tracking tool. CVEs that exist in the application are documented in the [cves](./cves) directory.

```
docker scout cves {container-image} --only-severity critical,high,medium --vex-location ./cves
```

### AWS RDS Connection
Please note that if you are running a docker container directly and want to connect to an RDS instance you will need to
make sure that your default IP address configuration does not conflict with AWS CIDR ranges. The following
configuration should prevent this. You can change docker addressing in `/etc/docker/daemon.json` or in the Docker
Engine config in Docker for Desktop. After this change restart your Docker daemon. You will need to make sure this
configuration is applied in order to run a local cluster as well.
```
{
  "default-address-pools":
  [
    {"base":"10.15.0.0/16","size":24}
  ]
}
```

## Expected Env Vars
```
RDS_HOST - Database host name
RDS_DB - Database table name, likely tvevents
RDS_USER - Database user, likely tvevnets
RDS_PASS - Database Password
RDS_PORT - Database port, should default to 5432
T1_SALT - The Salt encryption key used to decode hashes from the TV to verify request authenticity.
TVEVENTS_DEBUG - Used to enable debugging of the python application.
SERVICE_NAME - Used to send data to New Relic. Service name is defined in the application to help segment metrics.
FLASK_ENV - Used to enable flask debugging mode.
SEND_EVERGREEN - Should the application send data to the Evergreen firehose.
SEND_LEGACY - Should the application send data to the Legacy firehose.
EVERGREEN_FIREHOSE_NAME - The name of the Kinesis firehose to send to Evergreen.
DEBUG_EVERGREEN_FIREHOSE_NAME - Debug Kinesis firehose to send to Evergreen.
LEGACY_FIREHOSE_NAME - The name of the Kinesis firehose to send to Legacy.
DEBUG_LEGACY_FIREHOSE_NAME - Debug Kinesis firehose to send to Legacy.
AWS_REGION - The AWS reigon the firehose for the container is located in.
LOG_LEVEL - What level to configure the logger for, if not set it defaults to debug.
ACR_DATA_MSK_USERNAME - acr-data MSK username (for SASL/SCRAM authentication)
ACR_DATA_MSK_PASSWORD - acr-data MSK password (for SASL/SCRAM authentication)
OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT - Set limit for how many attributes are sent at a time
OTEL_EXPORTER_OTLP_HEADERS - Sets the formatted API KEY
OTEL_EXPORTER_OTLP_COMPRESSION - Compression for data trasmission to OTEL collector
OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST - Identify HTTP headers to collect
OTEL_LOG_LEVEL - Set log level for OTEL
OTEL_PYTHON_DEBUG - Debug mode for OTEL data
OTEL_PYTHON_LOG_CORRELATION - Enable log correlation with trace/span/metric data
OTEL_PYTHON_LOG_FORMAT - Log format for the python logger.
OTEL_EXPORTER_OTLP_PROTOCOL - Protocol for OTEL exporter (e.g., http/protobuf)
OTEL_EXPORTER_OTLP_ENDPOINT - OTEL collector endpoint (e.g., https://otlp.nr-data.net:443)
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED - Set to true to auto-enable logging instrumentation in Python.
OTEL_LOGS_EXPORTER - The OTEL logs exporter to use (e.g., otlp, console, etc...)
OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED - Set to true to enable Python auto-instrumentation.
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT - OTEL endpoint for traces (e.g., /v1/traces)
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT - OTEL endpoint for metrics (e.g., /v1/metrics)
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT - OTEL endpoint for logs (e.g., /v1/logs)
OTEL_SERVICE_NAME - The name of the OTEL service (e.g., local-test)
ENV - The environment (e.g., dev, stage, qa, prod)
TEST_CONTAINER - Set to true in order to disable OTEL and environment variable checks.
BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH - File path to the blacklisted channel IDs cache
```
Evergreen to Legacy Firehose mapping
```
inscape-evergreen-dev -> s3_bucket_prefix = "development/tvevents(_debug)/hotc/"
inscape-evergreen-prod -> s3_bucket_prefix = "production/tvevents(_debug)/hotc/"
inscape-evergreen-qa -> s3_bucket_prefix = "qa/tvevents(_debug)/hotc/"
inscape-evergreen-staging -> s3_bucket_prefix = "staging/tvevents(_debug)/warm/"
```

These environment variables should only be required when running the container locally either standalone, or in a
minikube cluster. They can be found in the SSO portal.

```
AWS_ACCOUNT
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
```

## Code Checkout
This repo uses a git submodule to include the dependency for [cnlib](https://github.com/CognitiveNetworks/cntools_py3/tree/master/cnlib).
You will need to make sure to init and update this module when you check out the repo if you want to successfully build
the docker container.

```
git submodule init
git submodule update
```

## Running a container locally

1. Build your container
```
docker build -t tvevents-k8s:latest . --pull --no-cache
```

Below is an example docker run command running the container after building locally, all sensitive secrets must be
passed into the container, and can be found in the following locations:

RDS_HOST - Can be found in the current `tvevents-{{zoo}}-iad.yaml` file.
RDS_PASS - Can be found in the current `tvevents-{{zoo}}-iad.yaml` file.
T1_SALT - Can be found in the current `tvevents-{{zoo}}-iad.yaml` file.
AWS_ACCOUNT - Can be found in the SSO portal section for `Access keys`
AWS_ACCESS_KEY_ID - Can be found in the SSO portal section for `Access keys`
AWS_SECRET_ACCESS_KEY - Can be found in the SSO portal section for `Access keys`
AWS_SESSION_TOKEN - Can be found in the SSO portal section for `Access keys`

```
docker run -d -p 8000:8000 \
-e AWS_REGION=us-east-1 \
-e TEST_CONTAINER=true \
-e LOG_LEVEL=DEBUG \
-e ENV=dev \
-e FLASK_ENV=dev \
-e SERVICE_NAME="local-testing" \
-e RDS_HOST={{RDS_USER_HOST}} \
-e RDS_DB={{RDS_USER_DB}} \
-e RDS_USER={{RDS_USER_USERNAME}} \
-e RDS_PASS={{RDS_USER_PASSWORD}} \
-e RDS_PORT=5432 \
-e T1_SALT={{T1_SALT}} \
-e TVEVENTS_DEBUG=false \
-e FLASK_ENV=tvevents-k8s-local \
-e SEND_EVERGREEN=True \
-e SEND_LEGACY=False \
-e EVERGREEN_FIREHOSE_NAME=tveoe-evergreen \
-e DEBUG_EVERGREEN_FIREHOSE_NAME=tveoe-debug-evergreen \
-e LEGACY_FIREHOSE_NAME=tveoe-legacy \
-e DEBUG_LEGACY_FIREHOSE_NAME=tveoe-debug-legacy \
-e AWS_ACCOUNT={{AWS_ACCOUNT}} \
-e AWS_ACCESS_KEY_ID={{AWS_ACCESS_KEY_ID}} \
-e AWS_SECRET_ACCESS_KEY={{AWS_SECRET_ACCESS_KEY}} \
-e AWS_SESSION_TOKEN={{AWS_SESSION_TOKEN}} \
--name tv-events-container \
tvevents-k8s:latest
```

## Running Minikube locally
1. Start minikube and make sure that the docker env vars are set. We need to make sure that the pods inside the
minikube container can correctly access the AWS arch via the VPN. It seems that sometimes the Docker network likes to
not create itself properly. Make sure that your subnets are correct with `docker network inspect minikube-bridge` before
starting the minikube service.

You will need to make sure that you allow connections out of your local minikube cluster to whatever DB you are
intending to connect to. You can use `nslookup` or `ping` on the `RDS_HOST` value to find out this IP address.
```
docker network create --subnet=10.16.0.0/24 minikube-bridge
minikube start --driver=docker --network minikube-bridge
minikube ssh -- 'sudo ip route add {{DB_IP_ADDRESS}} via 10.15.0.1'
```

2. Build/pull your container
```
docker build -t tvevents-k8s:{IMAGE TAG} . --pull --no-cache
```

NOTE: The latest tag sets the imagePullPolicy to Always implicitly. You can try setting it to IfNotPresent explicitly
or change to a tag other than latest. Avoid using the latest tag so that k8s correctly uses the local filestore for the
Docker image lookup.

Alternatively you can authenticate with your AWS profile to the AWS CLI and pull down the container build that is
present in the `charts/values.yaml` image section.
```
aws sso login --profile {{AWS SSO PROFILE}}
aws ecr get-login-password --region {{ECR REGION}} --profile {{AWS SSO PROFILE}} | docker login --username AWS --password-stdin {{AWS ACCOUNT ID}}.dkr.ecr.{{ECR REGION}}.amazonaws.com
docker pull {{REPO FROM charts/values.yaml}}:{{TAG FROM charts/values.yaml}}
```

3. Load the built Docker image into Minikube
```
minikube image load {{DOCKER IMAGE URI}}
```

4. Install the helm chart and create the namespace / secrets in the K8s cluster. When running locally you will need
AWS credentials that can be found on the SSO start page for whatever account you need to auth to.
```
helm upgrade --install tvevents-k8s ./charts \
  --namespace tvevents-k8s --create-namespace \
  --values ./charts/values.yaml \
  --set secrets.RDS_HOST=127.0.0.1 \
  --set secrets.RDS_DB=mydatabase \
  --set secrets.RDS_USER=postgres \
  --set secrets.RDS_PASS=mypassword \
  --set secrets.RDS_PORT=5432 \
  --set secrets.T1_SALT={{T1_SALT_VALUE}} \
  --set secrets.LOCAL_OTEL_EXPORTER_OTLP_HEADERS="{{NEW_RELIC_API_KEY}}" \
  --set secrets.LOCAL_OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp.nr-data.net:443" \
  --set secrets.AWS_ACCOUNT={{AWS ACCOUNT}} \
  --set secrets.AWS_ACCESS_KEY_ID={{AWS KEY}} \
  --set secrets.AWS_SECRET_ACCESS_KEY={{AWS SECRET}} \
  --set secrets.AWS_SESSION_TOKEN={{AWS SESSION TOKEN}}
```

5. Check that the service and pods are running as expected
```
kubectl get svc -n tvevents-k8s
kubectl get pods -n tvevents-k8s --show-labels
```

6. You should now be able to run the following minikube command to have the service opened in the browser
```
minikube service tvevents-k8s-service -n tvevents-k8s
```

7. You can now use `scripts/traffic-sim.sh {{IP_ADDRESS:PORT_OF_CLUSTER}}` with the IP address and port that was loaded in
your browser to simulate TV Event traffic to the cluster. This data should be aggregated and eventually be persisted
into the S3 bucket that is attached to your configured firehose. You can also inspect your minikube Docker container
and run `docker ps` inside it to find the container your traffic is being sent to and view its logs with
`docker logs -f --tail 50 {{DOCKER_CONTAINER_ID}}`

## Infra

This repository will be automatically built and deployed to the AWS Kubernetes cluster via GitHub actions. Helm configuration
is housed in the `charts` folder, and Kubernetes config can be found in the `kind-config.yaml` file.

### Helm Debugging
You can use the `helm lint` and `helm template` commands to verify that your Helm chart configuration is valid.

```
helm lint charts
helm template tvevents charts
```

### Logging
In order to get generic container logs you can run the following command.

```
kubectl get pods -n tvevents-k8s
kubectl logs {POD NAME} -n tvevents-k8s
```

In order to get into an individual TV Events container you can ssh into it directly.

```
kubectl exec -it {POD NAME} -n tvevents-k8s -- /bin/bash
```

### GitHub Workflows
This repo has several workflows configured for automated testing, building, and pushing of containers. It is recommended
when working on these workflows to use [act](https://nektosact.com/introduction.html) to test them.

The following commands can be used to run the workflows locally in order to test them without pushing to GitHub.

Test the CI pipeline
```
 act -j build-and-test-container
```

Test merge workflows
```
act -j master_build_and_push_to_ecr
act -j prerelease_build_and_push_to_ecr
```

To test the individual parts of CI
```
act -j pylint
act -j black
act -j pytest
act -j complexipy
act -j mypy
```

The comment workflow is not testable with ACT because we use a dynamic environment strategy to pull OIDC credentials
from GitHub secrets. At the time of this writing, ACT does not support variable environment declarations.

## Development
You will need to lock requirements with the lock script if you add anything to the pyproject.toml file. This will ensure
the docker environment gets built with the correct dependencies. If you have installed dependencies with pip, but have
not added them to the pyproject.toml file then they will not be locked into the requirements.txt files, and will not
be installed in the docker environment.

To lock the requirements added in pyproject.toml file, you can use the below commands

```
pip install pip-tools
./scripts/lock.sh
```

### Tooling
We run the following tooling in the dev env: \
[pylint](https://github.com/pylint-dev/pylint-django) \
[mypy](https://mypy-lang.org/) \
[black](https://github.com/psf/black) \
[pytest](https://pytest-django.readthedocs.io/en/latest/index.html) \
[complexipy](https://github.com/rohaquinlop/complexipy)
[mypy](https://mypy-lang.org/)

In order to run these checks individually you can use the following commands:
```
pytest
pylint app tests
black app tests
mypy app tests
complexipy app
complexipy tests
```

Black is configured not to touch string normalization by default, so it will not adjust quoting on strings.

To generate a code coverage report manually you can use the following command:

`pytest --cov-report=html:coverage_report`

You may also need to make sure that if running outside the Docker container that you have the cnlib dependency
installed and linked

```
pip install -e cntools_py3/cnlib
```

### Git Hooks
Since several standards are in place via GitHub actions if you would like to enable the provided git hook with the repo,
you can ensure anytime you commit that these tests are run in order to prevent erroneous failures. Run the following
command to enable these checks automatically.

```
git config core.hooksPath hooks
```

### Testing
If you want to test a TVE payload you can run the following and point it at wherever your instance is running
```
curl -X POST \
  'http://localhost:8000?tvid=2180993&event_type=NATIVEAPP_TELEMETRY' \
  -H 'cache-control: no-cache' \
  -H 'content-type: application/json' \
  -d '{
    "TvEvent": {
      "tvid": "2180993",
      "h": "554ab50be11666cf2c4c4c196448faa8",
      "client": "acr",
      "timestamp": 1599860922441,
      "EventType": "NATIVEAPP_TELEMETRY"
    },
    "EventData": {
      "AppId": "123abc",
      "AppName": "WatchFree+",
      "Timestamp": 1599860922440,
      "EventType": "ChannelChange",
      "AdId": {
          "LMT": 0,
          "IFA": "aa84c930-asdf-asdf-8cc0-123b55b2ff07",
          "IFA_TYPE": "dpid"
      },
      "ChannelId": "abc123",
      "ProgramId": "x9y8x7",
      "WatchFreePlusSessionId": "68b429c2-347b-4075-98a9-6d18d237cf68",
      "ChannelName": "Newsy",
      "NameSpace": 4,
      "Environment": "LOCAL",
      "IsContentBlocked": true
    }
}'
```

This request is scripted through the `scripts/traffic-sim.sh` script. It has the ability to use
[Oha](https://github.com/hatoo/oha) to simulate large amounts of traffic, or can do a simple curl for single request
testing. Please note that the hash is specific to the TVID and your environment will need to correct `T1_SALT`
environment variable configured in order for these requests to be validated and correctly decrypted. The tvid and hash
in the existing request can be verified with the `T1_SALT` in `s3://cn-secure/salt_external_pillar/tvevents-development-iad.yaml`
in the Inscape Production AWS account with ID 788724168120.

There is a built-in traffic shift script that also allows you to adjust AGA traffic weights and simulate traffic
moving between regions.

```
AWS_PROFILE=inscape-evergreen-ikon-admin ./traffic-shift.sh \
    -a arn:aws:globalaccelerator::445567069541:accelerator/c68433c9-e1d8-4fed-95d1-88e6f780e16b \
    -r us-east-1 \
    -w 100
```

### Before you merge the PR
Before merging PR, ensure this can run in the PR env (use PR comments to run / commands):

1. `/create-pod-identity firehose firehose-writer`
2. `/push-to-ecr dev`
3. Update `charts/values.yaml` `sha_ref` with the `sha_ref` returned from the `push-to-ecr` build comment. Only need `dev_sha_ref` for PR env.
4. Add `preview` label to PR
5. Will show up in argo as `tve-us-east-1-pr-<pr number>`, endpoint url: `http://tve-us-east-1-pr-<pr number>.dev.evergreen.tvinteractive.tv/status`, namespace: `tvevents-pr-<pr number>`

#### Adding new secrets to Helm chart
When adding new secrets to Helm chart, remember to:
1. Create respective entries for the secrets in Secrets Managers in ALL environments. If the secret in particular environment is not needed yet, create an entry with an empty value
2. Update [Expected Env Vars](#expected-env-vars) section in this document
3. Update [environment-check.sh](./environment-check.sh)