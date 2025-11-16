# AWS Deployment Guide - ECE461 Package Registry

## Overview

This guide covers deploying the ECE461 Package Registry to AWS using a multi-component architecture with EC2, S3, RDS, and supporting services.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [AWS Services Setup](#aws-services-setup)
4. [Environment Configuration](#environment-configuration)
5. [Deployment Steps](#deployment-steps)
6. [CI/CD Pipeline](#cicd-pipeline)
7. [Monitoring & Maintenance](#monitoring--maintenance)
8. [Troubleshooting](#troubleshooting)
9. [Cost Management](#cost-management)

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Internet                              │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│                    Application Load Balancer               │
│                    (Optional - for HA)                     │
└───────────────────────┬───────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────┐
        │      VPC (10.0.0.0/16)            │
        │  ┌────────────────────────────┐   │
        │  │   Public Subnet            │   │
        │  │   (10.0.1.0/24)            │   │
        │  │  ┌──────────────────────┐  │   │
        │  │  │  EC2 Instance        │  │   │
        │  │  │  - Flask App         │  │   │
        │  │  │  - Docker Container  │  │   │
        │  │  └──────────────────────┘  │   │
        │  └────────────────────────────┘   │
        │                                    │
        │  ┌────────────────────────────┐   │
        │  │   Private Subnet           │   │
        │  │   (10.0.2.0/24)            │   │
        │  │  ┌──────────────────────┐  │   │
        │  │  │  RDS PostgreSQL      │  │   │
        │  │  │  (db.t3.micro)       │  │   │
        │  │  └──────────────────────┘  │   │
        │  └────────────────────────────┘   │
        └────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────┐
        │      Amazon S3 Buckets             │
        │  - ece461-artifacts                │
        │  - ece461-backups                  │
        └────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────┐
        │    CloudWatch & Monitoring         │
        │  - Logs                            │
        │  - Metrics                         │
        │  - Alarms                          │
        └────────────────────────────────────┘
```

### Component Responsibilities

- **EC2 Instance**: Runs the Flask application in a Docker container
- **RDS PostgreSQL**: Stores user accounts, package metadata, audit logs
- **S3 Buckets**: Stores package artifacts (models, datasets, code)
- **CloudWatch**: Centralized logging and monitoring
- **IAM Roles**: Secure access control between services
- **Security Groups**: Network-level access control

---

## Prerequisites

### Required Tools

1. **AWS Account** with free tier eligibility
2. **AWS CLI** v2.x installed and configured
3. **Docker** for local testing
4. **Git** for repository management
5. **Python 3.10+** for local development

### AWS Credentials Setup

```bash
# Configure AWS CLI
aws configure

# Verify credentials
aws sts get-caller-identity
```

---

## AWS Services Setup

### 1. VPC and Networking

```bash
# Create VPC
aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=ece461-vpc}]'

# Note the VPC ID (e.g., vpc-xxx)
VPC_ID="vpc-xxx"

# Create Internet Gateway
aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=ece461-igw}]'

# Note the IGW ID
IGW_ID="igw-xxx"

# Attach IGW to VPC
aws ec2 attach-internet-gateway \
  --vpc-id $VPC_ID \
  --internet-gateway-id $IGW_ID

# Create Public Subnet
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=ece461-public-subnet}]'

# Note the Subnet ID
PUBLIC_SUBNET_ID="subnet-xxx"

# Create Private Subnet
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=ece461-private-subnet}]'

PRIVATE_SUBNET_ID="subnet-xxx"

# Create and configure Route Table
aws ec2 create-route-table \
  --vpc-id $VPC_ID \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=ece461-public-rt}]'

ROUTE_TABLE_ID="rtb-xxx"

# Add route to Internet Gateway
aws ec2 create-route \
  --route-table-id $ROUTE_TABLE_ID \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id $IGW_ID

# Associate route table with public subnet
aws ec2 associate-route-table \
  --subnet-id $PUBLIC_SUBNET_ID \
  --route-table-id $ROUTE_TABLE_ID
```

### 2. Security Groups

```bash
# Create Security Group for EC2
aws ec2 create-security-group \
  --group-name ece461-ec2-sg \
  --description "Security group for EC2 web server" \
  --vpc-id $VPC_ID

EC2_SG_ID="sg-xxx"

