# pragma: no cover
from pathlib import Path
import sys
from typing import Any
from cli_project import tester
from core import log
from urls.base import parse_url_file
from io.ndjson import NDJSONEncoder
from core.entities import HFModel
from metrics.base import Metric
from core.concurrency import compute_all_metrics

from adapters.huggingface import fetch_repo_metadata
from adapters.git_repo import fetch_bus_factor_raw_contributors


def test() -> None: # pragma: no cover
    """Implements ./run test """
    log.setup_logging()
    rc = tester.run_tests()

    sys.exit(rc)
    # print("0/0 test cases passed. 0% line coverage achieved.")

    # sys.exit(1)

def score(url_file: str) -> None: # pragma: no cover
    """Implements ./run URL_FILE"""
    log.setup_logging()

    url_path = Path(url_file)
    url_objs = parse_url_file(url_path)
    # print(url_objs)

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
