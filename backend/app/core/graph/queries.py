"""Dependency graph queries (Phase 1).

Small helpers over the precedent -> dependent ``DiGraph`` from
``graph.builder``. Later phases (Q&A tracing) build on ``ancestors`` with its
default depth of 6.
"""

from __future__ import annotations

from collections import deque

import networkx as nx


def _require(graph: nx.DiGraph, ref: str) -> None:
    if ref not in graph:
        raise KeyError(f"Cell not in graph: {ref!r}")


def precedents(graph: nx.DiGraph, ref: str) -> list[str]:
    """Direct precedents of ``ref`` (cells it depends on), sorted."""
    _require(graph, ref)
    return sorted(graph.predecessors(ref))


def dependents(graph: nx.DiGraph, ref: str) -> list[str]:
    """Direct dependents of ``ref`` (cells depending on it), sorted."""
    _require(graph, ref)
    return sorted(graph.successors(ref))


def _walk(
    graph: nx.DiGraph, ref: str, depth: int, forward: bool
) -> list[str]:
    _require(graph, ref)
    if depth < 1:
        return []
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(ref, 0)])
    while queue:
        node, dist = queue.popleft()
        if dist == depth:
            continue
        neighbors = graph.successors(node) if forward else graph.predecessors(node)
        for nxt in neighbors:
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))
    seen.discard(ref)  # a cycle leading back to the start is not its own ancestor
    return sorted(seen)


def ancestors(graph: nx.DiGraph, ref: str, depth: int = 6) -> list[str]:
    """All precedent cells upstream of ``ref`` up to ``depth`` hops."""
    return _walk(graph, ref, depth, forward=False)


def descendants(graph: nx.DiGraph, ref: str, depth: int = 6) -> list[str]:
    """All dependent cells downstream of ``ref`` up to ``depth`` hops."""
    return _walk(graph, ref, depth, forward=True)


def trace_chain(graph: nx.DiGraph, ref: str, depth: int = 6) -> dict[str, list[str]]:
    """Return ``{"target", "ancestors", "formulas"}`` for Q&A-style tracing.

    ``formulas`` maps each traced cell to its formula (or None for inputs).
    """
    chain = ancestors(graph, ref, depth)
    return {
        "target": [ref],
        "ancestors": chain,
        "formulas": [graph.nodes[n].get("formula") for n in [ref, *chain]],
    }
