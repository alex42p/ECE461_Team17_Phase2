# Quick Start Guide - ECE461 Package Registry

## For Developers

### Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/ECE461_Team17/ECE461_Team17_Phase2.git
cd ECE461_Team17_Phase2

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export DATABASE_URL="sqlite:///./test.db"
export JWT_SECRET="your-secret-key-for-development"
export SECRET_KEY="your-flask-secret-key"
export GITHUB_TOKEN="your_github_token"

# 5. Initialize database
python src/database.py

# 6. Run application
python src/app_enhanced.py
```

The application will be available at `http://localhost:8080`

### Default Credentials

- **Username**: `admin`
- **Password**: `admin123!`

⚠️ **Change these immediately in production!**

---

## For System Administrators

### AWS Deployment (Quick)

```bash
# 1. Configure AWS CLI
aws configure

# 2. Run deployment script (create VPC, EC2, RDS, etc.)
# See DEPLOYMENT_GUIDE.md for detailed instructions

# 3. Set GitHub Secrets for CI/CD
# - AWS_REGION
# - AWS_ROLE_TO_ASSUME
# - EC2_HOSTNAME
# - EC2_SSH_KEY

# 4. Push to main branch to trigger deployment
git push origin main
```

### Cost Monitoring

```bash
# Check current costs
python scripts/aws_cost_monitor.py --report

# Create budget with $10 limit
python scripts/aws_cost_monitor.py --create-budget 10

# Create billing alarm at $10 threshold
python scripts/aws_cost_monitor.py --create-alarm 10
```

---

## For End Users

### Using the Web Interface

1. **Navigate** to `http://your-domain.com:8080`
2. **Login** with your credentials (click Login button in top right)
3. **Search** for packages using the search form
4. **Upload** packages (requires uploader role)
5. **View Health** status in the health section

### Using the API

#### Authenticate

```bash
curl -X PUT http://localhost:8080/authenticate \
  -H "Content-Type: application/json" \
  -d '{
    "User": {"name": "admin", "isAdmin": true},
    "Secret": {"password": "admin123!"}
  }'
```

Save the `token` from the response.

#### Search Packages

```bash
curl -X GET "http://localhost:8080/packages/byRegex?RegEx=bert" \
  -H "X-Authorization: Bearer YOUR_TOKEN_HERE"
```

#### Upload Package

```bash
curl -X POST http://localhost:8080/package \
  -H "Content-Type: application/json" \
  -H "X-Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "name": "my-model",
    "version": "1.0.0",
    "url": "https://huggingface.co/username/model-name"
  }'
```

#### Check System Health

```bash
curl http://localhost:8080/health/components
```

---

## For Security Auditors

### Security Features

1. **Authentication**: JWT with 10-hour expiration, bcrypt password hashing
2. **Authorization**: Role-based access control (4 roles)
3. **Rate Limiting**: 10 login attempts/min, 1000 API calls per token
4. **Audit Logging**: All operations logged with timestamps
5. **Encryption**: TLS in transit, AES-256 at rest

### Security Documentation

- See `SECURITY_CASE.md` for comprehensive security analysis
- STRIDE threat modeling completed
- OWASP Top 10 mitigations implemented
- 4 vulnerabilities discovered and fixed

### Testing Security

```bash
# Run all tests including security tests
pytest tests/ -v

# Run Selenium UI tests
pytest tests/test_selenium_ui.py -v

# Check for known vulnerabilities
pip-audit

# Static analysis
bandit -r src/
```

---

## For QA Testers

### Running Tests

```bash
# All tests with coverage
pytest --cov=src --cov-report=html tests/

# Specific test file
pytest tests/test_selenium_ui.py -v

# Coverage report will be in htmlcov/index.html
```

### Manual Testing Checklist

- [ ] User registration (admin creates user)
- [ ] Login with valid credentials
- [ ] Login with invalid credentials (should fail)
- [ ] Search for packages
- [ ] Upload package (as uploader)
- [ ] View package details
- [ ] Check health dashboard
- [ ] View audit trail
- [ ] Test responsive design (mobile, tablet, desktop)
- [ ] Test keyboard navigation
- [ ] Test screen reader compatibility

---

## Troubleshooting

### Application won't start

```bash
# Check Python version (requires 3.10+)
python --version

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Check environment variables
env | grep -E '(DATABASE_URL|JWT_SECRET|SECRET_KEY)'
```

### Database errors

```bash
# Reset database
python -c "from database import db_manager; db_manager.reset_database(); from database import init_db; init_db()"
```

### Authentication fails

```bash
# Verify default admin user exists
python -c "from database import get_db, User; session = get_db(); user = session.query(User).filter_by(username='admin').first(); print(f'Admin exists: {user is not None}')"

# If admin doesn't exist, reinitialize
python src/database.py
```

### AWS deployment issues

See `DEPLOYMENT_GUIDE.md` Section "Troubleshooting" for detailed solutions.

---

## Important Files

| File | Purpose |
|------|---------|
| `src/app_enhanced.py` | Main Flask application |
| `src/database.py` | Database models and setup |
| `src/auth_service.py` | Authentication logic |
| `src/auth_middleware.py` | Authorization middleware |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container configuration |
| `.github/workflows/aws_build.yml` | CI/CD pipeline |
| `DEPLOYMENT_GUIDE.md` | AWS deployment instructions |
| `SECURITY_CASE.md` | Security analysis |

---

## Support

- **Documentation**: See `GEORGE_MODULE_README.md` for detailed information
- **Deployment**: See `DEPLOYMENT_GUIDE.md`
- **Security**: See `SECURITY_CASE.md`
- **GitHub**: https://github.com/ECE461_Team17/ECE461_Team17_Phase2

---

**Quick Reference Card**

```
┌─────────────────────────────────────────────┐
│      ECE461 Package Registry - Quick Ref    │
├─────────────────────────────────────────────┤
│ Local URL:    http://localhost:8080         │
│ Default User: admin / admin123!             │
│                                             │
│ Auth Endpoint:  PUT /authenticate           │
│ Search:         GET /packages/byRegEx       │
│ Upload:         POST /package               │
│ Health:         GET /health/components      │
│ Audit:          GET /artifact/.../audit     │
│                                             │
│ Roles: admin, uploader, searcher, downloader│
│ Token Expiry: 10 hours                      │
│ API Call Limit: 1000 per token             │
└─────────────────────────────────────────────┘
```

**Version**: 1.0  
**Last Updated**: January 15, 2024




