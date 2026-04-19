"""Five-layer Agent architecture + Hermes extensions.

Layers (improvements over Smallville's 3-layer):
  L1 Perception  — sense events, weight by importance
  L2 Memory      — store/retrieve with distortion tracking
               Hermes: tri-type (episodic / semantic / procedural)
  L3 Reasoning   — plan actions from memory
               Hermes: inner monologue (CoT before speaking)
  L4 Belief      — maintain worldview and faith (NEW — Smallville had none)
  L5 Action      — output: speech, movement, info propagation
               Hermes: structured action types (share_rumor / warn /
                       perform_ritual / gather_resource)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from llm.deepseek import chat
from memory.memory_stream import MemoryStream
from agents.personality import BigFive

if TYPE_CHECKING:
    from memory.social_pool import SocialPool


@dataclass
class AgentState:
    """Snapshot of agent state for API/WebSocket serialization."""
    agent_id: str
    name: str
    occupation: str
    position: tuple[int, int]
    current_action: str
    last_speech: str
    belief_summary: list[str]
    personality: dict
    avg_semantic_drift: float
    memory_count: int


class Agent:
    """LLM-driven agent with 5-layer cognitive architecture."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        age: int,
        occupation: str,
        personality: BigFive,
        position: tuple[int, int] = (0, 0),
    ):
        self.agent_id = agent_id
        self.name = name
        self.age = age
        self.occupation = occupation
        self.personality = personality
        self.position = position

        self.memory = MemoryStream(agent_id, neuroticism=personality.neuroticism)
        self.current_action: str = "idle"
        self.last_speech: str = ""
        self.last_action_type: str = "idle"  # Hermes: most recent structured action

        # L4 Belief state: key-value worldview entries
        # Not seeded — emerges from experience (P3)
        self.beliefs: dict[str, str] = {}

        # Seed the agent's character (personality only, no beliefs)
        seed = personality.to_seed_memory(name, age, occupation)
        self.memory.add(seed, memory_type="thought", poignancy=3.0, depth=0)

    # ── L1 Perception ──────────────────────────────────────────────────────

    async def perceive(self, event: str, event_type: str = "event", poignancy: Optional[float] = None) -> None:
        """Receive an external event and store it in memory."""
        # N dimension amplifies sensitivity to miracles/strange events
        if poignancy is None:
            poignancy = 5.0 + 4.0 * self.personality.miracle_sensitivity if event_type == "miracle" else 4.0

        self.memory.add(event, memory_type="event", poignancy=poignancy)  # type: ignore

    # ── L2 + L3 Reasoning ──────────────────────────────────────────────────

    async def think(self, context: str) -> str:
        """Generate a thought by reasoning over relevant memories."""
        relevant = self.memory.retrieve(context, top_k=8)
        mem_text = "\n".join(f"- {n.content}" for n in relevant)

        seed = self.personality.to_seed_memory(self.name, self.age, self.occupation)
        prompt = (
            f"You are {self.name}.\n"
            f"Character: {seed}\n\n"
            f"Your recent memories and beliefs:\n{mem_text}\n\n"
            f"Situation: {context}\n\n"
            f"What do you think about this? Respond in 1-2 sentences, in first person, "
            f"in the voice of your character."
        )
        thought = await chat(prompt, temperature=0.85)
        self.memory.add(thought, memory_type="thought", depth=1)
        return thought

    # ── L3 Reflection ──────────────────────────────────────────────────────

    async def reflect(self) -> list[str]:
        """Triggered when importance accumulator hits threshold.

        Synthesizes recent high-importance memories into deeper insights.
        High-N agents reflect more frequently (lower threshold).
        """
        if not self.memory.should_reflect():
            return []

        import logging as _log
        _log.getLogger(__name__).info(
            f"🔮 {self.name} reflecting (trigger={self.memory.importance_trigger_curr:.1f})"
        )

        # Step 1: identify focal points from recent high-poignancy memories
        recent = sorted(self.memory.nodes[-50:], key=lambda n: n.poignancy, reverse=True)[:15]
        mem_text = "\n".join(f"- {n.content}" for n in recent)

        focal_prompt = (
            f"Given these memories of {self.name}:\n{mem_text}\n\n"
            f"What are the 3 most important questions {self.name} is now thinking about? "
            f"List only the questions, one per line."
        )
        questions_raw = await chat(focal_prompt, temperature=0.7, max_tokens=200)
        questions = [q.strip("- ").strip() for q in questions_raw.strip().split("\n") if q.strip()][:3]

        insights: list[str] = []
        for question in questions:
            relevant = self.memory.retrieve(question, top_k=10)
            evidence = "\n".join(f"- {n.content}" for n in relevant)

            insight_prompt = (
                f"You are {self.name}. You are reflecting on: '{question}'\n"
                f"Based on these memories:\n{evidence}\n\n"
                f"What insight do you reach? Respond in 1 sentence."
            )
            insight = await chat(insight_prompt, temperature=0.75, max_tokens=150)
            insights.append(insight)

            # Determine if this insight rises to a belief (L4)
            if await self._is_belief(insight):
                await self._update_belief(question, insight)
                # Hermes: extract a reusable procedure from beliefs
                procedure = await self._extract_procedure(insight)
                if procedure:
                    self.memory.add(procedure, memory_type="procedure", depth=2, poignancy=8.0)
            else:
                self.memory.add(insight, memory_type="thought", depth=1)

        self.memory.reset_reflection_trigger()
        return insights

    # ── L4 Belief ──────────────────────────────────────────────────────────

    async def _is_belief(self, insight: str) -> bool:
        """Does this insight represent a stable worldview/faith claim?"""
        import logging as _log
        prompt = (
            f"Does this statement express a general belief, conviction, or worldview "
            f"(about nature, gods, fate, omens, community, danger, or life)? "
            f"NOT a specific plan or observation about a single event.\n"
            f"Statement: '{insight}'\n"
            f"Answer only YES or NO."
        )
        answer = await chat(prompt, temperature=0.1, max_tokens=5)
        result = "YES" in answer.upper()
        _log.getLogger(__name__).info(f"  belief check: '{insight[:60]}' → {answer.strip()}")
        return result

    async def _extract_procedure(self, belief: str) -> Optional[str]:
        """Hermes procedural memory: extract a reusable ritual/skill from a belief.

        e.g. "Gods send lightning as warning" → "When lightning strikes, burn
        an oak branch at dawn as offering"
        """
        prompt = (
            f"You are {self.name}, a {self.occupation}.\n"
            f"You hold this belief: '{belief}'\n\n"
            f"Based on this belief, what is ONE concrete, repeatable action or ritual "
            f"you would perform in the future when relevant circumstances arise?\n"
            f"If no practical procedure follows from this belief, reply with NONE.\n"
            f"Otherwise reply with a single sentence starting with 'When ...'"
        )
        result = await chat(prompt, temperature=0.7, max_tokens=80)
        result = result.strip()
        if result.upper() == "NONE" or not result.lower().startswith("when"):
            return None
        return result

    async def _update_belief(self, topic: str, new_belief: str) -> None:
        """Update L4 belief layer. High belief_resistance makes this harder."""
        existing = self.beliefs.get(topic)
        if existing and self.personality.belief_resistance > 0.7:
            # Stubborn agent: only update if new belief is strongly different
            return

        self.beliefs[topic] = new_belief
        self.memory.add(
            new_belief,
            memory_type="belief",
            depth=2,
            poignancy=8.0,
        )

    # ── L5 Action ──────────────────────────────────────────────────────────

    async def speak(self, to_agent: "Agent", social_pool: "SocialPool") -> Optional[str]:
        """Generate speech via Hermes inner-monologue then structured action.

        Step 1 — inner monologue (CoT): agent reasons over memories + beliefs
                 to decide WHAT to say and HOW (action type).
        Step 2 — generate speech grounded in that reasoning.
        Extraversion controls whether this agent initiates conversation.
        """
        import random
        if random.random() > self.personality.talk_probability:
            return None

        memories = self.memory.retrieve("important recent events or beliefs", top_k=5)
        if not memories:
            return None

        mem_text = "\n".join(f"- ({n.hermes_tier}) {n.content}" for n in memories)
        belief_text = "\n".join(f"- {b}" for b in self.beliefs.values()) or "none yet"
        proc_text = "\n".join(f"- {p.content}" for p in self.memory.procedures()) or "none"

        # Step 1: inner monologue — decide action type and topic
        monologue_prompt = (
            f"You are {self.name}, a {self.occupation}.\n"
            f"Your memories:\n{mem_text}\n\n"
            f"Your beliefs:\n{belief_text}\n\n"
            f"Your learned rituals/skills:\n{proc_text}\n\n"
            f"You are about to speak to {to_agent.name}.\n"
            f"Think step by step:\n"
            f"1. What is on your mind most right now?\n"
            f"2. Which action fits best — share_rumor, warn, perform_ritual, or gather_resource?\n"
            f"3. What exactly will you say (1 sentence)?\n"
            f"Answer as:\n"
            f"THOUGHT: <your reasoning>\n"
            f"ACTION: <share_rumor|warn|perform_ritual|gather_resource>\n"
            f"SPEECH: <what you say>"
        )
        raw = await chat(monologue_prompt, temperature=0.85, max_tokens=200)

        # Parse structured response
        action_type, speech = self._parse_monologue(raw)
        self.last_action_type = action_type
        self.last_speech = speech
        return speech

    @staticmethod
    def _parse_monologue(raw: str) -> tuple[str, str]:
        """Extract ACTION and SPEECH from inner-monologue response."""
        action_type = "share_rumor"  # default
        speech = raw.strip()  # fallback to full text

        for line in raw.splitlines():
            line = line.strip()
            if line.upper().startswith("ACTION:"):
                candidate = line.split(":", 1)[1].strip().lower()
                if candidate in ("share_rumor", "warn", "perform_ritual", "gather_resource"):
                    action_type = candidate
            elif line.upper().startswith("SPEECH:"):
                speech = line.split(":", 1)[1].strip()

        return action_type, speech

    async def receive_speech(
        self,
        speaker: "Agent",
        message: str,
        distorted_message: str,
        social_pool: "SocialPool",
    ) -> None:
        """Process incoming speech. Stores the distorted version (P2)."""
        self.memory.add(
            f"{speaker.name} told me: '{distorted_message}'",
            memory_type="chat",
            origin_content=message,
            distortion_hops=1,
        )

        # Possibly corroborate or add to social pool
        response = await self.think(f"{speaker.name} said: {distorted_message}")
        self.last_speech = response

    # ── State export ───────────────────────────────────────────────────────

    def state_snapshot(self) -> AgentState:
        return AgentState(
            agent_id=self.agent_id,
            name=self.name,
            occupation=self.occupation,
            position=self.position,
            current_action=self.current_action,
            last_speech=self.last_speech,
            belief_summary=self.memory.belief_summary(),
            personality=self.personality.to_dict(),
            avg_semantic_drift=self.memory.avg_semantic_drift(),
            memory_count=len(self.memory.nodes),
        )

    def to_dict(self) -> dict:
        s = self.state_snapshot()
        return {
            "agent_id": s.agent_id,
            "name": s.name,
            "occupation": s.occupation,
            "position": list(s.position),
            "current_action": s.current_action,
            "last_action_type": self.last_action_type,
            "last_speech": s.last_speech,
            "beliefs": self.beliefs,
            "belief_summary": s.belief_summary,
            "procedures": [p.content for p in self.memory.procedures()],
            "personality": s.personality,
            "research": {
                "avg_semantic_drift": round(s.avg_semantic_drift, 4),
                "memory_count": s.memory_count,
                "reflection_trigger": round(self.memory.importance_trigger_curr, 1),
                "memory_tiers": {
                    "episodic": sum(1 for n in self.memory.nodes if n.hermes_tier == "episodic"),
                    "semantic": sum(1 for n in self.memory.nodes if n.hermes_tier == "semantic"),
                    "procedural": sum(1 for n in self.memory.nodes if n.hermes_tier == "procedural"),
                },
            },
        }
