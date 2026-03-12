#!/bin/bash

kubectl delete jobs --all -n demo-app-loop-dev-$(echo $USER | tr '.' '-') --ignore-not-found=true