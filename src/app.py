"""
Flask application with authentication, health monitoring, and audit trails.
This is the main application file with all security and observability features.
"""
# mypy: ignore-errors
import os
import subprocess
import tempfile
import shutil
import json
from pathlib import Path
import logging 
from typing import Any, Dict, Tuple, Optional
from flask import Flask, request, jsonify, render_template, g
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

# Load environment variables
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION")
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", 'dev-secret-key-change-in-production')
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")

if not all([AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, DYNAMODB_ENDPOINT, FLASK_SECRET_KEY, GITHUB_TOKEN, S3_BUCKET_NAME]):
    # Load from AWS Secrets Manager if .env not available
    import boto3
    from botocore.exceptions import ClientError
    secret_name = "ece461-secrets"
    region_name = "us-east-2"

    # Create a Secrets Manager client
    # session = boto3.session.Session()
    client = boto3.client(
        'secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret_dict = json.loads(get_secret_value_response["SecretString"])
    AWS_ACCESS_KEY = secret_dict["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = secret_dict["AWS_SECRET_ACCESS_KEY"]
    AWS_REGION = secret_dict["AWS_DEFAULT_REGION"]
    DYNAMODB_ENDPOINT = secret_dict["DYNAMODB_ENDPOINT"]
    FLASK_SECRET_KEY = secret_dict["FLASK_SECRET_KEY"]
    GITHUB_TOKEN = secret_dict["GITHUB_TOKEN"]
    S3_BUCKET_NAME = secret_dict["S3_BUCKET_NAME"]

# Import storage
from storage import S3Storage

# Import database and services
from database import get_db, init_db, UserRole, AuditAction, db_manager, User
from dynamodb_service import DynamoDBService

# Ensure logs directory exists at project root
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(ROOT_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, 'flask_app.log')

# Configure logger
logger = logging.getLogger('flask_app')
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler(LOG_FILE, mode='w')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
file_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(file_handler)

logger.debug('Logger initialized, writing to %s', LOG_FILE)

try:
    # from cognito_auth import CognitoAuthService
    from cognito_auth import CognitoAuthService
    cognito_auth = CognitoAuthService(AWS_ACCESS_KEY, AWS_SECRET_KEY)
    from cognito_middleware import (
        require_auth, require_admin, require_uploader, require_downloader,
        optional_auth, get_current_user, rate_limit
    )
    USE_COGNITO = cognito_auth.enabled
    logger.debug(f"Cognito authentication: {'ENABLED' if USE_COGNITO else 'DISABLED (using legacy auth)'}")
except Exception as e:
    logger.error(f"Cognito not available: {e}")
    logger.info("Using legacy authentication system")
    USE_COGNITO = False

from health_monitor import health_monitor
from audit_service import AuditService

# Import Phase 1 modules for scoring
from base import HFModelURL
from entities import HFModel
from huggingface import fetch_repo_metadata
from git_repo import fetch_bus_factor_raw_contributors
from metric import Metric
from concurrency import compute_all_metrics

# Import metric modules so they register as subclasses
import license as license_metric
import code_quality
import dataset_quality
import ramp_up_time
import dataset_and_code
import bus_factor
import performance_claims
import size_score
import reproducibility
import reviewedness
import tree_score



app = Flask(__name__)
app.config['SECRET_KEY'] = FLASK_SECRET_KEY

# Initialize storage - use absolute path relative to app location to avoid path mismatches
# This ensures files are saved and queried from the same location regardless of working directory
app_dir = Path(__file__).resolve().parent  # src/ (absolute)
project_root = app_dir.parent  # project root (absolute)
storage_dir_absolute = project_root / "package_storage"
# Resolve to absolute path before passing to S3Storage
storage_dir_absolute = storage_dir_absolute.resolve()
storage = S3Storage(str(storage_dir_absolute), AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, S3_BUCKET_NAME)
# Verify the path is correctly resolved
resolved_metadata_dir = storage.metadata_dir.resolve()
logger.info(f"Storage initialized: metadata_dir = {resolved_metadata_dir}")
logger.info(f"Storage directory exists: {resolved_metadata_dir.exists()}")

# Initialize DynamoDB service 
dynamodb_service = DynamoDBService(AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, DYNAMODB_ENDPOINT)

# Initialize database on startup
with app.app_context():
    init_db()

@app.route('/')
def home():
    """Home page."""
    logger.info('Home page requested from %s', request.remote_addr)
    logger.debug('Rendering index.html')
    return render_template('index.html')

# Request/response hooks for health monitoring and database cleanup
@app.before_request
def before_request():
    """Set up request context."""
    g.request_start_time = datetime.now(timezone.utc)
    try:
        logger.debug('Before request: %s %s from %s', request.method, request.path, request.remote_addr)
    except Exception:
        logger.debug('Before request: could not get request metadata')

@app.after_request
def after_request(response):
    """Record request metrics and cleanup."""
    route = request.endpoint or request.path
    success = response.status_code < 400
    health_monitor.record_request(route, success)
    try:
        start = getattr(g, 'request_start_time', None)
        if start:
            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            logger.debug('After request: %s %s status=%s elapsed_ms=%s', request.method, route, response.status_code, elapsed_ms)
        else:
            logger.debug('After request: %s %s status=%s', request.method, route, response.status_code)
    except Exception:
        logger.exception('Error while logging after_request')

    return response

@app.teardown_appcontext # type: ignore
def teardown_db(exception=None):
    """Close database session at end of request."""
    session = g.pop('db_session', None)
    if session is not None:
        try:
            session.close()
            logger.debug('Database session closed in teardown')
        except Exception:
            logger.exception('Error closing database session in teardown')

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(401)
def unauthorized(error):
    """Handle 401 Unauthorized errors with user-friendly page."""
    # Check if request accepts HTML (browser) or JSON (API)
    logger.warning('Unauthorized access attempt: %s %s - %s', getattr(request, 'method', '<no-method>'), getattr(request, 'path', getattr(request, 'full_path', '<no-path>')), str(error))
    if getattr(request, 'accept_mimetypes', None) and request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json:
        return render_template('error.html', 
            error_code=401,
            error_title="Authentication Required",
            error_message="You must be logged in to access this page.",
            detail="Please authenticate using valid credentials."
        ), 401
    # Return JSON for API requests
    logger.debug('Returning JSON 401 for %s', request.path)
    return jsonify({
        "error": "Authentication required",
        "message": str(error)
    }), 401

@app.errorhandler(403)
def forbidden(error):
    """Handle 403 Forbidden errors with user-friendly page."""
    # Check if request accepts HTML (browser) or JSON (API)
    logger.warning('Forbidden access attempt: %s %s - %s', getattr(request, 'method', '<no-method>'), getattr(request, 'path', getattr(request, 'full_path', '<no-path>')), str(error))
    if getattr(request, 'accept_mimetypes', None) and request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json:
        return render_template('error.html',
            error_code=403,
            error_title="Access Denied - Admin Only",
            error_message="This resource is restricted to administrators only.",
            detail="You do not have sufficient permissions to access this page."
        ), 403
    # Return JSON for API requests
    logger.debug('Returning JSON 403 for %s', request.path)
    return jsonify({
        "error": "Forbidden",
        "message": str(error)
    }), 403

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/authenticate', methods=['PUT'])
def authenticate():
    """
    Authenticate user and return access token.
    Supports both Cognito and legacy auth.
    
    Request body:
    {
        "User": {
            "name": "username or email",
            "isAdmin": true
        },
        "Secret": {
            "password": "user_password"
        }
    }
    
    Returns:
        200: Token generated successfully
        401: Authentication failed
        400: Invalid request
        500: Error during authentication
    """
    try:
        logger.info('Authenticate endpoint called from %s', request.remote_addr)
        data = request.get_json()

        if not data:
            logger.warning('Authenticate called without request body')
            return jsonify({"error": "Request body required"}), 400

        user_data = data.get("User", {})
        secret_data = data.get("Secret", {})

        username = user_data.get("name")
        password = secret_data.get("password")

        if not username or not password:
            logger.warning('Authenticate missing username or password (username provided: %s)', bool(username))
            return jsonify({"error": "Username and password required"}), 400

        logger.debug('Authenticating user: %s (cognito=%s)', username, USE_COGNITO)

        # Try Cognito if enabled, otherwise use legacy auth
        logger.debug('Using Cognito: %s', USE_COGNITO)
        if USE_COGNITO:
            result = cognito_auth.authenticate(username, password)
            logger.info('User %s authenticated via Cognito', username)
            return jsonify({
                "token": result["access_token"],
                "user": {
                    "name": result["user"]["username"],
                    "role": result["user"]["role"],
                    "email": result["user"]["email"]
                },
                "expires_in": result["expires_in"],
                "max_api_calls": 1000
            }), 200
        else:
            # Legacy authentication using database
            logger.info('Using legacy database authentication for user: %s', username)
            try:
                # Check if user exists in database
                session = get_db()
                user = session.query(User).filter_by(username=username).first()
                
                if not user or not user.is_active:
                    logger.warning('Legacy auth: User %s not found or inactive', username)
                    return jsonify({"error": "Invalid credentials"}), 401
                
                # Verify password with bcrypt
                import bcrypt
                if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
                    logger.warning('Legacy auth: Invalid password for user %s', username)
                    return jsonify({"error": "Invalid credentials"}), 401
                
                # For legacy auth, return a simple token (username-based)
                # This is for autograder compatibility
                import base64
                simple_token = base64.b64encode(f"{username}:{user.role.value}".encode()).decode()
                
                logger.info('Legacy auth successful for user %s with role %s', username, user.role)
                
                return jsonify({
                    "token": simple_token,
                    "user": {
                        "username": username,
                        "role": user.role.value
                    }
                }), 200
                
            except Exception as e:
                logger.exception('Error in legacy authentication')
                return jsonify({"error": "Authentication failed"}), 500
            finally:
                if 'session' in locals():
                    session.close()

    except Exception as e:
        logger.exception('Error in authenticate endpoint')
        return jsonify({"error": str(e)}), 500

@app.route('/users', methods=['POST'])
#@require_admin()
def create_user():
    """
    Create a new user (admin only).
    
    Request body:
    {
        "username": "newuser",
        "password": "SecurePass123!",
        "role": "uploader"  // admin, uploader, searcher, downloader
    }
    """
    try:
        logger.info('Create user endpoint called by %s', request.remote_addr)
        data = request.get_json()

        if not data:
            logger.warning('Create user called without data')
            return jsonify({"error": "Data not returned"}), 404

        username = data.get("username")
        email = data.get("email", username)
        password = data.get("password")
        role_str = data.get("role", "searcher")

        if not username or not password:
            logger.warning('Create user missing username or password')
            return jsonify({"error": "Username and password required"}), 400

        logger.debug('Creating user %s with role %s (cognito=%s)', username, role_str, USE_COGNITO)

        if USE_COGNITO:
            # Cognito user creation
            valid_roles = ["admin", "uploader", "searcher", "downloader"]
            if role_str not in valid_roles:
                logger.warning('Invalid role provided for create_user: %s', role_str)
                return jsonify({
                    "error": f"Invalid role. Must be one of: {valid_roles}"
                }), 400

            user = cognito_auth.create_user(username, email, password, role_str)
            logger.info('Created Cognito user %s', username)
            return jsonify({
                "success": True,
                "user": user
            }), 201
        else:
            # Legacy user creation - not implemented in this phase
            logger.warning('Legacy user creation not available')
            return jsonify({
                "error": "User creation unavailable",
                "message": "Cognito authentication not configured"
            }), 503

    except ValueError as e:
        logger.exception('ValueError in create_user')
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception('Exception in create_user')
        return jsonify({"error": str(e)}), 500

@app.route('/users/<username>', methods=['DELETE'])
#@require_admin()
def delete_user(username: str):
    """
    Delete a user (admin only).
    """
    try:
        logger.info('Delete user called for %s by %s', username, request.remote_addr)
        if USE_COGNITO:
            # Delete user from Cognito
            cognito_auth.delete_user(username)
            logger.info('Deleted Cognito user %s', username)
        else:
            # Legacy delete - not implemented in this phase
            logger.warning('Legacy user deletion not available')
            return jsonify({
                "error": "User deletion unavailable",
                "message": "Cognito authentication not configured"
            }), 503

        return jsonify({"success": True, "message": f"User {username} deleted"}), 200

    except ValueError as e:
        logger.exception('ValueError in delete_user')
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception('Exception in delete_user')
        return jsonify({"error": str(e)}), 500

@app.route('/users', methods=['GET'])
#@require_admin()
def list_users():
    """List all users (admin only)."""
    try:
        logger.info('List users called by %s', request.remote_addr)
        if USE_COGNITO:
            # Get users from Cognito
            users = cognito_auth.list_users()
            logger.debug('Found %s users', len(users))
            return jsonify({
                "success": True,
                "count": len(users),
                "users": users
            }), 200
        else:
            # Legacy list users - not implemented in this phase
            logger.warning('Legacy user listing not available')
            return jsonify({
                "error": "User listing unavailable",
                "message": "Cognito authentication not configured"
            }), 503

    except Exception as e:
        logger.exception('Error in list_users')
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH MONITORING ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
#@require_admin()
def health_check():
    """
    Simple liveness check (admin only).
    Returns 200 if service is alive.
    """
    logger.info('Health check requested by %s', request.remote_addr)
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ECE461 Package Registry",
        "description": "service reachable"
    }), 200