# Allow SSH (port 22)
aws ec2 authorize-security-group-ingress \
  --group-id $EC2_SG_ID \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0

# Allow HTTP (port 80)
aws ec2 authorize-security-group-ingress \
  --group-id $EC2_SG_ID \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

# Allow HTTPS (port 443)
aws ec2 authorize-security-group-ingress \
  --group-id $EC2_SG_ID \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# Allow app port (8080)
aws ec2 authorize-security-group-ingress \
  --group-id $EC2_SG_ID \
  --protocol tcp \
  --port 8080 \
  --cidr 0.0.0.0/0

# Create Security Group for RDS
aws ec2 create-security-group \
  --group-name ece461-rds-sg \
  --description "Security group for RDS database" \
  --vpc-id $VPC_ID

RDS_SG_ID="sg-xxx"

# Allow PostgreSQL from EC2 security group only
aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG_ID \
  --protocol tcp \
  --port 5432 \
  --source-group $EC2_SG_ID
```

### 3. IAM Roles and Policies

```bash
# Create IAM role for EC2
aws iam create-role \
  --role-name ece461-ec2-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach policies for S3 access
aws iam attach-role-policy \
  --role-name ece461-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

# Attach policies for CloudWatch
aws iam attach-role-policy \
  --role-name ece461-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

# Attach policies for ECR (to pull Docker images)
aws iam attach-role-policy \
  --role-name ece461-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly

# Create instance profile
aws iam create-instance-profile \
  --instance-profile-name ece461-ec2-profile

# Add role to instance profile
aws iam add-role-to-instance-profile \
  --instance-profile-name ece461-ec2-profile \
  --role-name ece461-ec2-role
```

### 4. S3 Buckets

```bash
# Create bucket for artifacts
aws s3 mb s3://ece461-artifacts-team17

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket ece461-artifacts-team17 \
  --versioning-configuration Status=Enabled

# Set lifecycle policy (optional - move old versions to Glacier)
aws s3api put-bucket-lifecycle-configuration \
  --bucket ece461-artifacts-team17 \
  --lifecycle-configuration file://lifecycle-policy.json

# Block public access
aws s3api put-public-access-block \
  --bucket ece461-artifacts-team17 \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### 5. RDS PostgreSQL Database

```bash
# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name ece461-db-subnet-group \
  --db-subnet-group-description "Subnet group for ECE461 database" \
  --subnet-ids $PRIVATE_SUBNET_ID subnet-xxx  # Need 2 subnets in different AZs

# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier ece461-postgres \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 14.7 \
  --master-username admin \
  --master-user-password 'YourSecurePassword123!' \
  --allocated-storage 20 \
  --vpc-security-group-ids $RDS_SG_ID \
  --db-subnet-group-name ece461-db-subnet-group \
  --backup-retention-period 7 \
  --no-publicly-accessible \
  --storage-encrypted

# Wait for database to be available
aws rds wait db-instance-available --db-instance-identifier ece461-postgres

# Get database endpoint
aws rds describe-db-instances \
  --db-instance-identifier ece461-postgres \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text
```

### 6. EC2 Instance

```bash
# Create EC2 key pair for SSH access
aws ec2 create-key-pair \
  --key-name ece461-keypair \
  --query 'KeyMaterial' \
  --output text > ece461-keypair.pem

chmod 400 ece461-keypair.pem

# Launch EC2 instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \  # Amazon Linux 2 AMI (update for your region)
  --instance-type t2.micro \
  --key-name ece461-keypair \
  --security-group-ids $EC2_SG_ID \
  --subnet-id $PUBLIC_SUBNET_ID \
  --iam-instance-profile Name=ece461-ec2-profile \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ece461-server}]' \
  --user-data file://user-data.sh

# Note the Instance ID
INSTANCE_ID="i-xxx"

# Allocate and associate Elastic IP (optional but recommended)
aws ec2 allocate-address --domain vpc
# Note the Allocation ID
ALLOCATION_ID="eipalloc-xxx"

aws ec2 associate-address \
  --instance-id $INSTANCE_ID \
  --allocation-id $ALLOCATION_ID
```

### 7. ECR Repository

