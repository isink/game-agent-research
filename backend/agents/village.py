"""Village simulation manager — coordinates 8 LLM agents per tick.

Tick loop:
  1. Agents in proximity may speak to each other
  2. Distortion engine applies semantic drift to each transmission
  3. Social pool is updated with dominant narratives
  4. Miracle events are injected by the player (via API)
  5. Reflection is triggered when importance accumulator hits threshold

Research data emitted per tick for Godot visualization and export.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agents.agent import Agent
from agents.personality import BigFive
from memory.social_pool import SocialPool
from propagation.distortion import DistortionEngine

logger = logging.getLogger(__name__)

PROXIMITY_RADIUS = 3  # grid cells — agents within this range can talk


@dataclass
class MiracleEvent:
    miracle_type: str      # "rain", "lightning", "plague", "harvest", "fire", "eclipse"
    description: str       # e.g. "A bolt of lightning strikes the ancient oak tree"
    position: tuple[int, int]
    tick: int
    poignancy: float = 9.0


@dataclass
class TickResult:
    tick: int
    conversations: list[dict]     # sender, receiver, original, distorted, drift
    miracle: Optional[dict]
    agent_states: list[dict]
    social_narratives: list[dict]
    research_metrics: dict
    reflections: list[dict] = None


class Village:
    """Manages the 8-agent village simulation."""

    MIRACLE_DESCRIPTIONS = {
        "rain":      "The sky darkens and a torrential rain falls from a cloudless sky",
        "lightning": "A bolt of lightning strikes the ancient oak tree at the village center",
        "harvest":   "Overnight, all the crops triple in size without explanation",
        "plague":    "A strange illness strikes three villagers simultaneously",
        "fire":      "A fire starts spontaneously in the empty field, burning in a perfect circle",
        "eclipse":   "The sun disappears at midday, plunging the village into sudden darkness",
    }

    def __init__(self):
        self.agents: list[Agent] = []
        self.social_pool = SocialPool()
        self.distortion_engine = DistortionEngine()
        self.tick_count = 0
        self.miracle_queue: list[MiracleEvent] = []
        self._initialized = False

    async def initialize(self, data_path: Path = Path(__file__).parent.parent / "data" / "villagers.json") -> None:
        """Load villager configs and create agents."""
        configs = json.loads(data_path.read_text())
        for cfg in configs:
            p = BigFive.from_dict(cfg["personality"])
            agent = Agent(
                agent_id=cfg["agent_id"],
                name=cfg["name"],
                age=cfg["age"],
                occupation=cfg["occupation"],
                personality=p,
                position=tuple(cfg["position"]),
            )
            self.agents.append(agent)
        self._initialized = True
        logger.info(f"Village initialized with {len(self.agents)} agents")

    # ── Miracle injection (player action) ─────────────────────────────────

    def queue_miracle(self, miracle_type: str, position: Optional[tuple[int, int]] = None) -> MiracleEvent:
        desc = self.MIRACLE_DESCRIPTIONS.get(miracle_type, miracle_type)
        pos = position or (random.randint(1, 9), random.randint(1, 9))
        miracle = MiracleEvent(
            miracle_type=miracle_type,
            description=desc,
            position=pos,
            tick=self.tick_count + 1,
        )
        self.miracle_queue.append(miracle)
        return miracle

    # ── Main tick ──────────────────────────────────────────────────────────

    async def tick(self) -> TickResult:
        """Advance simulation by one time step."""
        self.tick_count += 1
        conversations: list[dict] = []
        miracle_data: Optional[dict] = None

        # 1. Process miracle if queued
        if self.miracle_queue:
            miracle = self.miracle_queue.pop(0)
            miracle_data = await self._process_miracle(miracle)

        # 2. Agent conversations (proximity-based)
        pairs = self._get_nearby_pairs()
        random.shuffle(pairs)

        conv_tasks = [self._conduct_conversation(a, b) for a, b in pairs[:3]]  # max 3 convos/tick
        conv_results = await asyncio.gather(*conv_tasks, return_exceptions=True)
        for r in conv_results:
            if isinstance(r, Exception):
                logger.warning(f"Conversation error: {type(r).__name__}: {r}")
            elif isinstance(r, dict):
                conversations.append(r)

        # 3. Trigger reflections
        reflections: list[dict] = []
        for agent in self.agents:
            if agent.memory.should_reflect():
                insights = await agent.reflect()
                if insights:
                    logger.info(f"{agent.name} reflected: {insights[0][:60]}...")
                    reflections.append({
                        "agent": agent.name,
                        "insights": insights,
                        "beliefs": agent.beliefs,
                        "procedures": [p.content for p in agent.memory.procedures()],
                    })

        # 4. Collect state
        agent_states = [a.to_dict() for a in self.agents]
        narratives = self.social_pool.all_narratives()
        metrics = self._research_metrics()

        return TickResult(
            tick=self.tick_count,
            conversations=conversations,
            miracle=miracle_data,
            agent_states=agent_states,
            social_narratives=narratives,
            research_metrics=metrics,
            reflections=reflections,
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _process_miracle(self, miracle: MiracleEvent) -> dict:
        """Broadcast miracle to all agents; nearby agents perceive it directly."""
        witness_ids: list[str] = []
        for agent in self.agents:
            dist = self._grid_distance(agent.position, miracle.position)
            if dist <= PROXIMITY_RADIUS * 2:
                await agent.perceive(miracle.description, event_type="miracle", poignancy=miracle.poignancy)
                witness_ids.append(agent.agent_id)

        # Record in social pool as ground truth
        self.social_pool.record(
            original_event=miracle.description,
            social_version=miracle.description,
            contributor_id="god",
            tags=["miracle", miracle.miracle_type],
        )
        logger.info(f"Miracle '{miracle.miracle_type}' at {miracle.position}, witnesses: {witness_ids}")
        return {
            "type": miracle.miracle_type,
            "description": miracle.description,
            "position": list(miracle.position),
            "witnesses": witness_ids,
            "tick": miracle.tick,
        }

    async def _conduct_conversation(self, a: Agent, b: Agent) -> Optional[dict]:
        """Two nearby agents exchange — direction is random each call."""
        # Randomly decide who initiates
        sender, receiver = (a, b) if random.random() < 0.5 else (b, a)

        original_msg = await sender.speak(receiver, self.social_pool)
        if not original_msg:
            return None

        # Sender also stores what they said (accumulates toward reflection trigger)
        sender.memory.add(
            f"I told {receiver.name}: '{original_msg[:120]}'",
            memory_type="chat",
            poignancy=3.0,
        )

        # Apply semantic distortion
        record = await self.distortion_engine.transmit(
            message=original_msg,
            sender=sender.personality,
            sender_id=sender.agent_id,
            receiver_id=receiver.agent_id,
            sender_name=sender.name,
            sender_occupation=sender.occupation,
            hop_number=1,
        )

        # Receiver processes the distorted version
        await receiver.receive_speech(sender, original_msg, record.distorted, self.social_pool)

        return {
            "sender": sender.name,
            "receiver": receiver.name,
            "action_type": getattr(sender, "last_action_type", "share_rumor"),
            "original": original_msg,
            "distorted": record.distorted,
            "semantic_drift": round(record.semantic_drift, 4),
            "cumulative_drift": round(record.cumulative_drift, 4),
        }

    def _get_nearby_pairs(self) -> list[tuple[Agent, Agent]]:
        """Return agent pairs within proximity radius."""
        pairs: list[tuple[Agent, Agent]] = []
        for i, a in enumerate(self.agents):
            for b in self.agents[i + 1:]:
                if self._grid_distance(a.position, b.position) <= PROXIMITY_RADIUS:
                    pairs.append((a, b))
        return pairs

    @staticmethod
    def _grid_distance(p1: tuple[int, int], p2: tuple[int, int]) -> float:
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

    def _research_metrics(self) -> dict:
        """Aggregate research metrics for the current tick."""
        all_drifts = [a.memory.avg_semantic_drift() for a in self.agents]
        hop_drift = self.distortion_engine.avg_drift_by_hop()
        narratives = self.social_pool.get_dominant_narrative(tags=["miracle"])

        return {
            "tick": self.tick_count,
            "avg_semantic_drift": round(sum(all_drifts) / len(all_drifts), 4) if all_drifts else 0,
            "drift_by_hop": hop_drift,
            "total_social_narratives": len(self.social_pool.all_narratives()),
            "dominant_miracle_narrative": narratives[0].social_version if narratives else None,
            "agent_belief_counts": {a.name: len(a.beliefs) for a in self.agents},
            "total_distortion_events": len(self.distortion_engine.records),
        }
