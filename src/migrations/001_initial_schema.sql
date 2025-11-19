
-- artifacts table (modles, dataset, code)
CREATE TABLE artifacts (
    id VARCHAR(255) PRIMARY KEY,
    artifact_type VARCHAR(50) NOT NULL CHECK (artifact_type IN ('model', 'dataset', 'code')),
    name VARCHAR(255) NOT NULL,
    version VARCHAR(100),
    url TEXT NOT NULL,
    s3_key TEXT,
    readme_content TEXT,
    metadata JSONB,
    scores JSONB,
    net_score FLOAT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    INDEX idx_name (name),
    INDEX idx_type_name (artifact_type, name),
    INDEX idx_created_at (created_at DESC)
);

-- version history for artifacts
CREATE TABLE artifact_versions (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(255) REFERENCES artifacts(id),
    version_number INTEGER NOT NULL,
    s3_key TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_artifact_versions (artifact_id, version_number DESC)
);

-- users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'uploader', 'searcher', 'downloader')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- audit logs
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(255),
    artifact_type VARCHAR(50),
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_artifact_audit (artifact_id, created_at DESC),
    INDEX idx_user_audit (user_id, created_at DESC)
);

-- lineage relationships
CREATE TABLE lineage_relationships (
    id SERIAL PRIMARY KEY,
    parent_artifact_id VARCHAR(255) REFERENCES artifacts(id),
    child_artifact_id VARCHAR(255) REFERENCES artifacts(id),
    relationship_type VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_artifact_id, child_artifact_id)
);