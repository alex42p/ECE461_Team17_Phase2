# AWS Cognito Integration Guide

## Overview

This project now uses AWS Cognito for authentication instead of custom JWT auth. This reduces authentication code from **751 lines to ~290 lines** (62% reduction) while improving security and maintainability.

## What Changed

### Files Created
- `src/cognito_auth.py` (200 lines) - Replaces `auth_service.py` (450 lines)
- `src/cognito_middleware.py` (90 lines) - Replaces `auth_middleware.py` (301 lines)
- `scripts/setup_cognito.sh` - Automated Cognito setup script

### Files Modified
- `src/app.py` - Updated to use Cognito auth
- `requirements.txt` - Removed bcrypt/PyJWT, kept boto3

### Files You Can Delete (Optional)
- `src/auth_service.py` (no longer used)
- `src/auth_middleware.py` (no longer used)

---

## Quick Setup (5 minutes)

### Step 1: Configure AWS CLI

```bash
# Install AWS CLI if not already installed
brew install awscli  # macOS
# or
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure with your credentials
aws configure
# Enter:
#   AWS Access Key ID
#   AWS Secret Access Key
#   Default region (us-east-1)
#   Output format (json)
```

### Step 2: Run Cognito Setup Script

```bash
cd /Users/george/ECE461_Team17/ECE461_Team17_Phase2

# Run the automated setup script
./scripts/setup_cognito.sh
```

The script will output environment variables. **Copy them!**

### Step 3: Set Environment Variables

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
export AWS_COGNITO_USER_POOL_ID="us-east-1_XXXXXXXXX"
export AWS_COGNITO_CLIENT_ID="xxxxxxxxxxxxxxxxxxxxx"
export AWS_COGNITO_CLIENT_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxx"
export AWS_REGION="us-east-1"
```

Then reload:

```bash
source ~/.zshrc  # or source ~/.bashrc
```

### Step 4: Install Dependencies

```bash
cd /Users/george/ECE461_Team17/ECE461_Team17_Phase2
source venv/bin/activate
pip install -r requirements.txt
```

### Step 5: Start Application

```bash
python src/app.py
```

**Default Credentials:**
- Email: `admin@example.com`
- Password: `Admin123!`

---

## Testing Authentication

### Test 1: Authenticate via CLI

```bash
curl -X PUT http://localhost:8080/authenticate \
  -H "Content-Type: application/json" \
  -d '{
    "User": {"name": "admin@example.com", "isAdmin": true},
    "Secret": {"password": "Admin123!"}
  }'
```

Expected response:

```json
{
  "token": "eyJraWQiOiJ...",
  "user": {
    "name": "admin@example.com",
    "role": "admin",
    "email": "admin@example.com"
  },
  "expires_in": 36000,
  "max_api_calls": 1000
}
```

### Test 2: Use Token to Access Protected Endpoint

```bash
# Save token from previous response
TOKEN="eyJraWQiOiJ..."

# Access health endpoint
curl -X GET http://localhost:8080/health/components \
  -H "X-Authorization: Bearer $TOKEN"
```

### Test 3: Create New User (Admin Only)

```bash
curl -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -H "X-Authorization: Bearer $TOKEN" \
  -d '{
    "username": "testuser@example.com",
    "email": "testuser@example.com",
    "password": "TestUser123!",
    "role": "uploader"
  }'
```

---

## Frontend Changes

Your frontend (`src/static/app.js`) already works with Cognito! The token format is compatible.

Just make sure users login with:
- **Email** (not username): `admin@example.com`
- **Password**: `Admin123!`

---

## User Management

### Roles
- **admin**: Full access, can create/delete users
- **uploader**: Can upload packages
- **searcher**: Can search packages
- **downloader**: Can download packages

### Create User via AWS Console

1. Go to [AWS Cognito Console](https://console.aws.amazon.com/cognito/)
2. Select your User Pool
3. Click "Create user"
4. Set email, temporary password, and custom attribute `role`

### Create User via CLI

```bash
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username "newuser@example.com" \
  --user-attributes Name=email,Value=newuser@example.com Name=custom:role,Value=uploader \
  --temporary-password "TempPass123!" \
  --message-action SUPPRESS

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username "newuser@example.com" \
  --password "NewPass123!" \
  --permanent
