#!/bin/bash
echo "Initialising LocalStack resources..."

# Seed the Steam API key into SSM Parameter Store
awslocal ssm put-parameter \
  --name "/steam/api-key" \
  --value "dummy-steam-api-key" \
  --type "SecureString" \
  --overwrite

echo "LocalStack init complete."

