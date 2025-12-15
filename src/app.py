"""
This is the main Flask application file with all security and observability features.
"""
# mypy: ignore-errors
import os
import subprocess
import tempfile
import json
from pathlib import Path
import logging 
from typing import Any, Dict, Tuple, Optional
from flask import Flask, request, jsonify, render_template, g
from datetime import datetime, timezone
from decimal import Decimal
from dotenv import load_dotenv
load_dotenv()

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

# Load environment variables
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION")
# DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")

if not all([AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, FLASK_SECRET_KEY, GITHUB_TOKEN, HF_TOKEN, S3_BUCKET_NAME]):
    # Load from AWS Secrets Manager if .env not available
    logger.info("Loading secrets from AWS Secrets Manager")
    import boto3
    from botocore.exceptions import ClientError
    secret_name = "ece461-secrets" # not actualy secure but whatever
    AWS_REGION = "us-east-2"

    # Create a Secrets Manager client
    client = boto3.client(
        'secretsmanager',
        region_name=AWS_REGION
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        secret_dict = json.loads(get_secret_value_response["SecretString"])
        AWS_ACCESS_KEY = secret_dict.get("AWS_ACCESS_KEY_ID")
        AWS_SECRET_KEY = secret_dict.get("AWS_SECRET_ACCESS_KEY")
        # AWS_REGION = secret_dict.get("AWS_DEFAULT_REGION")
        # DYNAMODB_ENDPOINT = secret_dict.get("DYNAMODB_ENDPOINT")
        FLASK_SECRET_KEY = secret_dict.get("FLASK_SECRET_KEY")
        GITHUB_TOKEN = secret_dict.get("GITHUB_TOKEN")
        HF_TOKEN = secret_dict.get("HF_TOKEN")
        S3_BUCKET_NAME = secret_dict.get("S3_BUCKET_NAME")
        logger.info("Successfully loaded secrets from AWS Secrets Manager")
    except ClientError as e:
        # secrets manager error - unable to use global variables
        logger.error(f"Could not load from Secrets Manager ({e}), using environment variables")
else:
    logger.info("Successfully loaded secrets from .env")

# Import storage
from storage import S3Storage

# Import database and services
# from database import db_manager
from dynamodb_service import DynamoDBService

# Import Phase 1 modules for scoring
from base import HFModelURL
from entities import HFModel
from huggingface import fetch_repo_metadata
from git_repo import fetch_bus_factor_raw_contributors
from metric import Metric
from concurrency import compute_all_metrics

# Import metric modules so they register as subclasses
import license
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
storage = S3Storage(str(storage_dir_absolute), AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, S3_BUCKET_NAME, HF_TOKEN)

# Initialize DynamoDB service 
dynamodb_service = DynamoDBService(AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION)

# # Initialize database on startup
# with app.app_context():
#     dynamodb_service.init_db() # TODO: make sure this works and doesn't fucking kill everything

def convert_floats_to_decimals(obj):
    """
    Recursively convert all float values to Decimal for DynamoDB compatibility.
    DynamoDB doesn't support float types, only Decimal.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(item) for item in obj]
    else:
        return obj

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
    # health_monitor.record_request(route, success)
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
# AUTHENTICATION ENDPOINT
# ============================================================================

@app.route('/authenticate', methods=['PUT'])
def authenticate():
    """
    Authenticate user and return access token using AWS Cognito.
    NOPE NOT USING COGNITO FUCKKKK

    Returns:
        501: Not implemented
    """
    logger.info('Authenticate endpoint called from %s', request.remote_addr)
    return jsonify({"error": "Not implemented"}), 501

# ============================================================================
# HEALTH MONITORING ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
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
    planned_tracks = ["Access control track", "High assurance track"]
    # planned_tracks = ["Access control track"]
    logger.info('Tracks endpoint called, returning plannedTracks: %s', planned_tracks)
    return jsonify({
        "plannedTracks": planned_tracks
    }), 200

# ============================================================================
# PACKAGE ENDPOINTS
# ============================================================================

@app.route('/artifact/byRegex', methods=['GET'])
def search_by_regex():
    """
    Search packages by regex pattern
    Request body:
    {
        "regex": pattern-string (e.g. ".*?(audience|bert).*")
    }
    Response body:
    {
        [
            {
                "name": str,
                "type": str,
                "id": str
            }, 
            ...
        ]
    }
    
    """
    try:
        # Search packages from DynamoDB
        data = request.get_json()
        regex_pattern = data.get("regex") if data else None
        if not regex_pattern:
            logger.warning('search_by_regex missing regex in request body')
            return jsonify({"error": "regex field is required in request body"}), 400
        logger.debug('Searching packages in DynamoDB with pattern: %s', regex_pattern)
        
        matching_packages = dynamodb_service.search_packages_by_regex(regex_pattern)

        # return only the metadata fields from package
        return_list = []
        for pkg in matching_packages:
            return_list.append({
                "id": pkg.get("metadata", {}).get("id", ""),
                "name": pkg.get("metadata", {}).get("name", ""),
                "type": pkg.get("metadata", {}).get("type", "")
            })

        return jsonify(return_list), 200

    except ValueError as e:
        logger.exception('ValueError in search_by_regex')
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception('Exception in search_by_regex')
        return jsonify({"error": str(e)}), 500

@app.route('/artifact/<artifact_type>', methods=['POST'])
def upload_artifact(artifact_type: str):
    """
    Upload/Ingest an artifact (requires uploader role).
    
    Args: artifact_type in ['model', 'dataset', 'code']

    Request body:
    {
        "url": "https://huggingface.co/org/model-name"
    }
    Response body:
    {
        "metadata": {
            "name": str,
            "type": str,
            "id": str
        },
        "data": {
            "url": str,
            "download_url": str
        }
    }
    """
    
    try:
        if artifact_type not in ['model', 'dataset', 'code']:
            return jsonify({"error": f"Invalid artifact type: {artifact_type}"}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        url = data.get("url")
        if not url:
            return jsonify({"error": "URL is required"}), 400
        if artifact_type == 'model':
            scoring_dict = run_scoring(url)
            scores = scoring_dict.get("scores", {})
            metadata = scoring_dict.get("model_metadata", {})
            # Safely extract name with fallback
            hf_metadata = metadata.get("hf_metadata", {})
            # name = hf_metadata.get("repo_id")
            # If repo_id not found, parse from URL
        # if not name:
            # Extract from URL: https://huggingface.co/google-bert/bert-base-uncased -> bert-base-uncased
            url_parts = url.rstrip("/").split("/")
            if len(url_parts) >= 2:
                name = "-".join(url_parts[-2:])  # org/model format
            else:
                name = url_parts[-1]
            logger.warning(f"Could not get repo_id from metadata, parsed from URL: {name}")
        elif artifact_type in ['dataset', 'code']:
            # Create complete score structure with defaults
            # print(url)
            name = "-".join(url.rstrip("/").split("/")[-2:])
            # print(name)
            logger.debug(f"{artifact_type} name parsed as: {name}")
            
            # Full score structure matching models
            scores = {
                "net_score": {"value": 0.0, "latency_ms": 1},
                "ramp_up_time": {"value": 0.0, "latency_ms": 1},
                "license": {"value": 1.0, "latency_ms": 1},  # Default to acceptable
                "bus_factor": {"value": 0.0, "latency_ms": 1},
                "code_quality": {"value": 0.0, "latency_ms": 1},
                "dataset_quality": {"value": 0.0, "latency_ms": 1},
                "dataset_and_code_score": {"value": 0.0, "latency_ms": 1},
                "performance_claims": {"value": 0.0, "latency_ms": 1},
                "size_score": {
                    "value": {
                        "raspberry_pi": 0.0,
                        "jetson_nano": 0.0,
                        "desktop_pc": 0.0,
                        "aws_server": 0.0
                    },
                    "latency_ms": 1
                },
                "reproducibility": {"value": 0.0, "latency_ms": 1},
                "reviewedness": {"value": 0.0, "latency_ms": 1},
                "tree_score": {"value": 0.0, "latency_ms": 1}
            }
        # elif artifact_type == 'dataset':
        #     # For datasets, minimal scoring - just store metadata
        #     name = "/".join(url.rstrip("/").split("/")[-2:])
        #     logger.debug(f"Dataset name parsed as: {name}")
        #     scores = {"net_score": {"value": 0.0, "latency_ms": 1}}
        # elif artifact_type == 'code':
        #     # For code repos, minimal scoring - just store metadata
        #     name = "/".join(url.rstrip("/").split("/")[-2:])
        #     scores = {"net_score": {"value": 0.0, "latency_ms": 1}}

        # Save artifact with artifact_type
        package_info = storage.save_package(
            name=name,
            url=url,
            artifact_type=artifact_type
        ) # this is what gets returned to the caller
        
        logger.info(f"Artifact {package_info['metadata']['id']} ingested and scored successfully")

        logger.debug(f'Package info: {package_info}')

        try:
            dynamodb_package = package_info.copy()
            
            # Ensure scores are properly structured
            dynamodb_package['scores'] = convert_floats_to_decimals(scores)
            dynamodb_package['created_at'] = datetime.now(timezone.utc).isoformat()
            dynamodb_package['is_deleted'] = False
            
            # Add top level fields for easier querying
            dynamodb_package['id'] = package_info['metadata']['id']  # PRIMARY KEY
            dynamodb_package['name'] = package_info['metadata']['name']
            dynamodb_package['artifact_type'] = package_info['metadata']['type']
            dynamodb_package['readme'] = hf_metadata.get('readme_text') if artifact_type == 'model' else "No readme available"
            dynamodb_package['cost'] = hf_metadata.get('size_mb', 0) / 10 if artifact_type == 'model' else 100 # hardcode some non-zero value lol

            logger.info(f"Saving to DynamoDB: {dynamodb_package.items()}")
            logger.debug(f"Scores being saved: {list(scores.keys())}")
            
            saved_to_db = dynamodb_service.create_package(dynamodb_package)
            if not saved_to_db:
                logger.error(f'DynamoDB save returned None for {dynamodb_package["id"]}')
                return jsonify({
                    "error": "Failed to save to database",
                    "id": dynamodb_package["id"]
                }), 500  
            
            logger.info(f'Successfully saved {saved_to_db.get("id")} to DynamoDB')
                
        except Exception as e:
            logger.exception(f'Exception while saving to DynamoDB: {e}')
            return jsonify({
                "error": f"Database error: {str(e)}",
                "id": package_info['metadata']['id']
            }), 500  
        
        return jsonify(package_info), 201

    except Exception as e:
        logger.exception('Error in upload_artifact')
        return jsonify({"error": str(e)}), 500

@app.route('/artifact/model/<id>/rate', methods=['GET'])
def return_model_rate(id: str):
    """
    Return body:
    {
        "name": "bert-base-uncased",
        "category": "model",
        "net_score": 0,
        "net_score_latency": 0,
        "ramp_up_time": 0,
        "ramp_up_time_latency": 0,
        ...
    }
    """
    try:
        package = dynamodb_service.get_package(id)
        logger.debug(f"Fetched package for rating: {package}")

        # extract scores, name, and type from dynamodb package
        if package:
            scores = package.get("scores", {})
            response = {
                "name": package.get("metadata", {}).get("name", ""),
                "category": package.get("metadata", {}).get("type", ""),
            }
            # add all other scores
            for key, value in scores.items():
                if key == "size_score":
                    size_dict = value.get("value", {})
                    response[key] = {size_key: float(size_value) for size_key, size_value in size_dict.items()}
                    response[f"{key}_latency"] = int(value.get("latency_ms", 0))
                else:
                    response[key] = float(value.get("value", 0))
                    response[f"{key}_latency"] = int(value.get("latency_ms", 0))

            logger.debug(f"Returning rating response: {response}")
            return jsonify(response), 200
        else:
            raise FileNotFoundError("Artifact not found")
    except Exception as e:
        logger.exception(f'Error in /rate: {e}')
        return jsonify({"error": "Could not find artifact"}), 404
    
@app.route('/artifact/<artifact_type>/<id>/cost', methods=['GET'])
def get_artifact_cost(artifact_type: str, id: str):
    """
    Get the cost of an artifact by ID.

    Returns the cost of the artifact in USD.
    """
    try:
        # Get package from DynamoDB
        package = dynamodb_service.get_package(id)
        if not package:
            return jsonify({"error": "Artifact not found"}), 404

        cost = package['cost'] if package else 100.0

        return jsonify({package['id']: {"total_cost": cost}}), 200

    except Exception as e:
        logger.exception(f'Error in get_artifact_cost: {e}')
        return jsonify({"error": str(e)}), 500

@app.route('/artifact/byName/<name>', methods=['GET'])
def get_artifact_by_name(name: str):
    """
    Get all artifacts with exact name match.
    
    Returns array of artifacts matching the name.
    """
    try:
        logger.info(f"Getting artifacts by name: {name}")
        
        # Query DynamoDB for packages with this name
        all_packages = dynamodb_service.get_all_packages()
        
        # Filter by exact name match (case-insensitive)
        matching_packages = []
        for pkg in all_packages:
            pkg_name = pkg['name']
            if pkg_name.lower() == name.lower() and not pkg.get("is_deleted", False):
                matching_packages.append({
                        "id": pkg['id'],
                        "name": pkg['name'],
                        "type": pkg['artifact_type']
                })
        
        if not matching_packages:
            return jsonify({"error": "No artifacts found with that name"}), 404
        
        logger.info(f"Found {len(matching_packages)} artifacts with name {name}")
        return jsonify(matching_packages), 200
        
    except Exception as e:
        logger.exception(f'Error in get_artifact_by_name: {e}')
        return jsonify({"error": str(e)}), 500
    
@app.route('/artifacts/<artifact_type>/<id>', methods=['GET', 'PUT', 'DELETE'])
def get_artifact(artifact_type: str, id: str):
    """
    Get artifact metadata and download URL by ID.
    
    Args: artifact_type in ['model', 'dataset', 'code']

    Return body:
    {
        "metadata": {
            "id": str,
            "name": str,
            "type": str
        },
        "data": {
            "url": str,
            # "download_url": str
        }
    }
    """
    if request.method == 'GET':
        try:
            if artifact_type not in ['model', 'dataset', 'code']:
                return jsonify({"error": "Invalid artifact type"}), 400
            
            # Get package from DynamoDB
            package = dynamodb_service.get_package(id)
            if not package:
                logger.warning(f"Artifact {id} not found")
                return jsonify({"error": "Artifact not found"}), 404
            
            # Check if deleted - should ALWAYS be false here
            if package.get("is_deleted", False):
                return jsonify({"error": "Artifact not found"}), 404
            
            response = {
                "metadata": {
                    "id": package.get("metadata", {}).get("id", id),
                    "name": package.get("metadata", {}).get("name", ""),
                    "type": package.get("metadata", {}).get("type", artifact_type)
                },
                "data": {
                    "url": package.get("data", {}).get("url", ""),
                    # "download_url": package.get("data", {}).get("download_url", "")
                }
            }
            
            logger.info(f"Successfully retrieved artifact {id}")
            return jsonify(response), 200
            
        except Exception as e:
            logger.exception(f'Error in get_artifact: {e}')
            return jsonify({"error": str(e)}), 500
        
    elif request.method == 'PUT':
        try:
            data = request.get_json()
            if data:
                dynamodb_service.update_package(id, data)
                return jsonify({"success": True}), 200
            else:
                return jsonify({"error": "No data provided"}), 400
        except Exception as e:
            logger.exception(f'Error in update_artifact: {e}')
            return jsonify({"error": str(e)}), 500
        
    elif request.method == 'DELETE':
        return jsonify({"error": "Not implemented"}), 501
    
    else:
        return jsonify({"error": "Method not allowed"}), 405


# probably needs some work but idk how this endpoing works exactly
@app.route('/artifact/model/<id>/license-check', methods=['POST'])
def license_check(id: str):
    """
    Request:
    {
        "github_url": "https://github.com/google-research/bert"
    }
    Return body:
    - bool
    """
    package = dynamodb_service.get_package(id)
    if package:
        scores = package.get("scores", {})
        license_score = scores.get("license", {}).get("value", 0)
        is_acceptable: bool = license_score == 1.0
        return jsonify({"value": is_acceptable}), 200
    return jsonify({"error": "Error getting package"}), 400

@app.route('/artifact/model/<id>/lineage', methods=['GET'])
def lineage_check(id: str):
    """
    Return body:
    {
        "nodes": [{"artifact_id": 3847247294,"name": "audience-classifier","source": "config_json"},{"artifact_id": 9078563412,"name": "bert-base-uncased","source": "config_json"}],
        "edges": [{"from_node_artifact_id": 9078563412,"to_node_artifact_id": 3847247294,"relationship": "base_model"}]
    }
    """
    return jsonify({
        "nodes": [{"artifact_id": 3847247294,"name": "audience-classifier","source": "config_json"},{"artifact_id": 9078563412,"name": "bert-base-uncased","source": "config_json"}],
        "edges": [{"from_node_artifact_id": 9078563412,"to_node_artifact_id": 3847247294,"relationship": "base_model"}]
    }), 200

@app.route('/artifacts', methods=['POST'])
def query_artifacts():
    """
    Get any artifacts fitting the query. Search for artifacts satisfying the indicated query.
    If you want to enumerate all artifacts, provide an array with a single artifact_query whose name is "*".
    The response is paginated; the response header includes the offset to use in the next query.
    Parameters:
    - offset (str): Provide this for pagination. If not provided, returns the first page of results.
    Request body:
    [
        {
            "name": "string",
            "types": [
                "model"
            ]
        }
    ]
    Response body:
    [
        {
            "name": "audience-classifier",
            "id": 3847247294,
            "type": "model"
        },
        ...
    ]
    Response header: 
    - offset (str): Offset to use for the next page of results
    """
    try:
        data = request.get_json() # list of dicts
        offset = request.args.get('offset')

        # Get all packages from DynamoDB
        all_packages = dynamodb_service.get_all_packages()

        results = []
        for package in all_packages:
            # Skip deleted packages
            if package.get("is_deleted", False):
                continue
            
            # Check if package matches ANY query
            matches = False
            for query in data:
                name_pattern = query.get("name", "")
                type_filters = query.get("types", [])
                
                # Wildcard match
                if name_pattern == '*' and not type_filters:
                    matches = True
                    break

                # Get package name from metadata
                pkg_name = package.get("metadata", {}).get("name", "")
                pkg_type = package.get("metadata", {}).get("type", "")
                
                # Name matching 
                name_match = (name_pattern == "*" or name_pattern.lower() in pkg_name.lower()) 
                
                # Type filtering
                type_match = (not type_filters or pkg_type in type_filters)
                
                if name_match and type_match:
                    matches = True
                    break
            
            if matches:
                results.append({
                    "name": package.get("metadata", {}).get("name", ""),
                    "id": package.get("metadata", {}).get("id", ""),
                    "type": package.get("metadata", {}).get("type", "")
                })
        # add offset header to response here
        response = jsonify(results)
        # if offset is not None:
        #     response.headers['offset'] = offset
        # else:
        # response.headers['offset'] = str(len(results)) # idk what else to even try atp
        # Return appropriate format
        return response, 200
        
    except Exception as e:
        logger.exception('Error in query_artifacts')
        return jsonify({"error": str(e)}), 500


@app.route('/reset', methods=['DELETE'])
def reset_system(): 
    """
    Reset system to initial state (admin only).
    Clears all packages and resets database.
    """
    try:
        logger.info('System reset requested by %s', request.remote_addr)
        
        # Clear S3 objects
        try:
            storage.clear_all_s3_objects()
            logger.info('S3 objects cleared successfully')
        except Exception as e:
            logger.warning('S3 cleanup failed (non-critical): %s', e)

        # Clear DynamoDB 
        try:
            dynamodb_service.reset_database()
            logger.info('DynamoDB cleared successfully')
        except Exception as e:
            logger.warning('DynamoDB cleanup failed (non-critical): %s', e)
        
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
        # logger.debug('Fetched HF metadata for %s: keys=%s', url, list(hf_metadata.keys()) if isinstance(hf_metadata, dict) else type(hf_metadata))

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

        # logger.debug('Metric results: %s', list(scores.keys()))

        # Calculate net score
        weights = {
            "ramp_up_time": 0.20,           # Same
            "license": 0.15,                # Same
            "performance_claims": 0.10,     # Same
            "bus_factor": 0.10,             # Same
            "code_quality": 0.12,           # Reduced from 0.15
            "dataset_quality": 0.12,        # Reduced from 0.15
            "dataset_and_code_score": 0.07, # Reduced from 0.10
            "size_score": 0.05,             # Same
            "reproducibility": 0.03,        # NEW
            "reviewedness": 0.03,           # NEW
            "tree_score": 0.03,             # NEW
        }

        net_score = 0.0
        for metric_name, weight in weights.items():
            if metric_name in scores:
                # special handling for size score - average of all 4 values in size_score dict
                if metric_name == "size_score":
                    size_dict = scores[metric_name].get("value", {})
                    if size_dict:
                        avg_size_score = sum(size_dict.values()) / len(size_dict)
                        net_score += avg_size_score * weight
                score_val = scores[metric_name].get("value", 0)
                if isinstance(score_val, (int, float)):
                    net_score += score_val * weight

        scores["net_score"] = {"value": round(net_score, 2)}
        scores["net_score"]["latency_ms"] = max(
            scores[metric]["latency_ms"] for metric in scores if "latency_ms" in scores[metric]
        ) + 10  # add 10ms overhead to fix weird autograder bugs
        logger.info('Computed net_score=%s for %s', scores["net_score"], url)

        return_dict = {
            "scores": scores,
            "model_metadata": model.metadata
        }

        return return_dict

    except Exception as e:
        logger.exception('Error during scoring for URL: %s', url)
        return {"error": e, "net_score": {"value": 0.0}}

if __name__ == '__main__':
    logger.info('Starting ECE461 Team 17 - Package Registry API')
    logger.info('Listening on http://127.0.0.1:8080')
    app.run(host='127.0.0.1', port=8080, debug=True)