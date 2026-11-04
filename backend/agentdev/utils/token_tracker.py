"""Token usage tracking module for AgentDev project."""
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any
from collections import defaultdict

from agentdev.utils.exceptions import WorkflowExecutionError

_log = logging.getLogger(__name__)


class BudgetExceededError(WorkflowExecutionError):
    """A run limit (tokens, cost, seconds, node runs) was exceeded."""


def _num(value, cast=float):
    try:
        return cast(value or 0)
    except (TypeError, ValueError):
        return cast(0)


def resolve_run_limits(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge graph ``run_limits`` with AGENTDEV_MAX_RUN_* env caps (the stricter wins)."""
    config = config or {}
    limits: Dict[str, Any] = {}
    for key, cast in (("max_tokens", int), ("max_cost_usd", float), ("max_seconds", float), ("max_node_runs", int)):
        value = _num(config.get(key), cast)
        if value > 0:
            limits[key] = value
    for key, env, cast in (
        ("max_seconds", "AGENTDEV_MAX_RUN_SECONDS", float),
        ("max_tokens", "AGENTDEV_MAX_RUN_TOKENS", int),
    ):
        cap = _num(os.environ.get(env), cast)
        if cap > 0:
            limits[key] = min(limits[key], cap) if key in limits else cap
    per_node = config.get("node_max_runs")
    if isinstance(per_node, dict):
        parsed = {str(k): _num(v, int) for k, v in per_node.items() if _num(v, int) > 0}
        if parsed:
            limits["node_max_runs"] = parsed
    return limits


@dataclass
class TokenUsage:
    """Stores token usage metrics for individual API calls."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    node_id: Optional[str] = None
    model_name: Optional[str] = None
    workflow_id: Optional[str] = None
    provider: Optional[str] = None  # Add provider field

    def to_dict(self):
        """Convert to dictionary format."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
            "node_id": self.node_id,
            "model_name": self.model_name,
            "workflow_id": self.workflow_id,
            "provider": self.provider  # Include provider in output
        }


class TokenTracker:
    """Singleton class to track token usage across a workflow."""
    
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.total_usage = TokenUsage()
        self.node_usages = defaultdict(TokenUsage)
        self.model_usages = defaultdict(TokenUsage)
        self.call_history = []
        self.node_call_counts = defaultdict(int)  # Track how many times each node is called
        # Parallel team members record usage from several threads at once.
        self._lock = threading.RLock()
        self._t0 = time.perf_counter()
        self._last_end = self._t0
        self.node_runs = []  # every run of every node, loops included
        self._node_extra = defaultdict(lambda: {"cache_read": 0, "cache_creation": 0, "cost_usd": 0.0, "wall_ms": 0.0})
        self._model_extra = defaultdict(lambda: {"cache_read": 0, "cache_creation": 0, "cost_usd": 0.0})
        self.limits: Dict[str, Any] = resolve_run_limits(None)
        self._cancel_cb = None
        self._warned = set()
        self._exceeded: Optional[BudgetExceededError] = None

    # ---- budgets -------------------------------------------------
    def configure_limits(self, run_limits: Optional[Dict[str, Any]], cancel_cb=None) -> None:
        with self._lock:
            self.limits = resolve_run_limits(run_limits)
            self._cancel_cb = cancel_cb

    def _fail(self, label_vi: str, label_en: str, used, limit) -> BudgetExceededError:
        top = self._top_nodes(1)
        top = top[0]["node"] if top else None
        suffix_vi = f" Node tốn nhiều nhất: {top}." if top else ""
        suffix_en = f" Top node: {top}." if top else ""
        err = BudgetExceededError(
            f"Vượt giới hạn {label_vi}: {used} / {limit}.{suffix_vi} "
            f"(Run budget exceeded: {label_en} {used} / {limit}.{suffix_en})",
            workflow_id=self.workflow_id,
            node_id=top,
            details={"limit": label_en, "used": used, "max": limit},
        )
        self._exceeded = err
        if self._cancel_cb:
            try:
                self._cancel_cb(str(err))
            except Exception:  # pragma: no cover
                pass
        return err

    def check_budget(self, node_id: Optional[str] = None, *, starting: bool = False) -> None:
        """Warn at 80% and raise BudgetExceededError past a limit. No-op without limits."""
        with self._lock:
            if self._exceeded is not None:
                raise self._exceeded
            lim = self.limits
            if not lim:
                return
            checks = [
                ("max_tokens", "token", "tokens", self.total_usage.total_tokens),
                ("max_cost_usd", "chi phí (USD)", "cost USD", round(sum(e["cost_usd"] for e in self._model_extra.values()), 4)),
                ("max_seconds", "thời gian (giây)", "seconds", round(time.perf_counter() - self._t0, 1)),
                ("max_node_runs", "số lần chạy node", "node runs", len(self.node_runs)),
            ]
            for key, vi, en, used in checks:
                cap = lim.get(key)
                if not cap:
                    continue
                if used > cap:
                    raise self._fail(vi, en, used, cap)
                if used >= 0.8 * cap and key not in self._warned:
                    self._warned.add(key)
                    _log.warning("Run budget at 80%%: %s %s / %s", en, used, cap)
            if starting and node_id:
                cap = (lim.get("node_max_runs") or {}).get(node_id)
                runs = sum(1 for r in self.node_runs if r["node"] == node_id)
                if cap and runs >= cap:
                    raise self._fail(f"số lần chạy của node {node_id}", f"runs of node {node_id}", runs, cap)

    # ---- node wall time ------------------------------------------
    def record_node_run(self, node_id: str, wall_ms: float, status: str = "ok", start_ts: Optional[str] = None) -> None:
        with self._lock:
            n = sum(1 for r in self.node_runs if r["node"] == node_id) + 1
            self._last_end = time.perf_counter()
            self.node_runs.append({
                "node": node_id,
                "n": n,
                "wall_ms": round(float(wall_ms), 1),
                "status": status,
                "start_ts": start_ts or datetime.now().isoformat(),
            })
            self._node_extra[node_id]["wall_ms"] += float(wall_ms)
        if status == "ok":
            self.check_budget(node_id)

    def record_usage(self, node_id: str, model_name: str, usage: TokenUsage, provider: str = None):
        """Records token usage for a specific call, handling multiple node executions."""
        with self._lock:
            self._record_usage(node_id, model_name, usage, provider)
        self.check_budget(node_id)

    def _record_usage(self, node_id: str, model_name: str, usage: TokenUsage, provider: str = None):
        # Update the usage with provider if it wasn't set already
        if provider and not usage.provider:
            usage.provider = provider
            
        # Add to total usage
        self.total_usage.input_tokens += usage.input_tokens
        self.total_usage.output_tokens += usage.output_tokens
        self.total_usage.total_tokens += usage.total_tokens
        
        # Add to node-specific usage
        node_usage = self.node_usages[node_id]
        node_usage.input_tokens += usage.input_tokens
        node_usage.output_tokens += usage.output_tokens
        node_usage.total_tokens += usage.total_tokens
        if provider:
            node_usage.provider = provider  # Store provider info
        
        # Add to model-specific usage
        model_usage = self.model_usages[model_name]
        model_usage.input_tokens += usage.input_tokens
        model_usage.output_tokens += usage.output_tokens
        model_usage.total_tokens += usage.total_tokens
        if provider:
            model_usage.provider = provider  # Store provider info
        
        # Increment call count for this node
        self.node_call_counts[node_id] += 1
        
        # Add to call history
        history_entry = {
            "node_id": node_id,
            "model_name": model_name,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "metadata": dict(usage.metadata),
            "timestamp": usage.timestamp.isoformat(),
            "execution_number": self.node_call_counts[node_id]  # Track which execution this is
        }
        
        # Add provider to history entry if available
        if provider:
            history_entry["provider"] = provider
            
        meta = usage.metadata or {}
        if "duration_ms" in meta:
            history_entry["duration_ms"] = meta["duration_ms"]
        cache_r = _num(meta.get("cache_read_input_tokens"), int)
        cache_w = _num(meta.get("cache_creation_input_tokens"), int)
        cost = _num(meta.get("total_cost_usd"), float)
        for bucket in (self._node_extra[node_id], self._model_extra[model_name]):
            bucket["cache_read"] += cache_r
            bucket["cache_creation"] += cache_w
            bucket["cost_usd"] += cost

        self.call_history.append(history_entry)

    def get_total_usage(self) -> TokenUsage:
        """Get total token usage for the workflow."""
        return self.total_usage

    def get_node_usage(self, node_id: str) -> TokenUsage:
        """Get token usage for a specific node (across all its executions)."""
        return self.node_usages[node_id]

    def get_model_usage(self, model_name: str) -> TokenUsage:
        """Get token usage for a specific model."""
        return self.model_usages[model_name]

    def get_node_execution_count(self, node_id: str) -> int:
        """Get how many times a node was executed."""
        return self.node_call_counts[node_id]

    def get_token_usage(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot()

    def _top_nodes(self, limit: int = 8):
        rows = {}
        for run in self.node_runs:
            row = rows.setdefault(run["node"], {"runs": 0, "wall_s": 0.0})
            row["runs"] += 1
            row["wall_s"] += run["wall_ms"] / 1000.0
        for node_id in self.node_usages:
            rows.setdefault(node_id, {"runs": 0, "wall_s": 0.0})
        out = []
        for node_id, row in rows.items():
            usage = self.node_usages.get(node_id)
            extra = self._node_extra.get(node_id)
            out.append({
                "node": node_id,
                "runs": row["runs"],
                "wall_s": round(row["wall_s"], 2),
                "tokens": usage.total_tokens if usage else 0,
                "cost_usd": round(extra["cost_usd"], 4) if extra else 0.0,
            })
        out.sort(key=lambda r: (r["wall_s"], r["tokens"]), reverse=True)
        return out[:limit]

    def _summary(self) -> Dict[str, Any]:
        cache_r = sum(e["cache_read"] for e in self._node_extra.values())
        cache_w = sum(e["cache_creation"] for e in self._node_extra.values())
        denom = cache_r + cache_w + self.total_usage.input_tokens
        return {
            "wall_s": round(max(self._last_end - self._t0, 0.0), 2) if self.node_runs else 0.0,
            "tokens": self.total_usage.total_tokens,
            "cache_hit_pct": round(100.0 * cache_r / denom, 1) if (cache_r + cache_w) > 0 and denom else None,
            "cost_usd": round(sum(e["cost_usd"] for e in self._model_extra.values()), 4),
            "top_nodes": self._top_nodes(8),
        }

    def _snapshot(self) -> Dict[str, Any]:
        data = {
            "workflow_id": self.workflow_id,
            "total_usage": {
                "input_tokens": self.total_usage.input_tokens,
                "output_tokens": self.total_usage.output_tokens,
                "total_tokens": self.total_usage.total_tokens,
            },
            "node_usages": {
                node_id: {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
                for node_id, usage in self.node_usages.items()
            },
            "model_usages": {
                model_name: {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
                for model_name, usage in self.model_usages.items()
            },
            "node_execution_counts": dict(self.node_call_counts),
            "call_history": list(self.call_history),
            "node_runs": [dict(r) for r in self.node_runs],
            "node_rollups": {
                node_id: {
                    "cache_read_tokens": e["cache_read"],
                    "cache_creation_tokens": e["cache_creation"],
                    "cost_usd": round(e["cost_usd"], 4),
                    "wall_s": round(e["wall_ms"] / 1000.0, 2),
                }
                for node_id, e in self._node_extra.items()
            },
            "model_rollups": {
                m: {
                    "cache_read_tokens": e["cache_read"],
                    "cache_creation_tokens": e["cache_creation"],
                    "cost_usd": round(e["cost_usd"], 4),
                }
                for m, e in self._model_extra.items()
            },
            "run_limits": dict(self.limits),
            "summary": self._summary(),
        }
        return data

    def export_to_file(self, filepath: str):
        """Export token usage data to a JSON file."""
        import json
        from pathlib import Path
        
        # Create directory if it doesn't exist
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = self.get_token_usage()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
