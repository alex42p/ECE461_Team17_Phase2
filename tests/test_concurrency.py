import time
from typing import Any, Dict, List

from src.concurrency import compute_all_metrics
from src.metric import Metric, MetricResult


class DummyMetric(Metric):
    def __init__(self, name: str, value: float = 1.0, fail: bool = False, delay: float = 0.0):
        self._name = name
        self._value = value
        self._fail = fail
        self._delay = delay

    @property
    def name(self) -> str:
        return self._name

    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        if self._fail:
            raise RuntimeError("boom")
        if self._delay:
            time.sleep(self._delay)
        return MetricResult(self._name, self._value, {"ok": True}, latency_ms=0)


def test_all_success() -> None:
    metrics: List[Metric] = [DummyMetric("m1", 1.0), DummyMetric("m2", 0.5)]
    results = compute_all_metrics({}, metrics, max_workers=2)

    assert {r.name for r in results} == {"m1", "m2"}
    assert all(isinstance(r, MetricResult) for r in results)


def test_with_failure() -> None:
    metrics: List[Metric] = [DummyMetric("ok", 1.0), DummyMetric("bad", fail=True)]
    results = compute_all_metrics({}, metrics, max_workers=2)

    names = {r.name for r in results}
    assert {"ok", "bad"} == names

    fail = next(r for r in results if r.name == "bad")
    assert fail.value == 0.0
    assert "error" in fail.details
