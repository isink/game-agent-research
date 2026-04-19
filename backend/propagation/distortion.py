"""Semantic distortion engine — core P2 research mechanism.

When an agent retells a memory to another agent, the message passes through
this engine which:
1. Asks the LLM to retell the message "in the agent's own words"
2. Measures semantic drift from the original
3. Records the distortion for research analysis

Distortion intensity is modulated by:
- Sender's distortion_tendency (N↑, A↓ → more distortion)
- Message importance (high-poignancy events attract more embellishment)
- Number of prior hops (drift accumulates)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from llm.deepseek import chat, cosine_distance, embed
from agents.personality import BigFive


@dataclass
class DistortionRecord:
    original: str
    distorted: str
    sender_id: str
    receiver_id: str
    hop_number: int
    semantic_drift: float          # cosine distance from original
    cumulative_drift: float        # drift from very first telling
    original_embedding: list[float]
    distorted_embedding: list[float]


class DistortionEngine:
    """Applies and tracks semantic distortion during inter-agent communication."""

    def __init__(self):
        self.records: list[DistortionRecord] = []

    async def transmit(
        self,
        message: str,
        sender: "BigFive",  # type: ignore
        sender_id: str,
        receiver_id: str,
        sender_name: str,
        sender_occupation: str,
        hop_number: int = 1,
        origin_embedding: Optional[list[float]] = None,
    ) -> DistortionRecord:
        """Apply distortion to a message as it passes from sender to receiver.

        The LLM retells the message filtered through the sender's personality.
        High distortion_tendency → more embellishment and drift.
        """
        distortion_level = sender.distortion_tendency
        style = self._distortion_style(sender)

        prompt = (
            f"You are {sender_name}, a {sender_occupation}.\n"
            f"You heard the following and are now retelling it to a neighbor:\n"
            f"\"{message}\"\n\n"
            f"Retell it in your own words. {style}\n"
            f"Keep it to 1-2 sentences. Do NOT say 'I heard' or 'someone said'. "
            f"Just tell the story as you remember it."
        )

        # Temperature scales with distortion tendency (higher N/lower A = wilder retelling)
        temperature = 0.5 + 0.7 * distortion_level
        distorted = await chat(prompt, temperature=min(temperature, 1.4), max_tokens=150)

        orig_emb = origin_embedding if origin_embedding is not None else embed(message)
        dist_emb = embed(distorted)
        hop_drift = cosine_distance(embed(message), dist_emb)
        cumulative_drift = cosine_distance(orig_emb, dist_emb)

        record = DistortionRecord(
            original=message,
            distorted=distorted,
            sender_id=sender_id,
            receiver_id=receiver_id,
            hop_number=hop_number,
            semantic_drift=hop_drift,
            cumulative_drift=cumulative_drift,
            original_embedding=orig_emb,
            distorted_embedding=dist_emb,
        )
        self.records.append(record)
        return record

    def export_records(self) -> list[dict]:
        """Export all distortion records for analysis (Jupyter/NetworkX)."""
        return [
            {
                "hop": r.hop_number,
                "sender": r.sender_id,
                "receiver": r.receiver_id,
                "original": r.original,
                "distorted": r.distorted,
                "hop_drift": round(r.semantic_drift, 4),
                "cumulative_drift": round(r.cumulative_drift, 4),
            }
            for r in self.records
        ]

    def avg_drift_by_hop(self) -> dict[int, float]:
        """Mean drift at each hop number — key P2 research metric."""
        from collections import defaultdict
        bucket: dict[int, list[float]] = defaultdict(list)
        for r in self.records:
            bucket[r.hop_number].append(r.cumulative_drift)
        return {hop: sum(drifts) / len(drifts) for hop, drifts in sorted(bucket.items())}

    @staticmethod
    def _distortion_style(p: "BigFive") -> str:  # type: ignore
        """Style instruction based on personality."""
        parts = []
        if p.neuroticism > 0.7:
            parts.append("You tend to remember the most frightening or surprising parts most vividly, and may exaggerate them slightly.")
        if p.agreeableness < 0.3:
            parts.append("You add your own skeptical commentary.")
        if p.openness > 0.7:
            parts.append("You add an imaginative interpretation of what it might mean.")
        if p.extraversion > 0.7:
            parts.append("You are enthusiastic and may add colorful details.")
        if not parts:
            parts.append("You tell it faithfully but in your own simple words.")
        return " ".join(parts)
