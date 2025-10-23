from pathlib import Path
import sys
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

def install() -> None:
    """Implements ./run install"""
    rc = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"]).returncode
    sys.exit(rc)

def test() -> None: # pragma: no cover
    """Implements ./run test """
    log.setup_logging()
    rc = tester.run_tests()
    sys.exit(rc)

def score(url_file: str) -> None: # pragma: no cover
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
            repo_metadata = fetch_bus_factor_raw_contributors(repo_url)
            repo_metadata["repo_url"] = repo_url

        else:
            repo_metadata = {}

        if model.model_url.datasets:
            dataset_url = model.model_url.datasets[0].url
            hf_metadata["dataset_url"] = dataset_url

        model.metadata =  {"hf_metadata" : hf_metadata, "repo_metadata" : repo_metadata, "nof_code_ds" : nof_code_ds}

        # print(model.metadata["hf_metadata"].get("repo_url"))
        # metric_results: list[MetricResult] = []
        # for metric_cls in Metric.__subclasses__():
        #     metric = metric_cls()
        #     result = metric.compute(model.metadata)
        #     metric_results.append(result)
        metrics = [cls() for cls in Metric.__subclasses__()]
        metric_results = compute_all_metrics(model.metadata, metrics, max_workers=8)

        model.add_results(metric_results)
        # print(model.metric_scores)
        models.append(model)
        # print(model.metric_scores["size_score"])

    # Encode + print as NDJSON
    NDJSONEncoder.print_records(models)
    sys.exit(0)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint. Dispatches to test(), install(), or score()."""
    parser = argparse.ArgumentParser(
        prog="run",
        description="Score HF model URLs, run tests, or install dependencies.",
    )

    parser.add_argument("command", nargs="?", help="'test' to run tests, 'install' for dependencies, or path to URL file")

    # Use provided argv list or fall back to process argv
    raw_args: list[str] = list(argv) if argv is not None else sys.argv[1:]
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
