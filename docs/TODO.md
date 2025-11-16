TODO.md - Phase 2 Implementation Plan
Project Overview
Transform Phase 1 CLI tool into a web-based registry system hosted on AWS with enhanced security, authentication, and advanced model management features.

___

JOEY'S MODULE: Core REST API & Storage Infrastructure
1. Database & Storage Setup

Task 1.1: Design and implement database schema

Choose between RDS (PostgreSQL/MySQL) or DynamoDB for metadata storage
Design tables: packages, users, audit_logs, lineage_relationships
Set up S3 buckets for model artifact storage (separate buckets for models/datasets/code)
Implementation: Create migration scripts and seed data


Task 1.2: Implement storage layer abstraction

Create StorageService class to handle S3 operations
Create DatabaseService class for metadata CRUD operations
Implement connection pooling and error handling
Add retry logic for AWS service calls



2. Baseline API Endpoints - CRUD Operations

Task 2.1: POST /artifact/{artifact_type} - Upload/Ingest

Accept HuggingFace URLs and validate format
Download artifacts from HuggingFace to S3
Run Phase 1 scoring metrics (integrate existing code)
Check minimum score threshold (0.5 on all metrics) before ingestion
Store metadata in database with generated artifact_id
Return 201 on success, 424 if disqualified


Task 2.2: GET /artifacts/{artifact_type}/{id} - Retrieve

Query database for artifact metadata by ID
Generate pre-signed S3 URLs for artifact downloads
Support optional query params for partial downloads (weights only, etc.)
Return 200 with full metadata, 404 if not found


Task 2.3: PUT /artifacts/{artifact_type}/{id} - Update

Validate that name and ID match existing artifact
Download new artifact from provided URL
Update S3 storage and database metadata
Preserve version history (store old versions with timestamps)


Task 2.4: DELETE /artifacts/{artifact_type}/{id} - Delete

Mark artifact as deleted in database (soft delete)
Archive S3 objects to glacier storage (optional)
Update audit logs


Task 2.5: DELETE /reset - System Reset

Clear all database tables
Delete all S3 objects (or move to archive bucket)
Recreate default admin user
Return system to initial state



3. Search & Enumeration

Task 3.1: POST /artifacts - List/Search with filters

Implement pagination using offset parameter
Support filtering by name (using ArtifactQuery)
Support filtering by artifact type
Limit results to prevent DoS (max 100 per page)
Return 413 if too many results


Task 3.2: POST /artifact/byRegEx - Regex search

Validate regex pattern for safety
Search across artifact names AND README text
Rank results by relevance (search scoring)
Return 400 for invalid regex


Task 3.3: GET /artifact/byName/{name} - Name-based lookup

Return all artifacts matching exact name
Include all versions/revisions
Sort by creation date (newest first)



4. Testing & Documentation

Task 4.1: Write unit tests for storage layer (60%+ coverage)
Task 4.2: Write integration tests for CRUD endpoints
Task 4.3: Document API responses with example payloads
Task 4.4: Create Postman collection for manual testing

___

ALEX'S MODULE: Advanced Features & Metrics
1. New Metrics Implementation

Task 1.1: Reproducibility Metric

