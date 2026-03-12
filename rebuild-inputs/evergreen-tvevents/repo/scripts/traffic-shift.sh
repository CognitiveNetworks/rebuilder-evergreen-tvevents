#!/bin/bash

# Usage function
usage() {
    echo "Usage: $0 -a <accelerator-arn> -r <region> -w <weight>"
    echo "  -a: Global Accelerator ARN"
    echo "  -r: Region to update (e.g., us-east-1)"
    echo "  -w: Traffic weight (0-100)"
    echo "Example: $0 -a arn:aws:globalaccelerator::123456789012:accelerator/xxxx -r us-east-1 -w 75"
    echo "AWS_PROFILE=inscape-evergreen-ikon-admin ./traffic-shift.sh -a arn:aws:globalaccelerator::445567069541:accelerator/c68433c9-e1d8-4fed-95d1-88e6f780e16b -r us-east-1 -w 0"
    exit 1
}

# Input validation function
validate_input() {
    if ! [[ $1 =~ ^[0-9]+$ ]] || [ $1 -lt 0 ] || [ $1 -gt 100 ]; then
        echo "Error: Weight must be between 0 and 100"
        exit 1
    fi
}

# Parse command line arguments
while getopts "a:r:w:" opt; do
    case $opt in
        a) ACCELERATOR_ARN="$OPTARG";;
        r) REGION="$OPTARG";;
        w) WEIGHT="$OPTARG";;
        *) usage;;
    esac
done

# Check if required parameters are provided
if [ -z "$ACCELERATOR_ARN" ] || [ -z "$REGION" ] || [ -z "$WEIGHT" ]; then
    usage
fi

# Validate the weight
validate_input "$WEIGHT"

echo "Discovering endpoint groups..."

# Set AWS_DEFAULT_REGION for request signing
export AWS_DEFAULT_REGION=us-west-2

# Get all listeners for the accelerator
LISTENERS=$(aws globalaccelerator list-listeners \
    --accelerator-arn "$ACCELERATOR_ARN" \
    --query 'Listeners[*].ListenerArn' \
    --output text)

if [ -z "$LISTENERS" ]; then
    echo "Error: No listeners found for accelerator"
    exit 1
fi

# Store endpoint groups in temporary files
REGIONS_FILE=$(mktemp)
ARNS_FILE=$(mktemp)

# Cleanup function
cleanup() {
    rm -f "$REGIONS_FILE" "$ARNS_FILE"
}
trap cleanup EXIT

# For each listener, get its endpoint groups
for LISTENER in $LISTENERS; do
    aws globalaccelerator list-endpoint-groups \
        --listener-arn "$LISTENER" \
        --query 'EndpointGroups[*].[EndpointGroupRegion,EndpointGroupArn]' \
        --output text >> "$REGIONS_FILE"
done

# Check if target region exists and get its ARN
TARGET_ARN=$(grep "^${REGION}" "$REGIONS_FILE" | cut -f2)

if [ -z "$TARGET_ARN" ]; then
    echo "Error: No endpoint group found for region $REGION"
    echo "Available regions:"
    cut -f1 "$REGIONS_FILE" | sort -u | sed 's/^/  - /'
    exit 1
fi

# Calculate opposite weight for other regions
OPPOSITE_WEIGHT=$((100 - WEIGHT))

# Update the specified region
echo "Setting $REGION to ${WEIGHT}%..."
aws globalaccelerator update-endpoint-group \
    --endpoint-group-arn "$TARGET_ARN" \
    --traffic-dial-percentage $WEIGHT

if [ $? -ne 0 ]; then
    echo "Error updating $REGION"
    exit 1
fi

# Update all other regions
while read -r REGION_NAME ARN; do
    if [ "$REGION_NAME" != "$REGION" ]; then
        echo "Setting $REGION_NAME to ${OPPOSITE_WEIGHT}%..."
        aws globalaccelerator update-endpoint-group \
            --endpoint-group-arn "$ARN" \
            --traffic-dial-percentage $OPPOSITE_WEIGHT
        
        if [ $? -ne 0 ]; then
            echo "Error updating $REGION_NAME"
            exit 1
        fi
    fi
done < "$REGIONS_FILE"

echo "Traffic distribution updated successfully:"
echo "  $REGION: ${WEIGHT}%"

