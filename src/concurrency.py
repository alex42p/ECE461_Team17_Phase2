import concurrent.futures
import time
from typing import List, Any
from metric import Metric, MetricResult

def compute_all_metrics(
    context: dict[str, Any],
    metrics: List[Metric],
    max_workers: int | None = None
) -> List[MetricResult]:
    """
    Compute all metrics for a given Hugging Face model metadata in parallel.
    Each metric runs in its own thread, results collected as MetricResult.
    """
    results: List[MetricResult] = []

    def timed_compute(metric: Metric) -> MetricResult:
        t0 = time.perf_counter()
        result = metric.compute(context)
        latency = int((time.perf_counter() - t0) * 1000)
        # Preserve original details but override latency
        return MetricResult(
            name=result.name,
            value=result.value,
            details=result.details,
            latency_ms=latency,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(timed_compute, m): m for m in metrics}
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    return results
