"""In-process LLM metrics in Prometheus text format (no extra dependency).

Each process counts its own calls; scrape every API/worker process, or use
the `llm_requests` table (shared by all processes) for per-organization and
per-job questions. Organization ids are never metric labels.
"""

import threading
from collections import defaultdict

LATENCY_BUCKETS = (0.5, 1, 2, 5, 10, 20, 40, 80, 160)
WAIT_BUCKETS = (0.1, 0.5, 1, 5, 15, 30, 60, 120, 300, 600)

HELP = {
    "llm_requests_total": ("counter", "Provider requests sent (including failures)."),
    "llm_requests_success_total": ("counter", "Provider requests that succeeded."),
    "llm_requests_failed_total": ("counter", "Provider requests that failed, by error kind."),
    "llm_rate_limit_total": ("counter", "Rate limits hit: source=provider (429) or local quota."),
    "llm_retries_total": ("counter", "Retries after a transient failure."),
    "llm_fallback_total": ("counter", "Calls answered by a fallback model."),
    "llm_cache_hits_total": ("counter", "Calls answered from the cache."),
    "llm_input_tokens_total": ("counter", "Input tokens reported by providers."),
    "llm_output_tokens_total": ("counter", "Output tokens reported by providers."),
    "llm_queue_wait_seconds": ("histogram", "Time waiting for quota before a request."),
    "llm_latency_seconds": ("histogram", "Provider request duration."),
    "llm_concurrency": ("gauge", "Provider requests in flight in this process."),
}

Labels = tuple[tuple[str, str], ...]


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.counters: dict[str, dict[Labels, float]] = defaultdict(lambda: defaultdict(float))
        self.gauges: dict[str, dict[Labels, float]] = defaultdict(lambda: defaultdict(float))
        self.histograms: dict[str, dict[Labels, list[float]]] = defaultdict(dict)

    @staticmethod
    def _labels(labels: dict[str, str]) -> Labels:
        return tuple(sorted((k, str(v)) for k, v in labels.items()))

    def inc(self, name: str, value: float = 1, **labels: str) -> None:
        with self._lock:
            self.counters[name][self._labels(labels)] += value

    def gauge(self, name: str, delta: float, **labels: str) -> None:
        with self._lock:
            self.gauges[name][self._labels(labels)] += delta

    def observe(self, name: str, value: float, **labels: str) -> None:
        buckets = WAIT_BUCKETS if name == "llm_queue_wait_seconds" else LATENCY_BUCKETS
        with self._lock:
            # [bucket counts..., +Inf count, sum]
            row = self.histograms[name].setdefault(self._labels(labels), [0.0] * (len(buckets) + 2))
            for i, bound in enumerate(buckets):
                if value <= bound:
                    row[i] += 1
            row[-2] += 1
            row[-1] += value

    def value(self, name: str, **labels: str) -> float:
        """Sum of a counter over series matching `labels` (tests, dashboards)."""
        wanted = set(self._labels(labels))
        return sum(v for k, v in self.counters.get(name, {}).items() if wanted <= set(k))

    def render(self) -> str:
        def fmt(labels: Labels, extra: tuple[tuple[str, str], ...] = ()) -> str:
            pairs = [*labels, *extra]
            if not pairs:
                return ""
            body = ",".join(
                f'{k}="{v.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
                for k, v in pairs
            )
            return "{" + body + "}"

        lines: list[str] = []
        with self._lock:
            for name, (kind, text) in HELP.items():
                lines += [f"# HELP {name} {text}", f"# TYPE {name} {kind}"]
                if kind == "counter":
                    for labels, v in self.counters.get(name, {}).items():
                        lines.append(f"{name}{fmt(labels)} {v:g}")
                elif kind == "gauge":
                    for labels, v in self.gauges.get(name, {}).items():
                        lines.append(f"{name}{fmt(labels)} {v:g}")
                else:
                    buckets = WAIT_BUCKETS if name == "llm_queue_wait_seconds" else LATENCY_BUCKETS
                    for labels, row in self.histograms.get(name, {}).items():
                        for bound, count in zip(buckets, row, strict=False):
                            lines.append(
                                f"{name}_bucket{fmt(labels, (('le', f'{bound:g}'),))} {count:g}"
                            )
                        lines.append(f"{name}_bucket{fmt(labels, (('le', '+Inf'),))} {row[-2]:g}")
                        lines.append(f"{name}_count{fmt(labels)} {row[-2]:g}")
                        lines.append(f"{name}_sum{fmt(labels)} {row[-1]:g}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