```bash
# Create ECR repository
aws ecr create-repository \
  --repository-name ece461-team17-phase2 \
  --image-scanning-configuration scanOnPush=true

# Get repository URI
aws ecr describe-repositories \
  --repository-names ece461-team17-phase2 \
  --query 'repositories[0].repositoryUri' \
  --output text
```

---

## Environment Configuration

### Environment Variables

Create `.env` file on EC2 instance:

```bash
# Database Configuration
DATABASE_URL=postgresql://admin:YourSecurePassword123!@ece461-postgres.xxx.us-east-1.rds.amazonaws.com:5432/ece461

# AWS Configuration
AWS_REGION=us-east-1
AWS_S3_BUCKET=ece461-artifacts-team17

# Application Configuration
FLASK_ENV=production
SECRET_KEY=your-super-secret-key-change-this
JWT_SECRET=your-jwt-secret-key-change-this

# External APIs
GITHUB_TOKEN=your_github_token
HF_TOKEN=your_huggingface_token

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/ece461/app.log
ENABLE_CLOUDWATCH=true

# Security
BCRYPT_LOG_ROUNDS=12
```

### User Data Script

Create `user-data.sh` for EC2 initialization:

```bash
#!/bin/bash
set -e

# Update system
yum update -y

# Install Docker
amazon-linux-extras install docker -y
systemctl start docker
systemctl enable docker
usermod -a -G docker ec2-user

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Create application directory
mkdir -p /opt/ece461
cd /opt/ece461

# Create log directory
mkdir -p /var/log/ece461
chown ec2-user:ec2-user /var/log/ece461

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Pull latest image
docker pull <account-id>.dkr.ecr.us-east-1.amazonaws.com/ece461-team17-phase2:latest

# Run container
docker run -d \
  --name ece461-app \
  --restart unless-stopped \
  -p 8080:8080 \
  -e DATABASE_URL="$DATABASE_URL" \
  -e AWS_REGION="us-east-1" \
  -e AWS_S3_BUCKET="ece461-artifacts-team17" \
  --log-driver=awslogs \
  --log-opt awslogs-group=/aws/ece461/app \
  --log-opt awslogs-stream=$(hostname) \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/ece461-team17-phase2:latest
```

---

## Deployment Steps

### Initial Deployment

1. **Clone Repository**
   ```bash
   git clone https://github.com/ECE461_Team17/ECE461_Team17_Phase2.git
   cd ECE461_Team17_Phase2
   ```

2. **Build and Test Locally**
   ```bash
   docker build -t ece461-app .
   docker run -p 8080:8080 ece461-app
   ```

3. **Push to ECR**
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
   
   docker tag ece461-app:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/ece461-team17-phase2:latest
   
   docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/ece461-team17-phase2:latest
   ```

4. **SSH to EC2 and Deploy**
   ```bash
   ssh -i ece461-keypair.pem ec2-user@<ec2-public-ip>
   
   # Pull and run
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
   
   docker pull <account-id>.dkr.ecr.us-east-1.amazonaws.com/ece461-team17-phase2:latest
   
   docker stop ece461-app || true
   docker rm ece461-app || true
   
   docker run -d --name ece461-app --restart unless-stopped -p 8080:8080 \
     -e DATABASE_URL="$DATABASE_URL" \
     <account-id>.dkr.ecr.us-east-1.amazonaws.com/ece461-team17-phase2:latest
   ```

### Database Initialization

```bash
# SSH to EC2
ssh -i ece461-keypair.pem ec2-user@<ec2-public-ip>

# Run database initialization
docker exec -it ece461-app python src/database.py
```

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/aws_build.yml`) automates:

1. **Build**: Creates Docker image
2. **Test**: Runs pytest suite
3. **Push**: Uploads to ECR
4. **Deploy**: SSHs to EC2 and updates container

### Required GitHub Secrets

```
AWS_REGION=us-east-1
AWS_ROLE_TO_ASSUME=arn:aws:iam::xxx:role/GithubActionsRole
EC2_HOSTNAME=<ec2-public-ip>
EC2_USER=ec2-user
EC2_SSH_KEY=<contents-of-ece461-keypair.pem>
EC2_SSH_PORT=22
```

---

## Monitoring & Maintenance

### CloudWatch Logs

```bash
# Create log group
aws logs create-log-group --log-group-name /aws/ece461/app

# Set retention
aws logs put-retention-policy \
  --log-group-name /aws/ece461/app \
  --retention-in-days 30
```

