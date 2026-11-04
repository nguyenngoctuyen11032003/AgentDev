"""Graph analysis shared by the Lab static check (``workflow_lab``) and the proposal lint.

Single source of truth for model tiers, cycles (strongly connected components), keyword edge
conditions (same semantics as ``KeywordEdgeConditionManager._evaluate``) and the critical-path speed
estimate. Kept free of heavy imports so both callers can use it without import cycles.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

TIER_SECONDS = {"small": 15, "mid": 40, "top": 90}
LOOP_PASS_SECONDS = 30  # one extra pass through a loop body
TEAM_DEFAULT_PARALLEL = 3  # entity/configs/node/team.py DEFAULT_MAX_PARALLEL
CRITICAL_PATH_SECONDS = 180
CRITICAL_PATH_AGENTS = 6

_SMALL_MARKERS = ("haiku", "flash", "mini", "luna", "nano", "lite")
_TOP_MARKERS = ("opus", "fable", "sol", "pro")


def _has_word(text: str, word: str) -> bool:
    # whole-word match so "gemini" is not "mini" and "console" is not "sol"
    return re.search(rf"(?<![a-z]){word}(?![a-z])", text) is not None


def model_tier(model: Any) -> str:
    """``small`` / ``mid`` / ``top`` from a model name (unknown names count as mid)."""
    name = str(model or "").lower()
    if any(_has_word(name, m) for m in _SMALL_MARKERS):
        return "small"
    if any(_has_word(name, m) for m in _TOP_MARKERS):
        return "top"
    return "mid"


def sccs(ids: Iterable[Any], adj: Dict[Any, List[Any]]) -> List[List[Any]]:
    """Tarjan's strongly connected components (iterative), in reverse topological order."""
    index: Dict[Any, int] = {}
    low: Dict[Any, int] = {}
    on_stack: set = set()
    stack: List[Any] = []
    out: List[List[Any]] = []
    counter = 0
    for root in ids:
        if root in index:
            continue
        work = [(root, iter(adj.get(root, [])))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(adj.get(nxt, []))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                out.append(comp)
    return out


def edge_condition_matches(condition: Any, text: str) -> bool:
    """Same semantics as ``KeywordEdgeConditionManager._evaluate``: ``none`` wins, then ``any``, then
    ``regex``; a condition with only ``none`` terms matches when none is present. Non-keyword conditions
    (functions) cannot be judged statically and are assumed to match."""
    if not isinstance(condition, dict) or condition.get("type") != "keyword":
        return True
    cfg = condition.get("config") or {}
    any_kw = [str(k) for k in cfg.get("any") or []]
    none_kw = [str(k) for k in cfg.get("none") or []]
    patterns = [str(k) for k in cfg.get("regex") or []]
    case_sensitive = bool(cfg.get("case_sensitive", True))
    hay = text if case_sensitive else text.lower()
    norm = (lambda w: w) if case_sensitive else (lambda w: w.lower())
    if any(kw and norm(kw) in hay for kw in none_kw):
        return False
    if any(kw and norm(kw) in hay for kw in any_kw):
        return True
    flags = 0 if case_sensitive else re.IGNORECASE
    for pattern in patterns:
        try:
            if re.search(pattern, text, flags):
                return True
        except re.error:
            continue
    return not (any_kw or patterns)


# ---------------------------------------------------------------------------- whole graph


class Graph:
    """Nodes by id, adjacency (edges between known nodes only), components and cycles."""

    def __init__(self, graph: Any) -> None:
        graph = graph if isinstance(graph, dict) else {}
        self.raw = graph
        self.nodes: Dict[Any, dict] = {n.get("id"): n for n in graph.get("nodes") or []
                                       if isinstance(n, dict) and n.get("id") is not None}
        self.edges: List[dict] = [e for e in graph.get("edges") or [] if isinstance(e, dict)]
        self.adj: Dict[Any, List[Any]] = {nid: [] for nid in self.nodes}
        self.radj: Dict[Any, List[Any]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            a, b = e.get("from"), e.get("to")
            if a in self.adj and b in self.adj:
                self.adj[a].append(b)
                self.radj[b].append(a)
        self.comps = sccs(list(self.nodes), self.adj)
        self.comp_of = {n: i for i, c in enumerate(self.comps) for n in c}
        self.cyclic = {i for i, c in enumerate(self.comps) if len(c) > 1 or c[0] in self.adj.get(c[0], [])}
        self._dead_counters: Optional[List[Any]] = None

    @classmethod
    def from_workflow(cls, data: Any) -> "Graph":
        return cls((data or {}).get("graph") if isinstance(data, dict) else None)

    def guarded(self, comp: int) -> bool:
        """The loop has a loop_counter the engine actually reaches (one on an inner loop never counts)."""
        dead = set(self.counters_in_inner_loop())
        return any(self.nodes[n].get("type") == "loop_counter" and n not in dead for n in self.comps[comp])

    def unguarded_cycles(self) -> List[List[Any]]:
        return [self.comps[i] for i in sorted(self.cyclic) if not self.guarded(i)]

    def counters_in_inner_loop(self) -> List[Any]:
        """loop_counter nodes the engine will never reach in their loop.

        The engine runs a loop from the one entry that fired (the node a step outside the loop, or the task for a
        start node, started) and treats any cycle left once that entry's incoming edges are dropped as an inner
        loop. An inner loop ends as soon as one of its nodes starts a node outside it, so a counter sitting on one
        (for example a counter wired back to the approval step that feeds it) is skipped and never stops the loop.
        Each entry is checked on its own, as the engine does; the result is computed once per graph.
        """
        if self._dead_counters is not None:
            return list(self._dead_counters)
        bad: List[Any] = []
        starts = set(self.raw.get("start") or [])
        for i in sorted(self.cyclic):
            loop = set(self.comps[i])
            counters = {n for n in loop if self.nodes[n].get("type") == "loop_counter"}
            if not counters:
                continue
            entries = {e.get("to") for e in self.edges
                       if e.get("to") in loop and e.get("from") not in loop and e.get("trigger", True) is not False}
            entries |= loop & starts
            dead: set = set()
            for entry in sorted(entries, key=str):
                adj: Dict[Any, List[Any]] = {n: [] for n in loop}
                for e in self.edges:
                    a, b = e.get("from"), e.get("to")
                    if a in loop and b in loop and b != entry and e.get("trigger", True) is not False:
                        adj[a].append(b)
                for comp in sccs(list(loop), adj):
                    if len(comp) > 1 or comp[0] in adj[comp[0]]:
                        dead.update(n for n in comp if n in counters)
            bad.extend(sorted(dead, key=str))
        self._dead_counters = bad
        return list(bad)

    def has_counter(self, comp: int) -> bool:
        return any(self.nodes[n].get("type") == "loop_counter" for n in self.comps[comp])

    def humans_approving_silence(self, silence: str, approval: str = "OK",
                                 refusal: str = "Không, sửa lại phần mở đầu") -> List[Any]:
        """Human gates where a timeout (nobody answered) takes the approve branch.

        The approve branch is the edge that takes ``approval`` but not a plain ``refusal``; a skip/revise branch
        takes refusals too, and silence going there is the safe outcome. Silence must never approve: no email is
        sent, nothing is published and no money is spent without a person.
        """
        bad: List[Any] = []
        for nid, node in self.nodes.items():
            if node.get("type") != "human":
                continue
            out = [e for e in self.edges if e.get("from") == nid and e.get("to") in self.adj]
            approve = [e for e in out if edge_condition_matches(e.get("condition"), approval)
                       and not edge_condition_matches(e.get("condition"), refusal)]
            if not approve or len(approve) == len(out):
                continue  # no decision at this gate
            if any(edge_condition_matches(e.get("condition"), silence) for e in approve):
                bad.append(nid)
        return bad

    def humans_blocking_auto_answer(self, answer: str) -> List[Any]:
        """Human nodes where the automatic answer cannot move the run on: no matching outgoing edge
        leaves the node's loop, unless that loop has a loop_counter that will end it."""
        bad: List[Any] = []
        for nid, node in self.nodes.items():
            if node.get("type") != "human":
                continue
            out = [e for e in self.edges if e.get("from") == nid and e.get("to") in self.adj]
            if not out:
                continue
            ok = False
            for e in out:
                if not edge_condition_matches(e.get("condition"), answer):
                    continue
                comp = self.comp_of[e["to"]]
                if comp != self.comp_of[nid] or self.guarded(comp):
                    ok = True
                    break
            if not ok:
                bad.append(nid)
        return bad

    def _agent_cost(self, node: dict, seen: frozenset = frozenset()) -> Tuple[int, int, int]:
        """(seconds, agents, heavy agents) of one agent; a team lead adds its members. The lead runs up
        to ``team.max_parallel`` members at once, so member time is spread over that many lanes (never
        less than the slowest member)."""
        if node.get("type") != "agent":
            return 0, 0, 0
        cfg = node.get("config") if isinstance(node.get("config"), dict) else {}
        tier = model_tier(cfg.get("name"))
        sec, cnt, hv = TIER_SECONDS[tier], 1, int(tier != "small")
        team = cfg.get("team") if isinstance(cfg.get("team"), dict) else {}
        if team.get("enabled"):
            member_secs = []
            for member in team.get("members") or []:
                if member in self.nodes and member not in seen and member != node.get("id"):
                    s, c, h = self._agent_cost(self.nodes[member], seen | {node.get("id")})
                    member_secs.append(s)
                    cnt, hv = cnt + c, hv + h
            if member_secs:
                try:
                    lanes = max(1, int(team.get("max_parallel") or TEAM_DEFAULT_PARALLEL))
                except (TypeError, ValueError):
                    lanes = TEAM_DEFAULT_PARALLEL
                sec += max(max(member_secs), -(-sum(member_secs) // lanes))
        return sec, cnt, hv

    def critical_path(self) -> Dict[str, Any]:
        """Longest chain over the condensed graph from the start nodes. A loop body counts once plus
        LOOP_PASS_SECONDS for one extra pass."""
        weight: Dict[int, Tuple[int, int, int]] = {}
        for i, c in enumerate(self.comps):
            sec = cnt = hv = 0
            for n in c:
                s, k, h = self._agent_cost(self.nodes[n])
                sec, cnt, hv = sec + s, cnt + k, hv + h
            if cnt and i in self.cyclic:
                sec += LOOP_PASS_SECONDS
            weight[i] = (sec, cnt, hv)
        cadj: Dict[int, set] = {i: set() for i in range(len(self.comps))}
        for a, bs in self.adj.items():
            for b in bs:
                if self.comp_of[a] != self.comp_of[b]:
                    cadj[self.comp_of[a]].add(self.comp_of[b])
        memo: Dict[int, Tuple[int, int, int]] = {}

        def best(i: int) -> Tuple[int, int, int]:
            if i not in memo:
                tail = max((best(j) for j in cadj[i]), default=(0, 0, 0))
                memo[i] = tuple(w + t for w, t in zip(weight[i], tail))  # type: ignore[assignment]
            return memo[i]

        # comps come out in reverse topological order: resolve sinks first to keep recursion shallow
        for i in range(len(self.comps)):
            best(i)
        start = [n for n in self.raw.get("start") or [] if n in self.comp_of]
        roots = [self.comp_of[n] for n in start] or list(range(len(self.comps)))
        seconds, agents, heavy = max((best(r) for r in roots), default=(0, 0, 0))
        slow = seconds > CRITICAL_PATH_SECONDS or heavy > CRITICAL_PATH_AGENTS
        return {"estimated_seconds": seconds, "agents": agents, "heavy_agents": heavy, "slow": slow}
