#!/bin/bash
# AWS Cognito User Pool Setup Script for ECE461 Package Registry
set -e

REGION="${AWS_REGION:-us-east-1}"
POOL_NAME="ece461-package-registry-users"

echo "=================================================="
echo "AWS Cognito User Pool Setup"
echo "=================================================="
echo "Region: $REGION"
echo ""

# Create User Pool
echo "Creating Cognito User Pool..."
POOL_ID=$(aws cognito-idp create-user-pool \
  --pool-name "$POOL_NAME" \
  --region "$REGION" \
  --policies '{
    "PasswordPolicy": {
      "MinimumLength": 8,
      "RequireUppercase": true,
      "RequireLowercase": true,
      "RequireNumbers": true,
      "RequireSymbols": true
    }
  }' \
  --auto-verified-attributes email \
  --username-attributes email \
  --schema '[
    {"Name": "email", "Required": true, "Mutable": false},
    {"Name": "name", "Required": false, "Mutable": true},
    {"Name": "custom:role", "AttributeDataType": "String", "Mutable": true, "DeveloperOnlyAttribute": false}
  ]' \
  --mfa-configuration OFF \
  --user-attribute-update-settings '{"AttributesRequireVerificationBeforeUpdate": ["email"]}' \
  --query 'UserPool.Id' \
  --output text)

echo "✓ User Pool Created: $POOL_ID"

# Create User Pool Client (App Client)
echo "Creating User Pool App Client..."
CLIENT_ID=$(aws cognito-idp create-user-pool-client \
  --user-pool-id "$POOL_ID" \
  --client-name "ece461-webapp-client" \
  --region "$REGION" \
  --generate-secret \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH ALLOW_ADMIN_USER_PASSWORD_AUTH \
  --token-validity-units '{"AccessToken": "hours", "IdToken": "hours", "RefreshToken": "days"}' \
  --access-token-validity 10 \
  --id-token-validity 10 \
  --refresh-token-validity 30 \
  --query 'UserPoolClient.ClientId' \
  --output text)

echo "✓ App Client Created: $CLIENT_ID"

# Get Client Secret
CLIENT_SECRET=$(aws cognito-idp describe-user-pool-client \
  --user-pool-id "$POOL_ID" \
  --client-id "$CLIENT_ID" \
  --region "$REGION" \
  --query 'UserPoolClient.ClientSecret' \
  --output text)

echo "✓ Client Secret Retrieved"

# Create admin user
echo ""
echo "Creating default admin user..."
aws cognito-idp admin-create-user \
  --user-pool-id "$POOL_ID" \
  --username "admin@example.com" \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true Name=custom:role,Value=admin \
  --temporary-password "TempAdmin123!" \
  --message-action SUPPRESS \
  --region "$REGION" || echo "⚠ Admin user may already exist"

# Set permanent password for admin
echo "Setting permanent password for admin..."
aws cognito-idp admin-set-user-password \
  --user-pool-id "$POOL_ID" \
  --username "admin@example.com" \
  --password "Admin123!" \
  --permanent \
  --region "$REGION" || echo "⚠ Password may already be set"

echo "✓ Admin user configured"

# Get User Pool domain (for advanced features)
DOMAIN_PREFIX="ece461-registry-${RANDOM}"
echo ""
echo "Creating User Pool Domain: $DOMAIN_PREFIX"
aws cognito-idp create-user-pool-domain \
  --domain "$DOMAIN_PREFIX" \
  --user-pool-id "$POOL_ID" \
  --region "$REGION" || echo "⚠ Domain may already exist"

echo ""
echo "=================================================="
echo "✓ Cognito Setup Complete!"
echo "=================================================="
echo ""
echo "Add these to your environment variables:"
echo ""
echo "export AWS_COGNITO_USER_POOL_ID=\"$POOL_ID\""
echo "export AWS_COGNITO_CLIENT_ID=\"$CLIENT_ID\""
echo "export AWS_COGNITO_CLIENT_SECRET=\"$CLIENT_SECRET\""
echo "export AWS_REGION=\"$REGION\""
echo ""
echo "Or add to your .env file:"
echo ""
echo "AWS_COGNITO_USER_POOL_ID=$POOL_ID"
echo "AWS_COGNITO_CLIENT_ID=$CLIENT_ID"
echo "AWS_COGNITO_CLIENT_SECRET=$CLIENT_SECRET"
echo "AWS_REGION=$REGION"
echo ""
echo "Default credentials:"
echo "  Email: admin@example.com"
echo "  Password: Admin123!"
echo ""
echo "=================================================="

