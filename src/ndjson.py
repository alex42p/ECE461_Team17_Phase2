import json
from typing import Any
from entities import HFModel

class NDJSONEncoder:
    """Utility to convert HFModel objects (with results) into NDJSON lines."""

    @staticmethod
    def encode(model: HFModel) -> str:
        """Return one NDJSON line for a model + its metric results."""
        record: dict[str, Any] = {
            "name": model.name,
            "category": model.model_url.category,
        }

        for r in model.metric_scores.values():
            record[r.name] = r.value
            record[f"{r.name}_latency"] = r.latency_ms

        if "net_score" not in record and model.metric_scores:
            # Define weights for each metric
            weights = {
                "license": 0.20,
                "code_quality": 0.18,
                "dataset_quality": 0.15,
                "ramp_up_time": 0.15,
                "dataset_and_code_score": 0.12,
                "bus_factor": 0.10,
                "performance_claims": 0.07,
                "size": 0.03,
            }

            # Compute weighted score
            net_score = 0.0
            for metric, weight in weights.items():
                if metric in model.metric_scores and isinstance(model.metric_scores[metric].value, (int, float)):
                    net_score += model.metric_scores[metric].value * weight # type: ignore

            record["net_score"] = round(net_score, 2)

            # Net score latency = sum of latencies
            record["net_score_latency"] = sum(r.latency_ms for r in model.metric_scores.values())
        return json.dumps(record)

    @staticmethod
    def encode_all(models: list[HFModel]) -> str:
        """Return full NDJSON (one line per model)."""
        return "\n".join(NDJSONEncoder.encode(m) for m in models)

    @staticmethod
    def print_records(models: list[HFModel]) -> None:
        print(NDJSONEncoder.encode_all(models))
