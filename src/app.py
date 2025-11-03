"""
This file is going to house our Flask app to run the website. It will hold all of the API endpoints as well as the logic to render the HTML templates.
"""

import os
from typing import Any
from flask import Flask, request, jsonify, render_template, session 

# Import storage
from storage import PackageStorage

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

app = Flask(__name__)

# Initialize storage
storage = PackageStorage()

# Get GitHub token
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/package', methods=['POST'])
def upload_package():
    """
    Ingest a package and score it.
    
    Request body:
    {
        "name": "package-name",
        "version": "1.0.0",
        "url": "https://huggingface.co/model-name"
    }
    
    Returns:
        Package ID and scores
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body required"}), 400
        
        name = data.get("name")
        version = data.get("version", "1.0.0")
        url = data.get("url")
        
        # Validation
        if not name:
            return jsonify({"error": "Package name required"}), 400
        
        if not url:
            return jsonify({"error": "Package URL required"}), 400
        
        # Run scoring
        scores = run_scoring(url)
        
        # Save package
        package_info = storage.save_package(
            name=name,
            version=version,
            url=url,
            scores=scores
        )
        
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
def get_package(package_id: str):
    """
    Retrieve package by ID.
    
    Returns:
        Package metadata and scores
    """
    try:
        package = storage.get_package(package_id)
        
        if not package:
            return jsonify({"error": f"Package {package_id} not found"}), 404
        
        return jsonify(package), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/packages/byRegex', methods=['GET'])
def search_by_regex():
    """
    Search packages by regex pattern.
    
    Query parameter:
        RegEx: Regular expression pattern to match package names
    
    Examples:
        GET /packages/byRegex?RegEx=bert
        GET /packages/byRegex?RegEx=bert.*uncased
        GET /packages/byRegex?RegEx=^gpt
    
    Returns:
        List of matching packages sorted by net score (highest first)
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
        metrics = [cls() for cls in Metric.__subclasses__()] # type: ignore
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
    print("\nEndpoints:")
    print("  POST /package              - Ingest and score a package")
    print("  GET  /package/<id>         - Retrieve package by ID")
    print("  GET  /packages/byRegex     - Search packages by regex")
    print("\nListening on http://127.0.0.1:8080")
    print("=" * 60)
    app.run(host='127.0.0.1', port=8080, debug=True)