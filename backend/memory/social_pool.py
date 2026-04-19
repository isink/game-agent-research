"""Social memory pool — shared collective memory across all agents.

Stores the *social interpretation* of major events (not individual memories).
This is the substrate from which collective myths emerge (P3 research).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SocialMemory:
    event_id: str
    original_event: str                    # What actually happened (ground truth)
    social_version: str                    # Collective retelling
    contributors: list[str] = field(default_factory=list)  # agent IDs
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reinforcement_count: int = 1           # How many agents have this version
    tags: list[str] = field(default_factory=list)  # e.g. ["miracle", "punishment"]


class SocialPool:
    """Collective memory shared by the village.

    Key invariant: the pool records what the *village believes happened*,
    which may diverge significantly from what actually happened.
    """

    def __init__(self):
        self._memories: dict[str, SocialMemory] = {}

    def record(
        self,
        original_event: str,
        social_version: str,
        contributor_id: str,
        tags: Optional[list[str]] = None,
    ) -> SocialMemory:
        """Add a new social interpretation of an event."""
        event_id = str(uuid.uuid4())[:8]
        mem = SocialMemory(
            event_id=event_id,
            original_event=original_event,
            social_version=social_version,
            contributors=[contributor_id],
            tags=tags or [],
        )
        self._memories[event_id] = mem
        return mem

    def reinforce(self, event_id: str, agent_id: str, new_version: Optional[str] = None) -> None:
        """An agent corroborates an existing social memory (possibly with drift)."""
        mem = self._memories.get(event_id)
        if not mem:
            return
        if agent_id not in mem.contributors:
            mem.contributors.append(agent_id)
        mem.reinforcement_count += 1
        if new_version:
            mem.social_version = new_version  # latest retelling wins

    def get_dominant_narrative(self, tags: Optional[list[str]] = None) -> list[SocialMemory]:
        """Return most-reinforced memories, optionally filtered by tag."""
        mems = list(self._memories.values())
        if tags:
            mems = [m for m in mems if any(t in m.tags for t in tags)]
        return sorted(mems, key=lambda m: m.reinforcement_count, reverse=True)

    def all_narratives(self) -> list[dict]:
        return [
            {
                "event_id": m.event_id,
                "original": m.original_event,
                "social": m.social_version,
                "reinforcement": m.reinforcement_count,
                "contributors": m.contributors,
                "tags": m.tags,
            }
            for m in self._memories.values()
        ]

    def export(self, path: Path) -> None:
        path.write_text(json.dumps(self.all_narratives(), indent=2, ensure_ascii=False))
