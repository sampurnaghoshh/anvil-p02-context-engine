from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from engine.memory import EventMemory


class TopologyGraph:
    """
    Shared directed graph of service dependencies.
    Owned by Engine; passed by reference into normalizer and causal modules.
    """

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()
        self._span_service: dict[str, str] = {}  # span_id -> canonical service
        self._role_cache: dict[tuple[str, str], str] = {}

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_event(self, event: dict, memory: "EventMemory") -> None:
        """Handle add_edge/remove_edge topology events and trace-derived edges."""
        kind = event.get("kind")

        if kind == "topology":
            change = event.get("change")
            if change not in ("add_edge", "remove_edge"):
                return  # rename handled via apply_rename(); ignore others
            src = memory.resolve(
                event.get("edge_source") or event.get("source") or ""
            )
            dst = memory.resolve(
                event.get("edge_target") or event.get("target") or ""
            )
            if not src or not dst:
                return
            if change == "add_edge":
                if self._g.has_edge(src, dst):
                    self._g[src][dst]["weight"] += 1
                else:
                    self._g.add_edge(src, dst, weight=1, source="explicit")
            else:
                if self._g.has_edge(src, dst):
                    self._g.remove_edge(src, dst)

        elif kind == "trace":
            svc = memory.resolve(event.get("service") or "")
            span_id = event.get("span_id")
            parent_span_id = event.get("parent_span_id")

            if span_id and svc:
                self._span_service[span_id] = svc

            if parent_span_id and svc:
                parent_svc = self._span_service.get(parent_span_id)
                if parent_svc and parent_svc != svc:
                    # caller -> callee direction (parent span is the caller)
                    if self._g.has_edge(parent_svc, svc):
                        self._g[parent_svc][svc]["weight"] += 1
                    else:
                        self._g.add_edge(parent_svc, svc, weight=1, source="trace")

    def apply_rename(self, old_name: str, new_name: str) -> None:
        """Relabel the graph node in-place; all edges are preserved by NetworkX."""
        if old_name in self._g and old_name != new_name:
            nx.relabel_nodes(self._g, {old_name: new_name}, copy=False)
        for span_id, svc in self._span_service.items():
            if svc == old_name:
                self._span_service[span_id] = new_name
        self._role_cache.clear()

    # ── Role assignment ───────────────────────────────────────────────────────

    def role_of(self, candidate: str, anchor: str, max_depth: int = 2) -> str:
        """
        BFS-based structural role assignment, cached per reconstruct_context call.
        Returns one of: target | upstream | downstream | peripheral | unknown
        """
        cache_key = (candidate, anchor)
        if cache_key in self._role_cache:
            return self._role_cache[cache_key]

        if not candidate or not anchor:
            role = "unknown"
        elif candidate == anchor:
            role = "target"
        elif self._bfs_directed(candidate, anchor, max_depth):
            role = "upstream"
        elif self._bfs_directed(anchor, candidate, max_depth):
            role = "downstream"
        elif self._bfs_undirected(candidate, anchor, max_depth):
            role = "peripheral"
        else:
            role = "unknown"

        self._role_cache[cache_key] = role
        return role

    def clear_role_cache(self) -> None:
        self._role_cache.clear()

    # ── Graph queries ─────────────────────────────────────────────────────────

    def descendants(self, canonical: str, max_hops: int = 2) -> set[str]:
        """Forward-reachable services within max_hops (excludes the start node)."""
        if canonical not in self._g:
            return set()
        visited: set[str] = set()
        frontier = {canonical}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for node in frontier:
                for succ in self._g.successors(node):
                    if succ not in visited and succ != canonical:
                        visited.add(succ)
                        next_frontier.add(succ)
            frontier = next_frontier
        return visited

    def ancestors(self, canonical: str, max_hops: int = 2) -> set[str]:
        """Backward-reachable services within max_hops (services that flow INTO canonical)."""
        if canonical not in self._g:
            return set()
        visited: set[str] = set()
        frontier = {canonical}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for node in frontier:
                for pred in self._g.predecessors(node):
                    if pred not in visited and pred != canonical:
                        visited.add(pred)
                        next_frontier.add(pred)
            frontier = next_frontier
        return visited

    def to_networkx(self) -> nx.DiGraph:
        """Return the underlying graph (read-only; do not mutate)."""
        return self._g

    # ── Private BFS ───────────────────────────────────────────────────────────

    def _bfs_directed(self, source: str, target: str, max_hops: int) -> bool:
        if source not in self._g or target not in self._g:
            return False
        visited = {source}
        frontier = {source}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for node in frontier:
                for neighbor in self._g.successors(node):
                    if neighbor == target:
                        return True
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return False

    def _bfs_undirected(self, source: str, target: str, max_hops: int) -> bool:
        if source not in self._g or target not in self._g:
            return False
        visited = {source}
        frontier = {source}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for node in frontier:
                neighbors = (
                    set(self._g.successors(node))
                    | set(self._g.predecessors(node))
                )
                for neighbor in neighbors:
                    if neighbor == target:
                        return True
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return False
