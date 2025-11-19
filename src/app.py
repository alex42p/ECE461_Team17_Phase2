"""
Flask application with authentication, health monitoring, and audit trails.
This is the main application file with all security and observability features.
"""

import os
import subprocess
import tempfile
from typing import Any
from flask import Flask, request, jsonify, render_template, g
from datetime import datetime, timezone

# Import storage
from storage import PackageStorage

# Import database and services
from database import get_db, init_db, UserRole, AuditAction, db_manager
from auth_service import AuthService
from auth_middleware import (
    require_auth, require_admin, require_uploader, require_downloader,
    optional_auth, get_current_user, rate_limit
)
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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize storage
storage = PackageStorage()

# Get GitHub token
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Initialize database on startup
with app.app_context():
    init_db()

@app.route('/')
def home():
    """Home page."""
    return render_template('index.html')

# Request/response hooks for health monitoring and database cleanup
@app.before_request
def before_request():
    """Set up request context."""
    g.request_start_time = datetime.now(timezone.utc)

@app.after_request
def after_request(response):
    """Record request metrics and cleanup."""
    # Record request for health monitoring
    route = request.endpoint or request.path
    success = response.status_code < 400
    health_monitor.record_request(route, success)
    
    return response

@app.teardown_appcontext # type: ignore
def teardown_db(exception=None):
    """Close database session at end of request."""
    session = g.pop('db_session', None)
    if session is not None:
        session.close()

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(401)
def unauthorized(error):
    """Handle 401 Unauthorized errors with user-friendly page."""
    # Check if request accepts HTML (browser) or JSON (API)
    if request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json:
        return render_template('error.html', 
            error_code=401,
            error_title="Authentication Required",
            error_message="You must be logged in to access this page.",
            detail="Please authenticate using valid credentials."
        ), 401
    # Return JSON for API requests
    return jsonify({
        "error": "Authentication required",
        "message": str(error)
    }), 401

