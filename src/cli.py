# mypy: ignore-errors
import os
import sys
from pathlib import Path
import subprocess
from typing import Any, List, Dict
import argparse
import tester
import log
from base import parse_url_file
from ndjson import NDJSONEncoder
from entities import HFModel
from metric import Metric
from concurrency import compute_all_metrics
from huggingface import fetch_repo_metadata
from git_repo import fetch_bus_factor_raw_contributors
from storage import S3Storage
# Import concrete metric modules so their classes are registered as subclasses of Metric. 
# Metric.__subclasses__() only returns classes that have been imported/loaded, 
# so we must import these modules before constructing the metrics list below.
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

try:
    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
except KeyError:
    raise RuntimeError("GITHUB_TOKEN variable is missing, and you kinda need that.")

def install() -> None:
    """Implements ./run install"""
    rc = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q", "--no-warn-script-location"]).returncode
    sys.exit(rc)

def test() -> None:
    """Implements ./run test """
    log.setup_logging()
    rc = tester.run_tests()
    sys.exit(rc)

def score(url_file: str) -> None:
    """Implements ./run URL_FILE"""
    log.setup_logging()

    url_path = Path(url_file)
    url_objs = parse_url_file(url_path)

    models: List[HFModel] = []
    for u in url_objs:
        # wrap HFModelURL into HFModel
        model = HFModel(model_url=u)
        hf_metadata = fetch_repo_metadata(model)  # fills model.repo_id + model.metadata
        nof_code_ds: Dict[str, Any] = dict()
        nof_code_ds["nof_code"] = len(model.model_url.code)
        nof_code_ds["nof_ds"] = len(model.model_url.datasets)

        if model.model_url.code:
            repo_url = model.model_url.code[0].url
            repo_metadata = fetch_bus_factor_raw_contributors(repo_url, GITHUB_TOKEN)
            repo_metadata["repo_url"] = repo_url

        else:
            repo_metadata = {}

        if model.model_url.datasets:
            dataset_url = model.model_url.datasets[0].url
            hf_metadata["dataset_url"] = dataset_url

        model.metadata =  {"hf_metadata" : hf_metadata, "repo_metadata" : repo_metadata, "nof_code_ds" : nof_code_ds}

        # Initialize storage and construct metrics
        storage = S3Storage()
        metrics = [cls() for cls in Metric.__subclasses__()] # type: ignore

        # Inject dependencies for metrics that need them (backwards compatible)
        for metric in metrics:
            if isinstance(metric, tree_score.TreeScoreMetric):
                metric.storage = storage
            elif isinstance(metric, reviewedness.ReviewednessMetric):
                metric.github_token = GITHUB_TOKEN
        metric_results = compute_all_metrics(model.metadata, metrics, max_workers=8)
        # Convert metric results to a simple scores dict (like app.run_scoring)
        scores = {}
        for result in metric_results:
            scores[result.name] = {"value": result.value, "latency_ms": result.latency_ms}

        # Calculate net score using same weights as app.py
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

        model.add_results(metric_results)
        models.append(model)

    # Encode + print as NDJSON
    # NDJSONEncoder.print_records(models, True)   # exclude phase 2 metrics
    NDJSONEncoder.print_records(models)       # include all metrics
    sys.exit(0)


def main() -> None:
    """CLI entrypoint. Dispatches to test(), install(), or score()."""
    parser = argparse.ArgumentParser(
        prog="run",
        description="Score HF model URLs, run tests, or install dependencies.",
    )

    parser.add_argument("command", nargs="?", help="'test' to run tests, 'install' for dependencies, or path to URL file")

    # Use provided argv list or fall back to process argv
    raw_args: List[str] = sys.argv[1:] # list(argv) if argv is not None else 
    args = parser.parse_args(raw_args)

    # If user ran `run -h`, argparse will handle printing help/exit
    if not args.command:
        parser.print_help()
    elif args.command == "test":
        test()
    elif args.command == "install":
        install()
    else:
        # Treat any other argument as the URL file path
        score(args.command)


if __name__ == "__main__":
    main()