Clone model repo to temporary location
Attempt to run demonstration code from model card
Use subprocess/Docker to execute safely
Score: 0 (no code/doesn't run), 0.5 (runs with debugging), 1 (runs perfectly)
Implement timeout mechanism (5 min max)


Task 1.2: Reviewedness Metric

Query GitHub API for linked repository
Use GraphQL to fetch PR data for all commits
Calculate ratio: (commits via reviewed PRs) / (total commits)
Return -1 if no GitHub repo linked
Cache results to avoid rate limiting


Task 1.3: TreeScore Metric (Lineage-based)

Parse config.json to extract parent model references
Build dependency graph recursively
Calculate average score of all parent models
Handle circular dependencies gracefully
Cache lineage graphs in database



2. Lineage & Dependency Management

Task 2.1: GET /artifact/model/{id}/lineage - Build lineage graph

Parse model config.json and model_index.json
Identify parent models, training datasets, base models
Create nodes (ArtifactLineageNode) and edges (ArtifactLineageEdge)
Return complete graph in required format
Handle models with no lineage (return empty graph)


Task 2.2: GET /artifact/{artifact_type}/{id}/cost - Size analysis

Calculate standalone artifact download size
If dependency=true, recursively compute all dependency sizes
Return breakdown showing per-artifact costs
Format: {"artifact_id": {"standalone_cost": X, "total_cost": Y}}


Task 2.3: POST /artifact/model/{id}/license-check - Compatibility analysis

Fetch GitHub repo license from LICENSE file
Fetch model license from HuggingFace metadata
Use ModelGo paper logic for compatibility matrix
Check "fine-tune + inference" use case specifically
Return boolean compatibility result



3. Model Rating Enhancements

Task 3.1: GET /artifact/model/{id}/rate - Enhanced rating

Integrate new metrics (reproducibility, reviewedness, tree_score)
Update net_score calculation with new weights
Ensure all metrics return proper latency measurements
Handle metric failures gracefully (return 500 with details)


Task 3.2: Update Phase 1 metrics for consistency

Ensure all metrics follow MetricResult format
Add proper error handling and timeouts
Update weight distribution for net_score calculation
Test with various HuggingFace models



4. Performance Optimization

Task 4.1: Implement caching layer

Use ElastiCache (Redis) for frequently accessed metadata
Cache HuggingFace API responses (1 hour TTL)
Cache GitHub API responses (6 hours TTL)
Cache computed metrics (24 hours TTL, invalidate on update)


Task 4.2: Optimize parallel metric computation

Review existing concurrent.futures implementation
Add configurable worker pool size based on EC2 instance type
Implement circuit breaker for failing external APIs
Add performance monitoring/logging



5. Testing & Documentation

Task 5.1: Write unit tests for new metrics (60%+ coverage)
Task 5.2: Integration tests for lineage and cost endpoints
Task 5.3: Performance benchmarking tests (measure P50, P99 latencies)
Task 5.4: Document new metric calculations and formulas

___

GEORGE'S MODULE: Security, Deployment & Observability
1. Authentication & Authorization (Security Track)

Task 1.1: User management system

Implement user registration (admin-only operation)
Store passwords using bcrypt with proper salting
Create user roles: admin, uploader, searcher, downloader
Implement user deletion (self + admin privileges)


Task 1.2: JWT-based authentication

PUT /authenticate - Generate JWT tokens
Validate username + password against database
Generate JWT with 10-hour expiration
Include usage counter in token (max 1000 API calls)
Return 401 for invalid credentials


Task 1.3: Authorization middleware

Create Flask middleware to validate X-Authorization header
Verify JWT signature and expiration
Check permission requirements for each endpoint
Track API call count per token
Return 403 for insufficient permissions


Task 1.4: Sensitive model protection

Add is_sensitive flag to artifact metadata
Support uploading JavaScript monitoring programs
Execute Node.js script before sensitive model downloads
Pass MODEL_NAME, UPLOADER_USERNAME, DOWNLOADER_USERNAME, ZIP_FILE_PATH
Reject download if script exits non-zero



2. Security Analysis & Threat Modeling

Task 2.1: ThreatModeler design

Create system architecture diagrams
Identify all components and data flows
Mark trust boundaries clearly
Document all external API interactions


Task 2.2: STRIDE analysis

Analyze each component for: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege
Document threats in threat matrix
Create dataflow diagrams with trust boundaries
Prioritize threats by severity


Task 2.3: OWASP Top 10 mitigation

A01 (Broken Access Control): Implement RBAC, validate all permissions
A02 (Cryptographic Failures): Use TLS, encrypt sensitive data at rest
A03 (Injection): Parameterize all SQL queries, validate regex inputs
A04 (Insecure Design): Follow security design patterns
A05 (Security Misconfiguration): Harden AWS security groups, disable debug mode
A07 (Authentication Failures): Implement rate limiting, strong password policy
A08 (Software Data Integrity): Verify artifact checksums, sign downloads
Document 4+ vulnerabilities found and fixed with "Five Whys" analysis



3. AWS Deployment & Infrastructure

Task 3.1: Multi-component AWS architecture

Set up EC2 instance for API server (t2.micro/t3.micro)
Configure S3 buckets with versioning and lifecycle policies
Set up RDS instance (db.t3.micro) OR DynamoDB tables
Configure VPC, subnets, and security groups
Set up IAM roles with least-privilege policies


Task 3.2: CI/CD Pipeline (GitHub Actions)

Update .github/workflows/main.yml for automated testing
Create deployment workflow triggered on merge to main
Build Docker container and push to ECR
Deploy to EC2 using SSH or CodeDeploy
Run smoke tests post-deployment


Task 3.3: Cost monitoring and alerting

Set up AWS Budgets with alerts at 50%, 80%, 100% of free tier
Create CloudWatch billing alarms
Estimate costs using spreadsheet for all services
Document free tier limits and usage tracking



4. Observability & Monitoring

Task 4.1: Health monitoring endpoints

GET /health - Simple liveness check (return 200)
GET /health/components - Detailed component health
Collect metrics: uptime, request counts, error rates
Monitor: S3 connectivity, database connectivity, external API status
Return status: ok/degraded/critical/unknown


Task 4.2: System health dashboard

Create web UI page displaying health metrics
Show real-time data for last hour (configurable window)
Display per-route request statistics
Show component-level health with issue counts
Provide log file access/references


Task 4.3: Logging infrastructure

Configure structured logging (JSON format)
Log all API requests with: timestamp, user, endpoint, status
Log all errors with stack traces
Store logs in CloudWatch Logs
Set up log retention policies (30 days)


Task 4.4: Audit trail system

GET /artifact/{artifact_type}/{id}/audit - Retrieve audit trail
Log all CRUD operations: CREATE, UPDATE, DOWNLOAD, RATE, AUDIT
Store: user, timestamp, artifact, action type
Support download history for sensitive models
Format per ArtifactAuditEntry schema



5. Frontend & User Interface

Task 5.1: Design web interface layout

Create mockups for: home page, search page, artifact detail page
Plan navigation and user flows
Ensure mobile-responsive design


Task 5.2: Implement web UI pages

Update templates/index.html with proper structure
Create artifact search interface with filters
Create artifact detail page showing all metadata
Create admin panel for user management (if auth implemented)
Style with CSS framework (Bootstrap/Tailwind)


Task 5.3: ADA Compliance (WCAG 2.1 Level AA)

Add proper ARIA labels and roles
Ensure keyboard navigation works
Verify color contrast ratios meet requirements
Add alt text for all images
Test with accessibility tools (WAVE, axe DevTools)


Task 5.4: Selenium automated UI tests

Test search functionality
Test artifact upload flow
Test authentication (if implemented)
Test responsive design on different viewports
Integrate into CI/CD pipeline



6. Documentation & Delivery

Task 6.1: Security case documentation

Document threat model with diagrams
Document STRIDE analysis results
Document 4+ vulnerabilities found and mitigations
Perform "Five Whys" root cause analysis
Document excluded risks with justifications


Task 6.2: Deployment documentation

Write deployment guide for AWS setup
Document environment variables and configuration
Create troubleshooting guide
Document backup and recovery procedures


Task 6.3: OpenAPI compliance verification

Test all endpoints against openapi_spec.yaml
Ensure request/response formats match exactly
Verify HTTP status codes are correct
Test with autograder examples

___

SHARED RESPONSIBILITIES (All Team Members)
1. Weekly Milestones & Project Management

Update GitHub Project Board weekly
Submit milestone reports with:

Completed tasks
Actual time spent per person
Blockers and dependencies
Screenshots of progress


Attend team sync meetings (2x per week recommended)

2. Integration & Testing

Integration testing between modules
End-to-end testing of complete workflows
Performance testing (especially for search and large artifacts)
Load testing with multiple concurrent clients

3. Code Quality

Follow Python type annotations (use mypy)
Follow PEP 8 style guide (use flake8)
Write meaningful commit messages
Conduct code reviews on all PRs
Maintain 60%+ overall code coverage

4. Deliverables

Delivery 1 (Mid-project): CI/CD + CRUD + Ingest + partial Enumerate working
Delivery 2 (Final): All baseline features + chosen extended track + security case
Postmortem: Reflection on plan vs. execution with lessons learned


PRIORITY LEVELS
CRITICAL (Must Complete for Passing Grade)

All baseline CRUD operations
Model ingestion with scoring
Search/enumerate functionality
AWS deployment with CI/CD
OpenAPI compliance
Basic security measures

HIGH (Strongly Recommended)

One extended track (Security/Performance/High-assurance)
Authentication system
Health monitoring
Test coverage ≥60%
Web UI with basic functionality

MEDIUM (Nice to Have)

Advanced search features
Complete observability dashboard
ADA-compliant UI
Performance optimizations
Advanced caching

LOW (If Time Permits)

Multiple extended tracks
Advanced analytics
Package confusion detection
Disaster recovery features


ESTIMATED TIMELINE (9 Weeks Total)
Week 1-2: Planning, AWS setup, database design, basic API skeleton
Week 3-4: Core CRUD endpoints, authentication, metric implementation
Week 5-6: Advanced features, lineage, web UI, testing
Week 7: Delivery 1 checkpoint, integration testing, bug fixes
Week 8: Extended features, security analysis, final testing
Week 9: Documentation, postmortem, final delivery

RISK MITIGATION
Risk 1: AWS costs exceed free tier

Mitigation: Set up billing alerts at 50%, use cost calculator, shutdown non-essential resources when not testing

Risk 2: External API rate limiting (HuggingFace, GitHub)

Mitigation: Implement caching, request throttling, graceful degradation

Risk 3: Metric computation takes too long

Mitigation: Set timeouts, implement async processing, show partial results

Risk 4: Team member unavailability

Mitigation: Document code thoroughly, conduct regular knowledge transfer, maintain bus factor >1 per module

Risk 5: Integration issues between modules

Mitigation: Define clear interfaces early, use mocking for parallel development, daily integration testing

___

PROMPTS FOR CLAUDE

**Prompt 1**: Background Context
I'm working on Phase 2 of a software engineering project to build a trustworthy ML model registry. Here's the context:

**Phase 1 (Completed - CLI Tool)**:
We built a command-line tool that:
- Accepts a text file with URLs (HuggingFace models, datasets, GitHub repos)
- Fetches metadata from HuggingFace and GitHub APIs
- Computes 8 quality metrics in parallel (license, bus factor, code quality, dataset quality, ramp-up time, performance claims, dataset/code availability, size compatibility)
- Calculates a weighted net score
- Outputs results in NDJSON format
- Includes testing framework with 60%+ coverage

Key Phase 1 files:
- `src/cli.py`: Main entrypoint with install/test/score commands
- `src/metric.py`: Abstract base class for metrics
- `src/concurrency.py`: Parallel metric computation
- `src/entities.py`: HFModel data class
- `src/base.py`: URL parsing utilities
- Individual metric files: `license.py`, `bus_factor.py`, `code_quality.py`, etc.
- `src/huggingface.py` & `src/git_repo.py`: External API integrations

**Phase 2 (Current Goal - Web Service)**:
Transform the CLI into a REST API deployed on AWS with:
- Multiple AWS services (EC2, S3, RDS/DynamoDB, etc.)
- CRUD operations for models, datasets, and code artifacts
- User authentication and authorization (Security track)
- Advanced features like lineage tracking, license checking, cost analysis
- Web-based UI with ADA compliance
- CI/CD pipeline using GitHub Actions
- System health monitoring and observability
- Comprehensive security analysis (STRIDE, OWASP Top 10)

**Architecture**:
- Flask REST API on EC2
- S3 for artifact storage
- RDS/DynamoDB for metadata
- JWT-based authentication
- OpenAPI spec compliance (see attached `openapi_spec.yaml`)

**Team Structure**: 3 members (Joey, Alex, George) splitting work into modules

I'll be providing specific tasks from our TODO.md for implementation guidance. The team needs to complete this in ~9 weeks with a mid-project and final delivery.

What questions do you have about the existing Phase 1 implementation or the Phase 2 goals before I share specific tasks?

___

**Prompt 2**: Joey's Implementation (Core API & Storage)
I'm Joey, working on the Core REST API & Storage Infrastructure module for our ML model registry project. Using the Phase 1 CLI code as a foundation, I need to implement the following:

**My Responsibilities**:

1. **Database & Storage Setup**
   - Design schema for: packages, users, audit_logs, lineage_relationships
   - Decide between RDS (PostgreSQL) vs DynamoDB
   - Set up S3 buckets for model/dataset/code storage
   - Create `StorageService` and `DatabaseService` abstraction layers

2. **Baseline CRUD Endpoints** (following `openapi_spec.yaml`):
   - `POST /artifact/{artifact_type}`: Ingest from HuggingFace URL, run Phase 1 scoring, check 0.5 threshold, store in S3 + DB
   - `GET /artifacts/{artifact_type}/{id}`: Retrieve metadata + generate S3 pre-signed URLs
   - `PUT /artifacts/{artifact_type}/{id}`: Update artifact, maintain version history
   - `DELETE /artifacts/{artifact_type}/{id}`: Soft delete with archival
   - `DELETE /reset`: Clear system to initial state

3. **Search & Enumeration**:
   - `POST /artifacts`: Paginated listing with filters (name, type), max 100 results
   - `POST /artifact/byRegEx`: Search by regex over names + README content
   - `GET /artifact/byName/{name}`: Get all artifacts with exact name match

4. **Integration Requirements**:
   - Integrate Phase 1 scoring from `src/cli.py` → `compute_all_metrics()`
   - Use existing `HFModel`, `HFModelURL` entities
   - Reuse `huggingface.py` and `git_repo.py` for API calls
   - Return proper HTTP status codes per OpenAPI spec

**Questions for you**:
1. What's the best AWS architecture for this? RDS vs DynamoDB trade-offs?
2. How should I structure the Flask app to handle these endpoints cleanly?
3. What's the best way to integrate the existing Phase 1 metric computation without rewriting it?
4. How do I generate unique artifact IDs that match the OpenAPI spec format?
5. What's the best practice for handling S3 uploads/downloads in Flask?
6. How should pagination work - cursor-based or offset-based?

Please provide:
- Recommended project structure for my module
- Key code snippets for storage abstraction layers
- Example implementation for one CRUD endpoint (POST /artifact/{artifact_type})
- Database schema design suggestions
- Error handling patterns for AWS service calls

___

**Prompt 3**: Alex's Implementation (Advanced Features)
I'm Alex, working on Advanced Features & Metrics for our ML model registry. I'm building on top of Joey's CRUD infrastructure and extending the Phase 1 metrics system with new capabilities.

**My Responsibilities**:

1. **New Metrics** (extending Phase 1 `metric.py` interface):
   - **Reproducibility**: Clone repo, attempt to run demo code, score 0/0.5/1 based on success
   - **Reviewedness**: Calculate % of commits via reviewed PRs using GitHub GraphQL API, return -1 if no repo
   - **TreeScore**: Recursively compute average quality of parent models from lineage graph

2. **Lineage & Dependency Analysis**:
   - `GET /artifact/model/{id}/lineage`: Parse config.json to build dependency graph (nodes + edges)
   - `GET /artifact/{artifact_type}/{id}/cost`: Calculate download size with/without dependencies
   - `POST /artifact/model/{id}/license-check`: Check GitHub repo vs model license compatibility

3. **Rating Enhancements**:
   - `GET /artifact/model/{id}/rate`: Add 3 new metrics to existing Phase 1 scoring
   - Update net_score calculation with new weights
   - Ensure proper latency tracking for all metrics

4. **Performance Optimization**:
   - Implement Redis caching for HuggingFace/GitHub API responses
   - Optimize parallel metric computation from Phase 1 `concurrency.py`
   - Add circuit breakers for failing external APIs

**Integration Context**:
- Phase 1 metrics follow this pattern:
```python
  class Metric(ABC):
      @property
      def name(self) -> str: ...
      def compute(self, metadata: dict[str, Any]) -> MetricResult: ...
```
- All metrics return `MetricResult(name, value, details, latency_ms)`
- `concurrency.py` runs metrics in parallel with ThreadPoolExecutor
- Existing metrics: license, bus_factor, code_quality, dataset_quality, ramp_up_time, performance_claims, dataset_and_code, size_score

**Questions**:
1. How should I safely execute demo code for reproducibility? Docker containers?
2. What's the best way to query GitHub GraphQL for PR review data efficiently?
3. How do I parse config.json to extract parent model references for lineage?
4. Should I use recursive depth-first or breadth-first for lineage traversal?
5. How do I integrate with Joey's storage layer to access artifact metadata?
6. What Redis key structure should I use for caching different API responses?
7. How do I update the net_score formula in `ndjson.py` to include new metrics?

Please provide:
- Implementation guide for one new metric (Reproducibility)
- Code structure for lineage graph construction
- Redis caching strategy with TTL recommendations
- Error handling for external API failures
- Testing strategy for metrics that require external services

___

**Prompt 4**: George's Implementation (Security, Deployment & Observability)
I'm George, responsible for Security, Deployment & Observability for our ML model registry. I'm building the security layer around Joey's CRUD APIs and Alex's advanced features, plus deploying everything to AWS.

**My Responsibilities**:

1. **Authentication & Authorization** (Security Track):
   - User management: registration (admin-only), role-based permissions (admin/uploader/searcher/downloader)
   - `PUT /authenticate`: JWT token generation (10-hour expiry, 1000 API call limit)
   - Authorization middleware: Validate X-Authorization header on all protected endpoints
   - Password storage: bcrypt hashing with proper salting
   - Sensitive model protection: Execute JavaScript monitoring scripts before download

2. **Security Analysis**:
   - Create ThreatModeler design with all components and trust boundaries
   - STRIDE analysis: Document threats for each component
   - OWASP Top 10 mitigation: Address A01-A08, document 4+ vulnerabilities found
   - "Five Whys" root cause analysis for discovered vulnerabilities

3. **AWS Deployment**:
   - Multi-component architecture: EC2 + S3 + RDS/DynamoDB + VPC setup
   - GitHub Actions CI/CD: Build Docker, push to ECR, deploy to EC2
   - Security groups, IAM roles with least privilege
   - Cost monitoring: Budgets, CloudWatch alarms, stay within free tier

4. **Observability**:
   - `GET /health`: Liveness check
   - `GET /health/components`: Detailed component health (per OpenAPI spec)
   - System health dashboard: Web UI showing metrics, logs, component status
   - Structured logging: JSON format, CloudWatch integration
   - `GET /artifact/{artifact_type}/{id}/audit`: Full audit trail

5. **Frontend UI**:
   - Web interface for search, artifact details, admin panel
   - WCAG 2.1 Level AA compliance: ARIA labels, keyboard nav, color contrast
   - Selenium automated tests for UI workflows
   - Mobile-responsive design

**Integration Context**:
- Joey's APIs need authentication middleware before processing
- Alex's metrics may fail - need graceful degradation
- Existing `.github/workflows/main.yml` runs pytest, needs deployment steps
- OpenAPI spec requires specific error responses (401, 403, etc.)

**Questions**:
1. What's the best Flask pattern for auth middleware - decorators or before_request?
2. How do I structure JWT tokens to track API call limits?
3. What AWS architecture gives best security posture within free tier constraints?
4. How should I implement rate limiting to prevent DoS?
5. What's the safest way to execute user-provided JavaScript for sensitive models?
6. How do I structure CloudWatch metrics for the health monitoring dashboard?
7. What's the best approach for managing secrets (DB passwords, API keys) in CI/CD?
8. How should I implement the audit trail - separate table or event sourcing?

Please provide:
- Authentication middleware implementation pattern
- JWT token structure with call counting
- AWS CloudFormation/Terraform template suggestions
- Security group configuration recommendations
- Health monitoring endpoint implementation examples
- Selenium test structure for Flask app
- Accessibility checklist for WCAG 2.1 AA compliance