### CloudWatch Alarms

```bash
# CPU Utilization Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name ece461-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID

# Disk Space Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name ece461-low-disk \
  --alarm-description "Alert when disk space below 20%" \
  --metric-name DiskSpaceUtilization \
  --namespace CWAgent \
  --statistic Average \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold
```

### Health Checks

```bash
# Application health check
curl http://<ec2-public-ip>:8080/health

# Component health check
curl http://<ec2-public-ip>:8080/health/components
```

---

## Troubleshooting

### Common Issues

#### 1. Cannot Connect to EC2

**Problem**: SSH connection refused

**Solution**:
```bash
# Check security group allows SSH
aws ec2 describe-security-groups --group-ids $EC2_SG_ID

# Check instance is running
aws ec2 describe-instance-status --instance-ids $INSTANCE_ID
```

#### 2. Database Connection Failed

**Problem**: Application cannot connect to RDS

**Solution**:
```bash
# Verify RDS is accessible from EC2
ssh -i ece461-keypair.pem ec2-user@<ec2-public-ip>
telnet <rds-endpoint> 5432

# Check security group rules
aws ec2 describe-security-groups --group-ids $RDS_SG_ID
```

#### 3. Docker Container Crashes

**Problem**: Container exits immediately

**Solution**:
```bash
# Check container logs
docker logs ece461-app

# Check environment variables
docker exec ece461-app env

# Run interactively to debug
docker run -it --rm <image> /bin/bash
```

#### 4. Out of Memory

**Problem**: EC2 instance running out of memory

**Solution**:
```bash
# Add swap space
sudo dd if=/dev/zero of=/swapfile bs=1G count=2
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Cost Management

### Free Tier Limits

- **EC2**: 750 hours/month of t2.micro
- **RDS**: 750 hours/month of db.t3.micro
- **S3**: 5GB storage, 20,000 GET requests, 2,000 PUT requests
- **CloudWatch**: 10 custom metrics, 10 alarms

### Cost Optimization Tips

1. **Stop EC2 when not in use**:
   ```bash
   aws ec2 stop-instances --instance-ids $INSTANCE_ID
   ```

2. **Use S3 lifecycle policies** to move old objects to Glacier

3. **Set up billing alerts**:
   ```bash
   aws budgets create-budget \
     --account-id <account-id> \
     --budget file://budget.json \
     --notifications-with-subscribers file://notifications.json
   ```

4. **Monitor costs**:
   ```bash
   aws ce get-cost-and-usage \
     --time-period Start=2024-01-01,End=2024-01-31 \
     --granularity MONTHLY \
     --metrics BlendedCost
   ```

### Budget Alert Configuration

Create `budget.json`:
```json
{
  "BudgetName": "ECE461-Monthly-Budget",
  "BudgetLimit": {
    "Amount": "10",
    "Unit": "USD"
  },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
```

---

## Backup and Recovery

### Database Backups

```bash
# Manual snapshot
aws rds create-db-snapshot \
  --db-instance-identifier ece461-postgres \
  --db-snapshot-identifier ece461-manual-snapshot-$(date +%Y%m%d)

# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier ece461-postgres-restored \
  --db-snapshot-identifier ece461-manual-snapshot-20240115
```

### S3 Backups

```bash
# Enable versioning (already done in setup)
# To restore a deleted object
aws s3api list-object-versions --bucket ece461-artifacts-team17 --prefix path/to/file
aws s3api get-object --bucket ece461-artifacts-team17 --key path/to/file --version-id <version-id> restored-file
```

---

## Security Best Practices

1. **Use IAM roles** instead of access keys on EC2
2. **Enable MFA** for AWS root account
3. **Rotate database passwords** regularly
4. **Use Parameter Store** or Secrets Manager for sensitive data
5. **Enable CloudTrail** for audit logging
6. **Regular security updates** on EC2 instances
7. **Use VPC endpoints** for S3 to avoid internet traffic
8. **Enable encryption** at rest for RDS and S3

---

## Support and Resources

- AWS Documentation: https://docs.aws.amazon.com/
- Flask Documentation: https://flask.palletsprojects.com/
- Docker Documentation: https://docs.docker.com/
- Team Repository: https://github.com/ECE461_Team17/ECE461_Team17_Phase2




