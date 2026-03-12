# rebuilder-evergreen-template-repo-python

This is a modified version of `evergreen-template-repo-python` used as the target
end-state reference for rebuilder. Key changes from the original template:
- **FastAPI + uvicorn** replaces Flask + gunicorn
- **Python 3.12** replaces Python 3.10
- Healthcheck bug fixed (original checks port 80 while gunicorn listens on 8000)

## Setup
Required installations
- [Helm](https://helm.sh/docs/intro/quickstart/)
- [Docker](https://docs.docker.com/get-started/introduction/get-docker-desktop/)
- [pip-tools](https://github.com/jazzband/pip-tools)

K8s Deployment Testing
- [Skaffold](https://skaffold.dev/) automates building, pushing, and deploying your application to Kubernetes.
- [stern](https://github.com/stern/stern) tool for log parsing from multiple K8s pods
- [k3s](https://k3s.io/)

### CVE tooling - We're still using these? 
- [Docker scout extension](https://scout.docker.com/) 
- [vexctl](http://github.com/openvex/vexctl) `brew install vexctl`

Run the following CLI command to view existing CVEs inside the container that have a remediation path. We purposely 
ignore vulnerabilities that are LOW or UNDEFINED severity ratings. We use 
[VEX](https://www.aquasec.com/cloud-native-academy/vulnerability-management/vulnerability-exploitability-exchange/)
as a CVE tracking tool. CVEs that exist in the application are documented in the [cves](./cves) directory.

## Environment Variables

Below is a detailed explanation of each required environment variable:
```
ENV - Required. The deployment environment (e.g. dev, staging, prod).
SERVICE_NAME - Used to send data to New Relic. Service name is defined in the application to help segment metrics.
AWS_REGION - The AWS region the firehose for the container is located in.
LOG_LEVEL - What level to configure the logger for, if not set it defaults to debug.
TEST_CONTAINER - Whether or not this is a test container, turns off OTEL.
OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED - Enable/disable OTEL auto-instrumentation (true/false).
```

OTEL Configuration env variables - Setting these affects the underlying OTEL installation: 
```
OTEL_EXPORTER_NEW_RELIC_API_KEY - New Relic API key for OTEL exporter.
OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT - Set limit for how many attributes are sent at a time.
OTEL_EXPORTER_OTLP_HEADERS - Sets the formatted API KEY.
OTEL_EXPORTER_OTLP_ENDPOINT - URI OTEL will send metric to.   
OTEL_EXPORTER_OTLP_COMPRESSION - Compression for data trasmission to OTEL collector.
OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST - Identify HTTP headers to collect.
OTEL_EXPORTER_OTLP_PROTOCOL - THe protocol that OTEL will use to send metrics to the endpoint.
OTEL_LOG_LEVEL - Set log level for OTEL.
OTEL_PYTHON_DEBUG - Debug mode for OTEL data.
OTEL_PYTHON_LOG_CORRELATION - Enable log correlation with trace/span/metric data.
OTEL_PYTHON_LOG_FORMAT - Logging format for the python logger configured by OTEL. 
```


## Initial setup
1. Create a venv, source it, install dev requirements
```
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

## Running a container locally

1. Build your container, you can pass the environment variables directly, or place them in a file and pass the 
file to the build command. 
``` 
docker build -t demo-app:latest . --pull --no-cache
```

``` 
docker run -d -p 8000:8000 --user root \
-e AWS_REGION=us-east-1 \
-e TEST_CONTAINER=true \
-e LOG_LEVEL=DEBUG \
-e ENV=dev \
-e SERVICE_NAME="local-testing" \
-e OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED=false \
--name demo-app \
demo-app:latest
```
or
```
docker run -d -p 8000:8000 --env-file env.list --user root --name demo-app \
demo-app:latest
```

## Test local changes in a K8s Cluster
Applications have the ability to package local changes and deploy them to a K8s cluster in order to test in a cluster 
environment. Skaffold will initiate AWS, and cluster authentication for you, build the docker container, place it in 
the ECR, deploy it via Helm to the development cluster in a namespace based on your username, and sync Python file 
changes automatically. If you run Skaffold without tailing the logs you will see a URL for the live app is provided
to you in order to verify the application is live. 

1. Run Skaffold in dev mode (auto-rebuilds on code changes):
```
SKAFFOLD_PROFILE=demo-app skaffold dev
```

2. Run without tailing logs:
```
SKAFFOLD_PROFILE=demo-app skaffold dev --tail=false
```

3. Or deploy once without watching:
```
SKAFFOLD_PROFILE=demo-app skaffold run
```

## Infra

This repository will be automatically built and deployed to the AWS Kubernetes cluster via GitHub actions.
Helm configuration is housed in the `charts` folder, and Kubernetes config can be found in the `kind-config.yaml` 
file.


### Logging

In order to get generic container logs you can run the following command.

``` 
kubectl get pods -n demo-app
kubectl logs {POD NAME} -n demo-app
```

For easier control use stern and utilize it's fuzzy search capability

view all logs from every pod in a namespace. the - is we are matching on any app with a dash in it
```
stern -n demo-app -
```

In order to get into an individual container you can ssh into it directly. 

``` 
kubectl exec -it {POD NAME} -n demo-app -- /bin/bash
```

### GitHub Workflows
This repo has several workflows configured for automated testing, building, and pushing of containers. It is recommended 
when working on these workflows to use [act](https://nektosact.com/introduction.html) to test them. 

The following commands can be used to run the workflows without pushing to GitHub. ACT can be finicky since you're 
going to be running several containers at the same time and orchestrating between them, it's best to retry a specific 
run if you are seeing odd failures that are not reproducible. Sometimes Netskope can cause issues inside contianers
when trying to validate SSL certs for external domains.

Test the CI pipeline
``` 
 act -j build-and-test-container
```

Test the build and push container on merge / comment workflows
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
act -j helm_lint
act -j helm_template
```

The comment workflow is not testable with ACT because we use a dynamic environment strategy to pull OIDC credentials 
from GitHub secrets. At the time of this writing, ACT does not support variable environment declarations.

## requirements.txt
You will need to lock requirements with the lock script if you add anything to the pyproject.toml file. This will ensure
the docker environment gets built with the correct dependencies. If you have installed dependencies with pip, but have
not added them to the pyproject.toml file then they will not be locked into the requirements.txt files, and will not
be installed in the docker environment.

To lock the requirements added in pyproject.toml file, you can use the below commands

```
./scripts/lock.sh
```

### Tooling
We run the following tooling in the dev env: \
[pylint](https://github.com/pylint-dev/pylint-django) \
[mypy](https://mypy-lang.org/) \
[black](https://github.com/psf/black) \
[pytest](https://pytest-django.readthedocs.io/en/latest/index.html) \
[complexipy](https://github.com/rohaquinlop/complexipy) \
[mypy](https://mypy-lang.org/)
[Helm Unittest](https://github.com/helm-unittest/helm-unittest.git)
```
helm plugin install https://github.com/helm-unittest/helm-unittest.git
```

In order to run these checks individually you can use the following commands:
``` 
pytest
pylint app tests
black app tests
mypy app tests
complexipy app
complexipy tests
helm unittest charts
./tests/test-helm-template.sh
```

Black is configured not to touch string normalization by default, so it will not adjust quoting on strings.

To generate a code coverage report manually you can use the following command:

`pytest --cov-report=html:coverage_report`

You may also need to make sure that if running outside the Docker container that you have the cnlib dependency 
installed and linked

``` 
pip install -e cntools_py3/cnlib 
```

### Helm Debugging
You can use the `helm lint` and `helm template` commands to verify that your Helm chart configuration is valid.
For more information refer to [charts/tests/README.md](charts/tests/README.md).

helm lint: Checks chart structure, syntax, and best practices (like YAML validity, required fields in Chart.yaml, etc.)

helm template: Actually renders the templates with values to produce the final Kubernetes manifests, letting you see 
what would be deployed

For a valid helm template to render a manifest some basic ciOptions inputs are required, you can find an example of 
these in the helm smoke tests.  

See [smoke test script](tests/test-helm-template.sh).

run as:
```
./tests/test-helm-template.sh
```

or for a specific template:

```
./tests/test-helm-template.sh Deployment.yaml
```

This will render templates using a variety of different inputs for the different environment types.

### Git Hooks
Since several standards are in place via GitHub actions if you would like to enable the provided git hook with the repo,
you can ensure anytime you commit that all CI checks are run in order to prevent erroneous failures. Run the following
command to enable these checks automatically on every commit.

See [pre-commit hook](hooks/pre-commit) for details.

``` 
git config core.hooksPath hooks  
```

You can run the script directly ./hooks/pre-commit while debugging.

### GitHub PR Commands
Certain command are configured via GitHub actions to allow you to perform build or compile actions based off the 
state of your PR. These can be valuable in the development of features and in working with PR environments. 

## Build and push container
`/push-to-ecr {env}`

This command allows you to specify an environment to push a container artifact to. It will build the container artifact
and place it in the correct AWS ECR depending on the environment you pass. You can then use the resulting output to 
either pull the container artifact down to your local machine for testing, or update the values in the helm values
file to deploy the container artifact to an environment.

After you will get a sha_ref comment and update 

```
environmentConfig:
  dev:
    logLevel: "DEBUG"
    otel:
      replicas: 1
    deployments:
      demo-app:
        sha_ref: "44ad9458001fb201f65c728d5ba4ca194940ecd2"
  ...
  other envs
  ...
```

## Create Pod Identity for PR Environments

To provision AWS access for your PR environment, you need to create an IAM policy and attach it to your PR namespace.

### Creating the IAM Policy

1. Navigate to the [inscape-identity-center](https://github.com/CognitiveNetworks/inscape-identity-center/tree/inscape/evergreen-iam/tvevents) repository
2. Create your IAM policy in the appropriate service and policy directory under `evergreen-iam/` So for demo-app we would have `evergreen-iam/demo-app/demo-app.json` 
3. Define the policy with the necessary AWS permissions for your service
4. Submit a PR to merge the policy

### Attaching to PR Namespace

Once the policy is created, use the GitHub PR command to attach it to your PR namespace:

To provision AWS access for your PR environment, comment with:

```
/create-pod-identity {service-type} [service-account]
```

1. Workflow for this located here: [.github/workflows/pod-identity-manager.yml](.github/workflows/pod-identity-manager.yml)
2. comment /create-pod-identity demo-app <service-name-you-want>

### **Example**
```
/create-pod-identity demo-app my-custom-sa
```

---

**Note:**  
If you do not create a pod identity for your PR environment, your containers will not be able to access AWS resources 
outside the cluster.