```

### List All Users

```bash
aws cognito-idp list-users \
  --user-pool-id us-east-1_XXXXXXXXX
```

### Delete User

```bash
aws cognito-idp admin-delete-user \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username "user@example.com"
```

---

## Benefits of Cognito vs Custom Auth

| Feature | Custom Auth | AWS Cognito |
|---------|-------------|-------------|
| Lines of Code | 751 | 290 |
| Password Management | Manual | Managed by AWS |
| MFA Support | Need to implement | Built-in |
| Password Reset | Need to implement | Built-in |
| Email Verification | Need to implement | Built-in |
| Rate Limiting | Manual | Built-in |
| Token Refresh | Manual | Built-in |
| Security Audits | Your responsibility | AWS handles |
| Scalability | Limited | Unlimited |
| Cost | Server costs | $0.0055/MAU after 50K free |

---

## Cost Estimation

### Free Tier (First 50,000 Monthly Active Users)
- **Cost**: $0/month
- Perfect for class projects and small deployments

### Paid Tier (After 50K MAUs)
- **Cost**: $0.0055 per MAU
- Example: 100,000 MAUs = $275/month
- Still cheaper than maintaining auth infrastructure

---

## Troubleshooting

### "Missing Cognito configuration" Error

**Problem**: Environment variables not set

**Solution**:
```bash
echo $AWS_COGNITO_USER_POOL_ID  # Should print pool ID
# If empty, run setup script again and set environment variables
```

### "Invalid token" Error

**Problem**: Token expired or invalid

**Solution**: Re-authenticate to get a new token. Tokens expire after 10 hours.

### "NotAuthorizedException" Error

**Problem**: Wrong password or user doesn't exist

**Solution**: 
- Verify email and password
- Use email format (not username)
- Check user exists in Cognito console

### Cannot Create Cognito Pool

**Problem**: AWS CLI not configured or insufficient permissions

**Solution**:
```bash
# Re-configure AWS CLI
aws configure

# Verify credentials
aws sts get-caller-identity

# Ensure IAM user has cognito-idp:* permissions
```

---

## Migration from Custom Auth

If you have existing users in your database, you'll need to migrate them to Cognito:

### Option 1: Manual Migration Script

```python
# migrate_users_to_cognito.py
from database import get_db, User
from cognito_auth import cognito_auth

session = get_db()
users = session.query(User).all()

for user in users:
    try:
        cognito_auth.create_user(
            username=user.username,
            email=f"{user.username}@example.com",  # Add proper email
            password="TempPassword123!",  # Users will need to reset
            role=user.role.value
        )
        print(f"✓ Migrated {user.username}")
    except Exception as e:
        print(f"✗ Failed to migrate {user.username}: {e}")
```

### Option 2: Fresh Start

Simply delete the old database and use Cognito for all new users.

---

## Security Best Practices

1. **Change Default Admin Password**
   ```bash
   aws cognito-idp admin-set-user-password \
     --user-pool-id $AWS_COGNITO_USER_POOL_ID \
     --username admin@example.com \
     --password "YourStrongPassword123!" \
     --permanent
   ```

2. **Enable MFA** (Optional but Recommended)
   - Go to Cognito Console
   - User Pool Settings → MFA
   - Enable "Required" for all users

3. **Rotate Client Secret**
   - In production, rotate secrets regularly
   - Store secrets in AWS Secrets Manager

4. **Use Environment-Specific Pools**
   - Development pool
   - Staging pool
   - Production pool

---

## Next Steps

1. ✅ Setup complete - Authentication working
2. ✅ Test all endpoints
3. [ ] Enable MFA in Cognito console
4. [ ] Set up proper email domain for verification emails
5. [ ] Configure password policies in Cognito
6. [ ] Set up CloudWatch logging for auth events
7. [ ] Clean up old auth files (optional)

---

## Support

**Documentation**: 
- [AWS Cognito Developer Guide](https://docs.aws.amazon.com/cognito/)
- [Boto3 Cognito Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cognito-idp.html)

**Issues**: Check application logs for detailed error messages

**Contact**: Your team for project-specific questions

---

**Last Updated**: November 24, 2025  
**Version**: 1.0