@app.errorhandler(403)
def forbidden(error):
    """Handle 403 Forbidden errors with user-friendly page."""
    # Check if request accepts HTML (browser) or JSON (API)
    if request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json:
        return render_template('error.html',
            error_code=403,
            error_title="Access Denied - Admin Only",
            error_message="This resource is restricted to administrators only.",
            detail="You do not have sufficient permissions to access this page."
        ), 403
    # Return JSON for API requests
    return jsonify({
        "error": "Forbidden",
        "message": str(error)
    }), 403

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/authenticate', methods=['PUT'])
@rate_limit(max_requests=10, window_seconds=60)  # Prevent brute force
def authenticate():
    """
    Authenticate user and generate JWT token.
    
    Request body:
    {
        "User": {
            "name": "username",
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
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body required"}), 400
        
        user_data = data.get("User", {})
        secret_data = data.get("Secret", {})
        
        username = user_data.get("name")
        password = secret_data.get("password")
        
        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400
        
        # Authenticate
        session = get_db()
        auth_service = AuthService(session)
        
        result = auth_service.authenticate(username, password)
        
        if not result:
            return jsonify({
                "error": "Authentication failed",
                "message": "Invalid username or password"
            }), 401
        
        return jsonify({
            "token": result["token"],
            "user": {
                "name": result["username"],
                "role": result["role"]
            },
            "expires_at": result["expires_at"],
            "max_api_calls": AuthService.MAX_API_CALLS_PER_TOKEN
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/users', methods=['POST'])
@require_admin()
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
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Data not returned"}), 404

        username = data.get("username")
        password = data.get("password")
        role_str = data.get("role", "searcher")
        
        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400
        
        try:
            role = UserRole(role_str)
        except ValueError:
            return jsonify({
                "error": f"Invalid role. Must be one of: {[r.value for r in UserRole]}"
            }), 400
        
        session = get_db()
        auth_service = AuthService(session)
        
        user = auth_service.create_user(username, password, role)
        session.commit()
        
        return jsonify({
            "success": True,
            "user": user.to_dict()
        }), 201
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/users/<username>', methods=['DELETE'])
@require_auth()
def delete_user(username: str):
    """
    Delete a user (self-deletion or admin).
    """
    try:
        current_user_data = get_current_user()
        if not current_user_data:
            return jsonify({"error": "Authentication required"}), 401
        session = get_db()
        auth_service = AuthService(session)
        
        # Get requesting user
        from database import User
        requesting_user = session.query(User).filter_by(
            username=current_user_data["username"]
        ).first()
        
        if not requesting_user:
            return jsonify({"error": "User not found"}), 404
        
        success = auth_service.delete_user(username, requesting_user)
        
        if success:
            session.commit()
            return jsonify({"success": True, "message": f"User {username} deleted"}), 200
        else:
            return jsonify({"error": "Insufficient permissions"}), 403
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/users', methods=['GET'])
@require_admin()
def list_users():
    """List all users (admin only)."""
    try:
        session = get_db()
        auth_service = AuthService(session)
        
        users = auth_service.list_users()
        
        return jsonify({
            "success": True,
            "count": len(users),
            "users": users
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH MONITORING ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
@require_admin()
def health_check():
    """
    Simple liveness check (admin only).
    Returns 200 if service is alive.
    """
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ECE461 Package Registry"
    }), 200

@app.route('/health/components', methods=['GET'])
@require_admin()
def health_components():
    """
    Detailed component health check (admin only).
    Returns health status of all system components.
    """
    try:
        summary = health_monitor.get_health_summary()
        route_stats = health_monitor.get_route_statistics()
        
        return jsonify({
            **summary,
            "route_statistics": route_stats
        }), 200
        
    except Exception as e:
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
        
        # Get audit trail
        trail = audit_service.get_artifact_audit_trail(artifact_id, limit, offset)
        
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
        return jsonify({"error": str(e)}), 500

@app.route('/artifact/<artifact_type>/<artifact_id>/downloads', methods=['GET'])
@require_auth()
def get_download_history(artifact_type: str, artifact_id: str):
    """Get download history for an artifact."""
    try:
        limit = min(int(request.args.get('limit', 100)), 500)
        
        session = get_db()
        audit_service = AuditService(session)
        
        downloads = audit_service.get_download_history(artifact_id, limit)
        
        return jsonify({
            "success": True,
            "artifact_id": artifact_id,
            "count": len(downloads),
            "downloads": downloads
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/audit/statistics', methods=['GET'])
@require_admin()
def get_audit_statistics():
    """Get overall audit statistics (admin only)."""
    try:
        session = get_db()
        audit_service = AuditService(session)
        
        stats = audit_service.get_audit_statistics()
        
        return jsonify({
            "success": True,
            **stats
        }), 200
        
    except Exception as e:
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
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body required"}), 400
        
        name = data.get("name")
        version = data.get("version", "1.0.0")
        url = data.get("url")
        is_sensitive = data.get("is_sensitive", False)
        monitoring_script = data.get("monitoring_script")
        
        # Validation
        if not name:
            return jsonify({"error": "Package name required"}), 400
        
        if not url:
            return jsonify({"error": "Package URL required"}), 400
        
        # Run scoring
        scores = run_scoring(url)
        
        # Get current user
        current_user = get_current_user()
        
        # Save package
        package_info = storage.save_package(
            name=name,
            version=version,
            url=url,
            scores=scores
        )
        
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
        return jsonify({"error": str(e)}), 500

@app.route('/package/<package_id>', methods=['GET'])
@require_auth()
def get_package(package_id: str):
    """
    Retrieve package by ID (requires authentication).
    """
    try:
        package = storage.get_package(package_id)
        
        if not package:
            return jsonify({"error": f"Package {package_id} not found"}), 404
        
        return jsonify(package), 200
        
    except Exception as e:
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
        regex_pattern = request.args.get('RegEx')
        
        if not regex_pattern:
            return jsonify({"error": "RegEx parameter is required"}), 400
        
        # Search packages
        results = storage.search_by_regex(regex_pattern)
        
        return jsonify({
            "success": True,
            "count": len(results),
            "regex_pattern": regex_pattern,
            "packages": results
        }), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reset', methods=['DELETE'])
@require_admin()
def reset_system():
    """
    Reset system to initial state (admin only).
    Clears all packages and resets database.
    """
    try:
        # Reset database
        db_manager.reset_database()
        
        # Reinitialize with default admin
        init_db()
        
        # Clear package storage
        import shutil
        storage_path = storage.metadata_dir
        if storage_path.exists():
            shutil.rmtree(storage_path)
            storage_path.mkdir(parents=True)
        
        return jsonify({
            "success": True,
            "message": "System reset to initial state"
        }), 200
        
    except Exception as e:
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
) -> tuple[bool, str]:
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
        
        # Check exit code
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr or result.stdout
        
    except subprocess.TimeoutExpired:
        return False, "Monitoring script execution timed out"
    except Exception as e:
        return False, f"Error executing monitoring script: {str(e)}"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def run_scoring(url: str) -> dict[str, Any]:
    """
    Run scoring metrics on a Hugging Face model URL.
    Integrates with Phase 1 scoring system.
    """
    try:
        # Parse URL
        model_url = HFModelURL(url=url)
        model = HFModel(model_url=model_url)
        
        # Fetch Hugging Face metadata
        hf_metadata = fetch_repo_metadata(model)
        
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
            except Exception as e:
                print(f"Warning: Could not fetch repo metadata: {e}")
        
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
            if isinstance(metric, tree_score.TreeScoreMetric):
                metric.storage = storage
            elif isinstance(metric, reviewedness.ReviewednessMetric):
                metric.github_token = GITHUB_TOKEN

        metric_results = compute_all_metrics(model.metadata, metrics, max_workers=4)
        
        # Convert to dict
        scores = {}
        for result in metric_results:
            scores[result.name] = {
                "value": result.value,
                "latency_ms": result.latency_ms
            }
        
        # Calculate net score
        weights = {
            "ramp_up_time": 0.20,
            "license": 0.15,
            "dataset_and_code_score": 0.10,
            "performance_claims": 0.10,
            "bus_factor": 0.10,
            "code_quality": 0.15,
            "dataset_quality": 0.15,
            "size_score": 0.05
        }
        
        net_score = 0.0
        for metric_name, weight in weights.items():
            if metric_name in scores:
                score_val = scores[metric_name].get("value", 0)
                if isinstance(score_val, (int, float)):
                    net_score += score_val * weight
        
        scores["net_score"] = {"value": round(net_score, 2)}
        
        return scores
        
    except Exception as e:
        print(f"Error during scoring: {e}")
        return {"error": str(e), "net_score": {"value": 0.0}}

if __name__ == '__main__':
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
    app.run(host='127.0.0.1', port=8080, debug=True)
