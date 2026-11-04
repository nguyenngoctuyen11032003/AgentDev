"""Execution engine benchmark: real engine, fake model with a fixed latency (no tokens spent).

Measures what the engine itself adds, and how well independent agents run side by side:

    uv run python -m scripts.bench_engine            # default 0.5 s per model call
    uv run python -m scripts.bench_engine --latency 1 --json

Shapes:
  chain_10        10 agents one after another (no parallelism possible): ideal = 10 x latency
  fanout_10       Plan -> 10 independent workers -> Merge: ideal = 3 x latency
  diamond         Plan -> (A, B -> C) -> Merge, critical path Plan-B-C-Merge: ideal = 4 x latency
  overhead_20     20 agents in a chain with zero latency: engine cost per step
  fanout_fail     fanout_10 where one worker fails: does the run stop, and how many workers ran
  fanout_fail_soft  same, workers marked continue_on_error: Merge should still run with 9 results + 1 note

Efficiency = ideal / measured (1.0 = no time lost). Numbers are printed as measured; nothing is estimated.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List

import yaml

from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.human_prompt import HumanPromptService, PromptResult


class FakeProvider:
    """Sleeps ``latency`` seconds, then answers; records start/end times and the peak number of calls in flight."""

    latency = 0.5
    fail_nodes: set = set()
    lock = threading.Lock()
    in_flight = 0
    peak = 0
    calls: List[tuple] = []

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        cls = type(self)
        node_id = self.config.node_id
        with cls.lock:
            cls.in_flight += 1
            cls.peak = max(cls.peak, cls.in_flight)
        start = time.perf_counter()
        try:
            if cls.latency:
                time.sleep(cls.latency)
            if node_id in cls.fail_nodes:
                raise RuntimeError(f"{node_id} failed (benchmark)")
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=f"{node_id} done"))
        finally:
            with cls.lock:
                cls.in_flight -= 1
                cls.calls.append((node_id, start, time.perf_counter()))

    def extract_token_usage(self, response):
        return None

    @classmethod
    def reset(cls, latency: float, fail_nodes=()):
        cls.latency, cls.fail_nodes = latency, set(fail_nodes)
        cls.in_flight = cls.peak = 0
        cls.calls = []


def install_fake_provider() -> None:
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    agent_executor_module.resolve_connection = lambda _id: creds
    ProviderRegistry.get_provider = staticmethod(lambda _name: FakeProvider)
    HumanPromptService.request = lambda *a, **k: PromptResult(text="ok")


def _agent(node_id: str) -> dict:
    return {"id": node_id, "type": "agent", "description": node_id,
            "config": {"connection": "fake", "provider": "fake", "name": "fake-model", "role": node_id}}


def _graph(nodes: List[str], edges: List[tuple], start: str, end: str) -> dict:
    return {"version": "0.4.0", "graph": {
        "id": "bench", "start": [start], "end": [end], "log_level": "WARNING",
        "nodes": [_agent(n) for n in nodes],
        "edges": [{"from": a, "to": b} for a, b in edges]}}


def _soft(definition: dict, node_ids: List[str]) -> dict:
    for node in definition["graph"]["nodes"]:
        if node["id"] in node_ids:
            node["continue_on_error"] = True
    return definition


def shapes() -> Dict[str, dict]:
    workers = [f"W{i}" for i in range(1, 11)]
    chain = [f"S{i}" for i in range(1, 11)]
    long_chain = [f"S{i}" for i in range(1, 21)]
    fan_edges = [("Plan", w) for w in workers] + [(w, "Merge") for w in workers]
    return {
        "chain_10": {"graph": _graph(chain, list(zip(chain, chain[1:])), chain[0], chain[-1]), "ideal_steps": 10},
        "fanout_10": {"graph": _graph(["Plan", *workers, "Merge"], fan_edges, "Plan", "Merge"), "ideal_steps": 3},
        "diamond": {"graph": _graph(["Plan", "A", "B", "C", "Merge"],
                                    [("Plan", "A"), ("Plan", "B"), ("B", "C"), ("A", "Merge"), ("C", "Merge")],
                                    "Plan", "Merge"), "ideal_steps": 4},
        "overhead_20": {"graph": _graph(long_chain, list(zip(long_chain, long_chain[1:])), "S1", "S20"),
                        "ideal_steps": 0, "latency": 0.0},
        "fanout_fail": {"graph": _graph(["Plan", *workers, "Merge"], fan_edges, "Plan", "Merge"), "ideal_steps": 3,
                        "fail": ["W3"]},
        "fanout_fail_soft": {"graph": _soft(_graph(["Plan", *workers, "Merge"], fan_edges, "Plan", "Merge"), workers),
                             "ideal_steps": 3, "fail": ["W3"]},
    }


def run_shape(name: str, spec: dict, latency: float, folder: Path) -> dict:
    from agentdev.runtime.sdk import run_workflow

    lat = spec.get("latency", latency)
    FakeProvider.reset(lat, spec.get("fail", ()))
    path = folder / f"{name}.yaml"
    path.write_text(yaml.safe_dump(spec["graph"]), encoding="utf-8")
    error = None
    started = time.perf_counter()
    try:
        run_workflow(path, task_prompt="benchmark", session_name=f"bench_{name}")
    except Exception as exc:  # noqa: BLE001 - the benchmark reports how the run ended
        error = f"{type(exc).__name__}: {str(exc)[:120]}"
    wall = time.perf_counter() - started
    calls = list(FakeProvider.calls)
    first_call = min((c[1] for c in calls), default=None)
    ideal = spec["ideal_steps"] * lat
    result = {
        "shape": name,
        "wall_s": round(wall, 3),
        "ideal_s": round(ideal, 3),
        "efficiency": round(ideal / wall, 2) if ideal else None,
        "model_calls": len(calls),
        "peak_parallel_calls": FakeProvider.peak,
        "time_to_first_call_s": round(first_call - started, 3) if first_call else None,
        "error": error,
        "merge_ran": any(c[0] == "Merge" for c in calls),
    }
    if not lat and calls:
        result["engine_ms_per_step"] = round(wall * 1000 / len(calls), 1)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--latency", type=float, default=0.5, help="seconds per fake model call")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument("--only", nargs="*", help="shape names to run")
    args = parser.parse_args()

    install_fake_provider()
    with tempfile.TemporaryDirectory(prefix="agentdev-bench-") as tmp:
        import agentdev.runtime.sdk as sdk

        sdk.OUTPUT_ROOT = Path(tmp) / "out"  # keep benchmark output out of the real warehouse
        results = [run_shape(n, s, args.latency, Path(tmp)) for n, s in shapes().items()
                   if not args.only or n in args.only]
    if args.json:
        print(json.dumps(results, indent=2))
        return
    cols = ["shape", "wall_s", "ideal_s", "efficiency", "model_calls", "peak_parallel_calls",
            "time_to_first_call_s", "engine_ms_per_step", "merge_ran", "error"]
    print(" | ".join(cols))
    for r in results:
        print(" | ".join(str(r.get(c, "")) for c in cols))


if __name__ == "__main__":
    main()
