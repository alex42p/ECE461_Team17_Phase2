Build Docker image, push to ECR, and deploy to EC2

Overview
--------
This repository includes a GitHub Actions workflow that will build a Docker image, push it to Amazon ECR, and (optionally) SSH into an EC2 instance to pull and restart the container.

What I added
------------
- `Dockerfile` - minimal container build for this Python project.
- `.github/workflows/ci-cd.yml` - GitHub Actions workflow to build, tag, and push image to ECR and then SSH-deploy.
- `scripts/ec2_deploy.sh` - remote helper script to pull and restart the container on EC2.
- `scripts/ec2_service_example.service` - example systemd unit you can use to run the container.

AWS and GitHub secrets required
------------------------------
Set the following repository secrets in GitHub (Settings -> Secrets):

- `AWS_REGION` - e.g. `us-east-1`
- One of the following for AWS credentials:
  - `AWS_ROLE_TO_ASSUME` (ARN) and configure `aws-actions/configure-aws-credentials` to assume it, OR
  - `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` (less recommended)
- `EC2_HOSTNAME` - public DNS or IP of your EC2 instance (optional; only required if you want automatic SSH deploy)
- `EC2_USER` - SSH username (e.g., `ubuntu` or `ec2-user`)
- `EC2_SSH_KEY` - private SSH key contents (the action uses it to SSH)
- `EC2_SSH_PORT` - optional (defaults to 22)

Notes on IAM and ECR setup
-------------------------
- Create an ECR repository named `ece461-team17-phase2` (or change `IMAGE_NAME` in the workflow).
- Grant the GitHub Actions role/credentials permission to push to ECR (e.g., `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:CompleteLayerUpload`, `ecr:UploadLayerPart`, `ecr:GetAuthorizationToken`, `ecr:DescribeRepositories`, `sts:GetCallerIdentity`).

EC2 preparation
---------------
On the EC2 instance you will need:
- Docker installed and working
- awscli installed and configured (if using the `scripts/ec2_deploy.sh` approach)
- The instance must have either:
  - an IAM role that allows ECR access (recommended), OR
  - AWS credentials configured in `~/.aws/credentials` on the host

Alternatively, to keep secrets off the host, you can configure an IAM instance profile with ECR permissions.

How the workflow works
----------------------
1. Checkout code.
2. Configure AWS credentials (either via role or access keys).
3. Login to ECR.
4. Build Docker image and tag with `latest` and commit SHA.
5. Push both tags to ECR.
6. If `EC2_HOSTNAME` secret is present, SSH into the EC2 host and run a simple pull-and-run sequence.

Security
--------
- Use least-privilege IAM policies and prefer roles/instance profiles over long-lived keys.
- Store the SSH private key in GitHub Secrets and rotate it regularly.

Customization
-------------
- Adjust exposed ports and `docker run` flags in the workflow and `ec2_deploy.sh` to fit your application.
- If you prefer not to SSH, consider using AWS CodeDeploy, SSM Run Command, or ECS + Fargate for managed deployments.

Troubleshooting
---------------
- If docker login fails, ensure the credentials have `ecr:GetAuthorizationToken` and the region is correct.
- If SSH deploy fails, test your key connectivity and security group inbound rules.