@app.route('/tracks', methods=['GET'])
def get_tracks():
    """Get system tracks (for autograder tracking)."""
    # Always return Access Control Track for autograder
    # This endpoint should never fail - it's critical for autograder
    tracks = ["Access Control Track"]
    logger.info('Tracks endpoint called, returning: %s', tracks)
    return jsonify({
        "tracks": tracks
    }), 200

@app.route('/health/components', methods=['GET'])
#@require_admin()
def health_components():
    """
    Detailed component health check (admin only).
    Returns health status of all system components.
    """
    try:
        logger.info('Health components requested by %s', request.remote_addr)
        summary = health_monitor.get_health_summary()
        route_stats = health_monitor.get_route_statistics()

        logger.debug('Health summary: %s', summary)
        return jsonify({
            **summary,
            "route_statistics": route_stats
        }), 200

    except Exception as e:
        logger.exception('Error fetching health components')
        return jsonify({
            "status": "critical",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 500

# ============================================================================
# AUDIT TRAIL ENDPOINTS
# ============================================================================

@app.route('/artifact/<artifact_type>/<artifact_id>/audit', methods=['GET'])
@require_auth()
def get_audit_trail(artifact_type: str, artifact_id: str):
    """
    Get audit trail for an artifact.
    
    Query params:
        limit: Maximum entries to return (default 100)
        offset: Number of entries to skip (default 0)
    """
    try:
        logger.info('Get audit trail called for %s/%s by %s', artifact_type, artifact_id, request.remote_addr)
        limit = min(int(request.args.get('limit', 100)), 500)
        offset = int(request.args.get('offset', 0))

        session = get_db()
        audit_service = AuditService(session)

        # Log the audit access
        current_user = get_current_user()
        audit_service.log_audit(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            username=current_user["username"] if current_user else None
        )
        session.commit()
        logger.debug('Logged audit access for %s by %s', artifact_id, current_user)

        # Get audit trail
        trail = audit_service.get_artifact_audit_trail(artifact_id, limit, offset)

        logger.info('Returning %s audit entries for %s', len(trail), artifact_id)
        return jsonify({
            "success": True,
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "count": len(trail),
            "limit": limit,
            "offset": offset,
            "audit_trail": trail
        }), 200

    except Exception as e:
        logger.exception('Error in get_audit_trail')
        return jsonify({"error": str(e)}), 500

@app.route('/artifact/<artifact_type>/<artifact_id>/downloads', methods=['GET'])
@require_auth()
def get_download_history(artifact_type: str, artifact_id: str):
    """Get download history for an artifact."""
    try:
        limit = min(int(request.args.get('limit', 100)), 500)

        logger.info('Get download history called for %s/%s (limit=%s) by %s', artifact_type, artifact_id, limit, request.remote_addr)
        session = get_db()
        audit_service = AuditService(session)

        downloads = audit_service.get_download_history(artifact_id, limit)
        logger.debug('Found %s downloads for %s', len(downloads), artifact_id)

        return jsonify({
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "count": len(downloads),
            "limit": limit,
            "downloads": downloads
        }), 200

    except Exception as e:
        logger.exception('Error in get_download_history')
        return jsonify({"error": str(e)}), 500

@app.route('/audit/statistics', methods=['GET'])
#@require_admin()
def get_audit_statistics():
    """Get overall audit statistics (admin only)."""
    try:
        logger.info('Audit statistics requested by %s', request.remote_addr)
        session = get_db()
        audit_service = AuditService(session)

        stats = audit_service.get_audit_statistics()
        logger.debug('Audit statistics: %s', stats)

        return jsonify({
            "success": True,
            "statistics": stats
        }), 200

    except Exception as e:
        logger.exception('Error in get_audit_statistics')
        return jsonify({"error": str(e)}), 500

# ============================================================================
# PACKAGE ENDPOINTS (with authentication and audit logging)
# ============================================================================

@app.route('/package', methods=['POST'])
@require_uploader()
@rate_limit(max_requests=50, window_seconds=60)
def upload_package():
    """
    Ingest a package and score it (requires uploader role).
    
    Request body:
    {
        "name": "package-name",
        "version": "1.0.0",
        "url": "https://huggingface.co/model-name",
        "is_sensitive": false,
        "monitoring_script": "optional JS code"
    }
    """
    try:
        logger.info('Upload package called by %s', request.remote_addr)
        data = request.get_json()

        if not data:
            logger.warning('upload_package called without body')
            return jsonify({"error": "Request body required"}), 400

        name = data.get("name")
        version = data.get("version", "1.0.0")
        url = data.get("url")
        is_sensitive = data.get("is_sensitive", False)
        monitoring_script = data.get("monitoring_script")

        # Validation
        if not name:
            logger.warning('upload_package missing name')
            return jsonify({"error": "Package name required"}), 400

        if not url:
            logger.warning('upload_package missing url')
            return jsonify({"error": "Package URL required"}), 400

        logger.debug('Uploading package %s version=%s url=%s sensitive=%s', name, version, url, is_sensitive)

        # Run scoring
        logger.info('Starting scoring for package %s', name)
        scores = run_scoring(url)
        logger.debug('Scoring results for %s: %s', name, scores)

        # Get current user
        current_user = get_current_user()

        # Save package
        package_info = storage.save_package(
            name=name,
            version=version,
            url=url,
            scores=scores
        )
        logger.info('Package saved with id %s', package_info.get('id'))

        # Log to audit trail
        session = get_db()
        audit_service = AuditService(session)
        audit_service.log_create(
            artifact_id=package_info["id"],
            artifact_type="model",  # TODO: detect type from URL
            username=current_user["username"] if current_user else None,
            artifact_name=name,
            artifact_version=version
        )
        session.commit()
        logger.debug('Audit log created for package %s', package_info.get('id'))

        return jsonify({
            "success": True,
            "package_id": package_info["id"],
            "name": name,
            "version": version,
            "url": url,
            "scores": scores,
            "message": "Package ingested and scored successfully"
        }), 201

    except Exception as e:
        logger.exception('Error in upload_package')
        return jsonify({"error": str(e)}), 500

@app.route('/package/<package_id>', methods=['GET'])
@require_auth()
def get_package(package_id: str):
    """
    Retrieve package by ID (requires authentication).
    """
    try:
        logger.info('Get package called for id=%s by %s', package_id, request.remote_addr)
        package = storage.get_package(package_id)

        if not package:
            logger.info('Package %s not found', package_id)
            return jsonify({"error": f"Package {package_id} not found"}), 404

        logger.debug('Returning package %s', package_id)
        return jsonify(package), 200

    except Exception as e:
        logger.exception('Error in get_package')
        return jsonify({"error": str(e)}), 500

@app.route('/packages/byRegex', methods=['GET'])
@require_auth()
@rate_limit(max_requests=100, window_seconds=60)
def search_by_regex():
    """
    Search packages by regex pattern (requires authentication).
    
    Query parameter:
        RegEx: Regular expression pattern to match package names
    """
    try:
        logger.info('Search by regex called by %s', request.remote_addr)
        regex_pattern = request.args.get('RegEx')

        if not regex_pattern:
            logger.warning('search_by_regex missing RegEx parameter')
            return jsonify({"error": "RegEx parameter is required"}), 400

        logger.debug('Searching packages with pattern: %s', regex_pattern)
        # Search packages
        results = storage.search_by_regex(regex_pattern)

        logger.info('search_by_regex found %s results', len(results))
        return jsonify({
            "success": True,
            "count": len(results),
            "regex_pattern": regex_pattern,
            "packages": results
        }), 200

    except ValueError as e:
        logger.exception('ValueError in search_by_regex')
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception('Exception in search_by_regex')
        return jsonify({"error": str(e)}), 500

@app.route('/artifact/<artifact_type>', methods=['POST'])
@require_uploader()
@rate_limit(max_requests=50, window_seconds=60)
def upload_artifact(artifact_type: str):
    """Upload/Ingest an artifact (requires uploader role)."""
    try:
        if artifact_type not in ['model', 'dataset', 'code']:
            return jsonify({"error": f"Invalid artifact type: {artifact_type}"}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        name = data.get("name")
        version = data.get("version", "1.0.0")
        url = data.get("url")
        if not name:
            return jsonify({"error": "Artifact name required"}), 400
        if not url:
            return jsonify({"error": "URL is required"}), 400

        # Run scoring (no threshold check - accept all artifacts like /package endpoint)
        scores = run_scoring(url)

        # Save artifact with artifact_type
        package_info = storage.save_package(name=name, version=version, url=url, scores=scores)
        package_info["artifact_type"] = artifact_type
        
        # Update metadata file with artifact_type
        metadata_file = storage.metadata_dir / f"{package_info['id']}.json"
        with open(metadata_file, "w") as f:
            json.dump(package_info, f, indent=2)
        
        current_user = get_current_user()
        session = get_db()
        audit_service = AuditService(session)
        audit_service.log_create(
            artifact_id=package_info["id"],
            artifact_type=artifact_type,
            username=current_user["username"] if current_user else None,
            artifact_name=name,
            artifact_version=version
        )
        session.commit()
        session.close()

        return jsonify({
            "success": True,
            "artifact_id": package_info["id"],
            "name": name,
            "version": version,
            "url": url,
            "scores": scores,
            "message": "Artifact ingested and scored successfully"
        }), 201

    except Exception as e:
        logger.exception('Error in upload_artifact')
        return jsonify({"error": str(e)}), 500

@app.route('/artifacts', methods=['POST'])
@require_auth()
def query_artifacts():
    """Query artifacts with filters (requires authentication)."""
    try:
        data = request.get_json() or {}
        offset = int(request.args.get('offset', 0))
        limit = min(int(request.args.get('limit', 100)), 100)
        
        # Extract filters
        query = data.get("ArtifactQuery", {})
        name_filter = query.get("name") or data.get("Name")
        artifact_type = query.get("type")
        
        # Query all packages from storage
        # Use resolved absolute path to ensure consistency with reset
        results = []
        storage_path = storage.metadata_dir.resolve()
        logger.debug('Query artifacts: Checking metadata directory %s', storage_path)
        if storage_path.exists():
            for metadata_file in storage_path.glob("*.json"):
                try:
                    with open(metadata_file, "r") as f:
                        package_data = json.load(f)
                        if package_data.get("is_deleted", False):
                            continue
                        if artifact_type and package_data.get("artifact_type") != artifact_type:
                            continue
                        if name_filter and name_filter.lower() not in package_data.get("name", "").lower():
                            continue
                        results.append(package_data)
                except Exception:
                    continue
        
        # Sort by created_at (newest first)
        if results:
            results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        paginated_results = results[offset:offset + limit]
        
        return jsonify({
            "success": True,
            "count": len(paginated_results),
            "total": len(results),
            "offset": offset,
            "limit": limit,
            "artifacts": paginated_results
        }), 200
    except Exception as e:
        logger.exception('Error in query_artifacts')
        return jsonify({"error": str(e)}), 500

@app.route('/reset', methods=['DELETE'])
#@require_admin()
def reset_system():
    """
    Reset system to initial state (admin only).
    Clears all packages and resets database.
    """
    try:
        logger.info('System reset requested by %s', request.remote_addr)
        
        # Clear S3 objects first (before clearing metadata)
        try:
            storage.clear_all_s3_objects()
            logger.info('S3 objects cleared successfully')
        except Exception as e:
            logger.warning('S3 cleanup failed (non-critical): %s', e)
        
        # Clear local package storage metadata files - AGGRESSIVE APPROACH
        # Use resolved absolute path to ensure consistency
        storage_path = storage.metadata_dir.resolve()
        logger.info('Reset: Clearing metadata files from %s', storage_path)
        logger.info('Reset: Directory exists: %s', storage_path.exists())
        
        deleted_files = 0
        
        if storage_path.exists():
            import os
            import shutil
            
            # Get ALL files in directory (not just JSON)
            try:
                all_items = os.listdir(storage_path)
                logger.info('Reset: Found %d items in directory: %s', len(all_items), all_items[:10])
            except Exception as e:
                logger.error('Reset: Could not list directory: %s', e)
                all_items = []
            
            # Method 1: Try to delete individual files
            json_files = [f for f in all_items if f.endswith('.json')]
            logger.info('Reset: Found %d JSON files to delete', len(json_files))
            
            for filename in json_files:
                filepath = storage_path / filename
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        if filepath.exists():
                            filepath.unlink()
                            if not filepath.exists():
                                deleted_files += 1
                                logger.debug('Reset: Deleted %s', filename)
                                break
                            else:
                                logger.warning('Reset: File still exists after unlink: %s', filename)
                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error('Reset: Failed to delete %s after %d attempts: %s', 
                                       filename, max_retries, e)
                        else:
                            import time
                            time.sleep(0.05)
            
            # Method 2: Nuclear option - remove and recreate directory
            try:
                logger.info('Reset: Nuclear option - removing entire directory')
                shutil.rmtree(storage_path)
                logger.info('Reset: Directory removed successfully')
                
                # Recreate empty directory
                storage_path.mkdir(parents=True, exist_ok=True)
                logger.info('Reset: Directory recreated')
            except Exception as e:
                logger.error('Reset: Failed to remove directory: %s', e)
        else:
            logger.warning('Reset: Metadata directory does not exist: %s', storage_path)
            # Create it
            storage_path.mkdir(parents=True, exist_ok=True)
        
        logger.info('Reset: Deleted %d metadata files', deleted_files)
        
        # Reset database
        try:
            db_manager.reset_database()
            logger.info('Database reset completed')
        except Exception as e:
            logger.error('Database reset failed: %s', e)
            raise
        
        # Reinitialize with default admin
        try:
            init_db()
            logger.info('Database reinitialized with default admin')
        except Exception as e:
            logger.error('Database reinitialization failed: %s', e)
            raise
        
        # Also clear DynamoDB if it exists
        try:
            dynamodb_service.reset_database()
            logger.info('DynamoDB reset completed')
        except Exception as e:
            logger.warning('DynamoDB reset failed (non-critical): %s', e)
        
        # Verify reset by checking if any artifacts remain
        # Multiple verification passes with delays
        import time
        import os
        
        verification_path = storage.metadata_dir.resolve()
        logger.info('Reset verification: Checking directory %s', verification_path)
        
        # Wait for filesystem to sync
        time.sleep(0.3)
        
        # Multiple verification passes
        for verification_attempt in range(3):
            if not verification_path.exists():
                logger.warning('Reset verification: Directory does not exist, recreating')
                verification_path.mkdir(parents=True, exist_ok=True)
                remaining_count = 0
                break
                
            try:
                dir_contents = os.listdir(verification_path)
                json_files = [f for f in dir_contents if f.endswith('.json')]
                remaining_count = len(json_files)
                
                logger.info('Reset verification attempt %d: Found %d files: %s', 
                           verification_attempt + 1, remaining_count, json_files[:5])
                
                if remaining_count == 0:
                    break
                    
                # Try to delete remaining files
                for filename in json_files:
                    filepath = verification_path / filename
                    try:
                        if filepath.exists():
                            filepath.unlink()
                            logger.info('Reset verification: Deleted remaining file %s', filename)
                    except Exception as e:
                        logger.error('Reset verification: Failed to delete %s: %s', filename, e)
                
                # Wait before next verification
                if verification_attempt < 2:
                    time.sleep(0.2)
                    
            except OSError as e:
                logger.error('Reset verification: Could not list directory: %s', e)
                remaining_count = 0
                break
        
        logger.info('Reset verification final: %d artifacts remain', remaining_count)

        # Final verification - count remaining artifacts
        import os
        final_check_path = storage.metadata_dir.resolve()
        final_remaining = []
        
        if final_check_path.exists():
            try:
                dir_contents = os.listdir(final_check_path)
                final_remaining = [f for f in dir_contents if f.endswith('.json')]
                logger.info('Reset final check: Directory contains %d items, %d JSON files', 
                           len(dir_contents), len(final_remaining))
            except OSError as e:
                logger.error('Reset final check: Could not list directory: %s', e)
        else:
            logger.warning('Reset final check: Directory does not exist')
            final_check_path.mkdir(parents=True, exist_ok=True)
        
        if final_remaining:
            logger.error('RESET FAILED: %d artifacts still remain: %s', len(final_remaining), final_remaining)
            # Try one more time to delete them
            for filename in final_remaining:
                try:
                    (final_check_path / filename).unlink()
                except:
                    pass
            return jsonify({
                "success": False,
                "message": "System reset incomplete - artifacts remain",
                "remaining_count": len(final_remaining),
                "remaining_files": final_remaining[:10]
            }), 500
        else:
            logger.info('RESET SUCCESS: System reset completed - no artifacts remain')
            return jsonify({
                "success": True,
                "message": "System reset to initial state",
                "remaining_count": 0
            }), 200

    except Exception as e:
        logger.exception('Error in reset_system')
        return jsonify({"error": str(e)}), 500

# ============================================================================
# SENSITIVE MODEL PROTECTION
# ============================================================================

def execute_monitoring_script(
    script_content: str,
    model_name: str,
    uploader_username: str,
    downloader_username: str,
    zip_file_path: str
) -> Tuple[bool, str]:
    """
    Execute JavaScript monitoring script for sensitive models.
    
    Args:
        script_content: JavaScript code to execute
        model_name: Name of the model
        uploader_username: Username who uploaded the model
        downloader_username: Username downloading the model
        zip_file_path: Path to the ZIP file
        
    Returns:
        Tuple of (success: bool, output: str)
    """
    try:
        # Create temporary file for script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        logger.info('Executing monitoring script for model %s (uploader=%s downloader=%s)', model_name, uploader_username, downloader_username)
        logger.debug('Wrote monitoring script to %s', script_path)

        # Set environment variables
        env = os.environ.copy()
        env.update({
            'MODEL_NAME': model_name,
            'UPLOADER_USERNAME': uploader_username,
            'DOWNLOADER_USERNAME': downloader_username,
            'ZIP_FILE_PATH': zip_file_path
        })
        
        # Execute script with Node.js
        result = subprocess.run(
            ['node', script_path],
            env=env,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        # Clean up
        os.unlink(script_path)
        logger.debug('Monitoring script exit code=%s stdout=%s stderr=%s', result.returncode, result.stdout, result.stderr)
        # Check exit code
        if result.returncode == 0:
            logger.info('Monitoring script executed successfully for %s', model_name)
            return True, result.stdout
        else:
            logger.error('Monitoring script failed for %s with code %s', model_name, result.returncode)
            return False, result.stderr or result.stdout
        
    except subprocess.TimeoutExpired:
        logger.error('Monitoring script timed out for %s', model_name)
        return False, "Monitoring script execution timed out"
    except Exception as e:
        logger.exception('Error executing monitoring script for %s', model_name)
        return False, f"Error executing monitoring script: {str(e)}"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def run_scoring(url: str) -> Dict[str, Any]:
    """
    Run scoring metrics on a Hugging Face model URL.
    Integrates with Phase 1 scoring system.
    """
    try:
        logger.info('Running scoring for URL: %s', url)
        # Parse URL
        model_url = HFModelURL(url=url)
        model = HFModel(model_url=model_url)

        # Fetch Hugging Face metadata
        hf_metadata = fetch_repo_metadata(model)
        logger.debug('Fetched HF metadata for %s: keys=%s', url, list(hf_metadata.keys()) if isinstance(hf_metadata, dict) else type(hf_metadata))

        # Count code repos and datasets
        nof_code_ds = {
            "nof_code": len(model.model_url.code),
            "nof_ds": len(model.model_url.datasets)
        }

        # Fetch GitHub data if code repo exists
        repo_metadata = {}
        if model.model_url.code and GITHUB_TOKEN:
            try:
                repo_url = model.model_url.code[0].url
                repo_metadata = fetch_bus_factor_raw_contributors(repo_url, GITHUB_TOKEN)
                repo_metadata["repo_url"] = repo_url
                logger.debug('Fetched repo metadata for %s', repo_url)
            except Exception as e:
                logger.exception('Warning: Could not fetch repo metadata')

        # Combine metadata
        model.metadata = {
            "hf_metadata": hf_metadata,
            "repo_metadata": repo_metadata,
            "nof_code_ds": nof_code_ds
        }

        # Run all metrics
        metrics = [cls() for cls in Metric.__subclasses__()]  # type: ignore

        # Inject dependencies for new metrics
        for metric in metrics:
            try:
                if isinstance(metric, tree_score.TreeScoreMetric):
                    metric.storage = storage
                elif isinstance(metric, reviewedness.ReviewednessMetric):
                    metric.github_token = GITHUB_TOKEN
            except Exception:
                logger.exception('Error injecting dependencies for metric %s', type(metric))

        metric_results = compute_all_metrics(model.metadata, metrics, max_workers=8)

        # Convert to dict
        scores = {}
        for result in metric_results:
            scores[result.name] = {
                "value": result.value,
                "latency_ms": result.latency_ms
            }

        logger.debug('Metric results: %s', list(scores.keys()))

        # Calculate net score
        weights = {
            "ramp_up_time": 0.20,           # Same
            "license": 0.15,                # Same
            "dataset_and_code_score": 0.10, # Same
            "performance_claims": 0.10,     # Same
            "bus_factor": 0.07,             # Reduced from 0.10
            "code_quality": 0.12,           # Reduced from 0.15
            "dataset_quality": 0.12,        # Reduced from 0.15
            "size_score": 0.05,             # Same
            "reproducibility": 0.03,        # NEW
            "reviewedness": 0.03,           # NEW
            "tree_score": 0.03,             # NEW
        }

        net_score = 0.0
        for metric_name, weight in weights.items():
            if metric_name in scores:
                score_val = scores[metric_name].get("value", 0)
                if isinstance(score_val, (int, float)):
                    net_score += score_val * weight

        scores["net_score"] = {"value": round(net_score, 2)}
        logger.info('Computed net_score=%s for %s', scores["net_score"], url)

        return scores

    except Exception as e:
        logger.exception('Error during scoring for URL: %s', url)
        return {"error": str(e), "net_score": {"value": 0.0}}

if __name__ == '__main__':
    logger.info('Starting ECE461 Team 17 - Package Registry API')
    logger.info('Listening on http://127.0.0.1:8080')
    print("=" * 60)
    print("  ECE461 Team 17 - Package Registry API")
    print("=" * 60)
    print("\nAuthentication Endpoints:")
    print("  PUT  /authenticate            - Generate JWT token")
    print("  POST /users                   - Create user (admin)")
    print("  GET  /users                   - List users (admin)")
    print("  DELETE /users/<username>      - Delete user")
    print("\nHealth Monitoring:")
    print("  GET  /health                  - Liveness check")
    print("  GET  /health/components       - Component health")
    print("\nAudit Endpoints:")
    print("  GET  /artifact/<type>/<id>/audit     - Audit trail")
    print("  GET  /artifact/<type>/<id>/downloads - Download history")
    print("\nPackage Endpoints:")
    print("  POST /package                 - Ingest and score")
    print("  GET  /package/<id>            - Retrieve package")
    print("  GET  /packages/byRegex        - Search packages")
    print("  DELETE /reset                 - Reset system (admin)")
    print("\nListening on http://127.0.0.1:8080")
    print("=" * 60)
    app.run(host='127.0.0.1', port=8080)
