import os
import sys
from pathlib import Path
import subprocess
from typing import Any
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
from storage import PackageStorage
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

    models: list[HFModel] = []
    for u in url_objs:
        # wrap HFModelURL into HFModel
        model = HFModel(model_url=u)
        hf_metadata = fetch_repo_metadata(model)  # fills model.repo_id + model.metadata
        nof_code_ds: dict[str, Any] = dict()
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
        storage = PackageStorage()
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

        # Save package into storage so future tree_score lookups can find this model
        try:
            pkg_name = model.repo_id or model.name or model.model_url.url
            storage.save_package(name=pkg_name, version="1.0", url=model.model_url.url, scores=scores)
        except Exception:
            # non-fatal; continue scoring other models
            pass

        model.add_results(metric_results)
        models.append(model)
        # print(model.metric_scores["size_score"])

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
    raw_args: list[str] = sys.argv[1:] # list(argv) if argv is not None else 
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
