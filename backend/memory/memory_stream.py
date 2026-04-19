"""Individual agent memory stream — improved over Smallville.

Key improvements:
- Recency uses real datetime delta, not list-position (fixes Smallville bug)
- importance_weight dynamically scaled by Big Five N (neuroticism)
- Belief-type memories never expire (expiration field actually enforced)
- Distortion tracking: each memory records semantic drift from origin
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

from llm.deepseek import cosine_distance, embed

MemoryType = Literal["event", "chat", "thought", "belief", "procedure"]


@dataclass
class MemoryNode:
    content: str                          # Natural language description
    memory_type: MemoryType
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    poignancy: float = 5.0                # 1-10 importance score
    depth: int = 0                        # 0=event, 1=thought, 2+=belief/insight
    embedding: list[float] = field(default_factory=list)
    node_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Distortion tracking (P1/P2 research data)
    origin_content: Optional[str] = None      # Original event before any distortion
    origin_embedding: Optional[list[float]] = None
    distortion_hops: int = 0                  # How many agent hops since origin
    semantic_drift: float = 0.0               # cosine distance from origin

    # Expiration: beliefs never expire; events decay after 30 sim-days
    expires_days: Optional[float] = 30.0

    @property
    def is_belief(self) -> bool:
        return self.memory_type in ("belief", "procedure") or self.depth >= 2

    @property
    def hermes_tier(self) -> str:
        """Hermes tri-type memory classification."""
        if self.memory_type in ("event", "chat"):
            return "episodic"
        if self.memory_type == "procedure":
            return "procedural"
        return "semantic"  # thought, belief

    def touch(self) -> None:
        self.last_accessed = datetime.now(timezone.utc)

    def age_hours(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.last_accessed).total_seconds() / 3600.0

    def is_expired(self, sim_day: int) -> bool:
        if self.is_belief or self.expires_days is None:
            return False
        created_day = self.created_at.timestamp() / 86400
        return (sim_day - created_day) > self.expires_days


class MemoryStream:
    """Ordered list of MemoryNodes with retrieval scoring."""

    # Retrieval weights (Smallville used [0.5, 3, 2]; we keep but make N-adjustable)
    BASE_WEIGHTS = {"recency": 0.5, "relevance": 3.0, "importance": 2.0}
    RECENCY_DECAY = float(__import__("os").getenv("MEMORY_RECENCY_DECAY", "0.995"))

    def __init__(self, agent_id: str, neuroticism: float = 0.5):
        self.agent_id = agent_id
        self.neuroticism = neuroticism  # Big Five N [0,1]
        self.nodes: list[MemoryNode] = []

        # Reflection trigger: N↑ → lower threshold → more frequent reflection
        base_threshold = int(__import__("os").getenv("MEMORY_IMPORTANCE_THRESHOLD", "150"))
        self.importance_trigger_max = base_threshold * (1.0 - 0.4 * neuroticism)
        self.importance_trigger_curr = self.importance_trigger_max

    # ── Write ──────────────────────────────────────────────────────────────

    def add(
        self,
        content: str,
        memory_type: MemoryType = "event",
        poignancy: Optional[float] = None,
        depth: int = 0,
        origin_content: Optional[str] = None,
        distortion_hops: int = 0,
    ) -> MemoryNode:
        emb = embed(content)
        if poignancy is None:
            poignancy = self._default_poignancy(memory_type)

        # N dimension amplifies perceived poignancy (research variable P1)
        poignancy = min(10.0, poignancy * (1.0 + 0.3 * self.neuroticism))

        origin_emb = embed(origin_content) if origin_content else emb
        drift = cosine_distance(emb, origin_emb) if origin_content else 0.0

        node = MemoryNode(
            content=content,
            memory_type=memory_type,
            poignancy=poignancy,
            depth=depth,
            embedding=emb,
            origin_content=origin_content or content,
            origin_embedding=origin_emb,
            distortion_hops=distortion_hops,
            semantic_drift=drift,
            expires_days=None if memory_type == "belief" else 30.0,
        )
        self.nodes.append(node)

        # Decrement reflection trigger
        if memory_type in ("event", "chat"):
            self.importance_trigger_curr -= poignancy

        return node

    # ── Retrieve ───────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = 10) -> list[MemoryNode]:
        """3-dimension retrieval: recency × relevance × importance."""
        if not self.nodes:
            return []

        query_emb = embed(query)
        now = datetime.now(timezone.utc)

        # Importance weight amplified by N (Big Five research variable)
        w = {
            "recency": self.BASE_WEIGHTS["recency"],
            "relevance": self.BASE_WEIGHTS["relevance"],
            "importance": self.BASE_WEIGHTS["importance"] * (1.0 + 0.5 * self.neuroticism),
        }

        scored: list[tuple[float, MemoryNode]] = []
        for node in self.nodes:
            recency = self._recency_score(node, now)
            relevance = 1.0 - cosine_distance(query_emb, node.embedding)
            importance = node.poignancy / 10.0

            score = (
                w["recency"] * recency
                + w["relevance"] * relevance
                + w["importance"] * importance
            )
            scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [node for _, node in scored[:top_k]]
        for node in results:
            node.touch()
        return results

    def should_reflect(self) -> bool:
        return self.importance_trigger_curr <= 0

    def reset_reflection_trigger(self) -> None:
        self.importance_trigger_curr = self.importance_trigger_max

    # ── Research metrics ───────────────────────────────────────────────────

    def avg_semantic_drift(self) -> float:
        """Mean distortion across all non-zero-hop memories (P1/P2 metric)."""
        drifted = [n.semantic_drift for n in self.nodes if n.distortion_hops > 0]
        return sum(drifted) / len(drifted) if drifted else 0.0

    def belief_summary(self) -> list[str]:
        """All current belief-type memory contents."""
        return [n.content for n in self.nodes if n.is_belief]

    def procedures(self) -> list[MemoryNode]:
        """All procedural memories (learned rituals/skills)."""
        return [n for n in self.nodes if n.memory_type == "procedure"]

    # ── Internal ───────────────────────────────────────────────────────────

    def _recency_score(self, node: MemoryNode, now: datetime) -> float:
        """Real time-based exponential decay (fixes Smallville list-position bug)."""
        hours_elapsed = node.age_hours(now)
        return math.pow(self.RECENCY_DECAY, hours_elapsed)

    @staticmethod
    def _default_poignancy(memory_type: MemoryType) -> float:
        defaults = {"event": 4.0, "chat": 3.0, "thought": 5.0, "belief": 7.0, "procedure": 8.0}
        return defaults.get(memory_type, 4.0)
