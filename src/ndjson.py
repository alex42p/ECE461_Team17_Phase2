import json
from typing import Any, Dict
from entities import HFModel

class NDJSONEncoder:
    """Utility to convert HFModel objects (with results) into NDJSON lines."""

    @staticmethod
    def encode(model: HFModel, phase_one: bool = False) -> str:
        """Return one NDJSON line for a model + its metric results."""
        record: dict[str, Any] = {
            "name": model.name,
            "category": model.model_url.category,
        }

        for r in model.metric_scores.values():
            record[r.name] = r.value
            record[f"{r.name}_latency"] = r.latency_ms

        if "net_score" not in record and model.metric_scores:
            if phase_one:
                weights: Dict[str, float] = {
                "ramp_up_time": 0.20,
                "license": 0.15,
                "dataset_and_code_score": 0.10,
                "performance_claims": 0.10,
                "bus_factor": 0.10,
                "code_quality": 0.15,
                "dataset_quality": 0.15,
                "size_score": 0.05
                }
            else:
                weights: Dict[str, float] = {
                    "ramp_up_time": 0.15,           # Reduced from 0.20
                    "license": 0.12,                # Reduced from 0.15
                    "dataset_and_code_score": 0.10, # Same
                    "performance_claims": 0.08,     # Reduced from 0.10
                    "bus_factor": 0.10,             # Same
                    "code_quality": 0.12,           # Reduced from 0.15
                    "dataset_quality": 0.12,        # Reduced from 0.15
                    "size_score": 0.05,             # Same
                    "reproducibility": 0.10,        # NEW
                    "reviewedness": 0.03,           # NEW
                    "tree_score": 0.03,             # NEW
                }

            # Compute weighted score
            net_score = 0.0
            for metric, weight in weights.items():
                # print("Metric:", metric, "; Score:", model.metric_scores[metric].value)
                if metric in model.metric_scores and isinstance(model.metric_scores[metric].value, float):
                    net_score += model.metric_scores[metric].value * weight # type: ignore

            record["net_score"] = round(net_score, 2)

            # Net score latency = maximum of submetric latencies
            record["net_score_latency"] = max((r.latency_ms for r in model.metric_scores.values()), default=1) + 100
        return json.dumps(record)

    @staticmethod
    def encode_all(models: list[HFModel], phase_one: bool = False) -> str:
        """Return full NDJSON (one line per model)."""
        return "\n".join(NDJSONEncoder.encode(m, phase_one) for m in models)

    @staticmethod
    def print_records(models: list[HFModel], phase_one: bool = False) -> None:
        print(NDJSONEncoder.encode_all(models, phase_one))
