# Dapr Presentation Talk Track

## Slide 1: Dapr Quick Reference

"Today I'm going to walk you through Dapr - the Distributed Application Runtime. Dapr is a portable runtime that simplifies building microservices. The key thing to understand is that Dapr runs as a sidecar alongside your application, providing building blocks for common managed cloud services - all without requiring you to change your application code.

The core concept here is the sidecar pattern - Dapr runs in a separate container next to your app container inside the same pod, and intercepts calls to provide these distributed capabilities. You configure components via YAML - whether that's AWS S3, Google Cloud Storage, Redis, Kafka, or any other supported service. Dapr provides a consistent API regardless of which underlying service you're using.

The other two concepts to understand are the Component and Bindings, which we we will go over in the next slides.

The diagram here shows how Dapr fits into the broader microservices ecosystem with input and output bindings that interface with these components."

---

## Slide 2: Architecture & Enabling Dapr

"Let's look at a simpler architecture diagrm. Your application runs on port 8000 - that's your Flask app or whatever service you're building. The Dapr sidecar runs alongside it and exposes three key ports: HTTP on 3500, gRPC on 50001, and metrics on 9090.

When your application needs to interact with external services - like S3, SQS, or any other component - it makes a simple HTTP or gRPC call to the Dapr sidecar on localhost. The sidecar then handles all the complexity of talking to those external services. This means your application code stays clean and portable - you're not tightly coupled to AWS or GCP APIs."

---

## Slide 3: Enabling Dapr in Your Service

"Enabling Dapr in our Kubernetes environment is straightforward through Helm values. The simple case is a few actions - enable Dapr, give it an app ID, and tell it what port your app listens on.

The more interesting example is when we want to configure actual components. Here we're setting up object storage bindings for both AWS S3 and Google Cloud Storage. Notice the structure - we define components under cloud providers, give each a name like 'object-storage', specify the binding type, and provide metadata like bucket name and region.

The beauty here is that you can configure multiple cloud providers in the same service. Your code just talks to 'object-storage' - Dapr handles whether that's S3 or GCS under the hood. This makes multi-cloud deployments much simpler."

From here our Continuous Deployment system, in our case Argo will pass which cloud provider the Chart is being deployed in and apply the correct component.

---

## Slide 4: S3/Python Implementation - Upload

"Now let's see what this looks like in actual Python code. This is a Flask endpoint for uploading files to S3 via Dapr.

Notice how simple this is - we're just making a POST request to localhost:3500, which is the Dapr sidecar. We specify the operation as 'create', pass the file content as data, and provide metadata with the key - that's the S3 object key.

There's no boto3, no AWS SDK imports, no credential management in your code. Dapr handles all of that. The sidecar uses the pod identity we configured in Kubernetes to authenticate with AWS. Your application code stays clean and focused on business logic."

---

## Slide 5: S3/Python Implementation - Download, List, Delete

"Here are the other common operations. Download is just as simple - POST to the same Dapr endpoint with operation 'get' and the key you want to retrieve. The response comes back with the file data base64 encoded.

List operations let you enumerate objects in the bucket - you can specify maxResults to limit how many you get back. And delete is straightforward - just specify the operation and the key.

All of these follow the same pattern: POST to localhost:3500/v1.0/bindings/your-binding-name with an operation and metadata. It's consistent, it's simple, and it's portable across different storage backends."

---

## Slide 6: S3 Binding Operations

"Let me summarize the key operations you can perform with S3 bindings. Create for uploads, get for downloads, delete for removing objects, and list for enumeration. Each operation takes specific metadata fields - for example, create can take an optional ContentType.

The key takeaways here: First, the API is incredibly simple - just POST to localhost:3500. Second, you don't need the AWS SDK, which means smaller container images and less dependency management. Third, IAM role support is built-in through pod identity. And finally, you can perform all the standard object storage operations through this consistent interface.

This means if you need to switch from S3 to GCS or Azure Blob Storage, you're just changing Helm configuration - not rewriting application code."

---

## Slide 7: Debugging & Best Practices

"Finally, let's talk about debugging and best practices. When things go wrong, you'll want to look at the Dapr sidecar logs. Use kubectl logs with the -c daprd flag to see the sidecar container logs specifically.

You can also inspect Dapr components directly with kubectl get components and kubectl describe to see the configuration that's actually deployed.

For best practices: Keep your app IDs consistent with your service names for clarity. Make sure appPort matches what your application actually listens on - this is a common source of errors. Leverage Dapr components instead of hardcoding infrastructure details in your code. Handle errors gracefully - always check response status codes. And monitor the sidecar health - if the sidecar is down, your app can't communicate with external services.

The Dapr documentation is excellent, and there's a Python SDK if you want more type safety than raw HTTP requests. I've included links here for further reading."

---

## Closing

"To wrap up: Dapr gives you a portable, consistent way to interact with cloud services without coupling your code to specific cloud providers. It runs as a sidecar, handles authentication with retries, and provides a simple HTTP API. For our use case with object storage, it means we can write code once and deploy it to AWS or GCP without changes. Questions?"
