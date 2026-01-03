# ECE 461 - ML Model Registry (Phase 2)

A trustworthy machine learning model registry system that evaluates and stores ML models, datasets, and code repositories from HuggingFace and GitHub with comprehensive quality metrics.

## Team Members
- Alex Piet
- George Meng
- Joey D'Alessandro

## Overview

This system provides a REST API for managing ML artifacts with automated quality scoring across 12 metrics including license compliance, code quality, reproducibility, and deployment suitability. All artifacts are stored in AWS S3 with metadata in DynamoDB.

## Architecture

- **Backend**: Flask REST API
- **Storage**: AWS S3 (artifacts), DynamoDB (metadata)
- **Scoring Engine**: Multi-threaded metric computation
- **Authentication**: AWS Cognito (configured but not fully implemented)

## Key Features

### Automated Quality Metrics (12 total)
- **Phase 1 Metrics**: License, Ramp-Up Time, Bus Factor, Code Quality, Dataset Quality, Performance Claims, Size Score, Dataset & Code
- **Phase 2 Metrics**: Reproducibility, Reviewedness, Tree Score (parent model quality)

### API Endpoints
- `POST /artifact/{type}` - Upload and score artifacts (model/dataset/code)
- `GET /artifact/byRegex` - Search by regex pattern
- `GET /artifacts/{type}/{id}` - Get artifact metadata
- `GET /artifact/model/{id}/rate` - Get quality scores
- `POST /artifacts` - Query artifacts with filters
- `DELETE /reset` - Reset entire system

### Storage System
- Streams HuggingFace repos directly to S3 (no local disk usage)
- Generates pre-signed URLs for downloads
- Stores package metadata in DynamoDB with full-text search

## Setup

### Prerequisites
```bash
# Required environment variables
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
AWS_DEFAULT_REGION=us-east-2
S3_BUCKET_NAME=team-17-model-storage
FLASK_SECRET_KEY=<random-secret>
GITHUB_TOKEN=<github-token>
HF_TOKEN=<huggingface-token>
```

### Installation
```bash
./run install  # Install dependencies
```

### Running Locally
```bash
python run.py  # Starts server on http://localhost:8080
```

### Running with Docker
```bash
docker build -t ml-registry .
docker run -p 8080:8080 --env-file .env ml-registry
```

## CLI Usage

Score models from a URL file:
```bash
./run urls.txt
```

Format: `code_url,dataset_url,model_url` (one per line)

Run tests:
```bash
./run test
```

## API Examples

### Upload a Model
```bash
curl -X POST http://localhost:8080/artifact/model \
  -H "Content-Type: application/json" \
  -d '{"url": "https://huggingface.co/google-bert/bert-base-uncased"}'
```

### Search Artifacts
```bash
curl -X GET http://localhost:8080/artifact/byRegex \
  -H "Content-Type: application/json" \
  -d '{"regex": "bert.*uncased"}'
```

### Get Scores
```bash
curl http://localhost:8080/artifact/model/{id}/rate
```

## Scoring Weights

Net score calculation:
- Ramp-Up Time: 20%
- License: 15%
- Code Quality: 12%
- Dataset Quality: 12%
- Performance Claims: 10%
- Bus Factor: 10%
- Dataset & Code: 7%
- Size Score: 5%
- Reproducibility: 3%
- Reviewedness: 3%
- Tree Score: 3%

## CI/CD

GitHub Actions pipeline automatically:
1. Runs tests with coverage reporting
2. Merges `main` → `prod` on successful builds

## Testing

```bash
pytest --cov=src --cov-report=term-missing tests/
```

Current coverage: ~58%

## Project Structure

```
src/
├── app.py              # Flask API endpoints
├── cli.py              # Command-line interface
├── storage.py          # S3 storage operations
├── dynamodb_service.py # DynamoDB operations
├── metric.py           # Base metric interface
├── [metric_name].py    # Individual metric implementations
└── templates/          # Web UI (basic)
```

## Known Limitations

- Authentication system incomplete (returns 501)
- Cognito integration configured but not fully implemented
- No localStorage support in web artifacts
- Some metrics use heuristics rather than deep analysis

## Notes

- All artifact uploads are automatically scored
- Large models stream directly to S3 without local storage
- Regex search works on both artifact names and README content
- System tracks artifact lineage through parent model references
