"""Big Five (OCEAN) personality framework for agent initialization.

Each agent gets 5 continuous scores [0, 1]. These are converted to:
1. Natural language seed memory (injected as initial context)
2. Behavioral parameters (distortion rate, reflection frequency, etc.)

Beliefs/worldview/faith are NOT injected — left to emerge naturally (P3).
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class BigFive:
    openness: float        # O [0,1]: curiosity vs. conservatism
    conscientiousness: float  # C [0,1]: orderly vs. spontaneous
    extraversion: float    # E [0,1]: outgoing vs. reserved
    agreeableness: float   # A [0,1]: cooperative vs. stubborn
    neuroticism: float     # N [0,1]: sensitive/anxious vs. stable

    @classmethod
    def random(cls, seed: int | None = None) -> "BigFive":
        rng = random.Random(seed)
        return cls(
            openness=rng.random(),
            conscientiousness=rng.random(),
            extraversion=rng.random(),
            agreeableness=rng.random(),
            neuroticism=rng.random(),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "BigFive":
        return cls(**{k: float(v) for k, v in d.items()})

    def to_dict(self) -> dict:
        return {
            "openness": round(self.openness, 3),
            "conscientiousness": round(self.conscientiousness, 3),
            "extraversion": round(self.extraversion, 3),
            "agreeableness": round(self.agreeableness, 3),
            "neuroticism": round(self.neuroticism, 3),
        }

    # ── Natural language seed generation ──────────────────────────────────

    def to_seed_memory(self, name: str, age: int, occupation: str) -> str:
        """Convert Big Five scores to a natural language character description.

        Only personality traits are injected. Beliefs emerge from experience.
        """
        traits: list[str] = []

        # Openness
        if self.openness > 0.7:
            traits.append("curious and open to new ideas, always wondering about the world")
        elif self.openness < 0.3:
            traits.append("cautious and traditional, preferring familiar ways over new ones")
        else:
            traits.append("balanced between tradition and curiosity")

        # Conscientiousness
        if self.conscientiousness > 0.7:
            traits.append("organized and dependable, taking duties seriously")
        elif self.conscientiousness < 0.3:
            traits.append("spontaneous and flexible, living in the moment")
        else:
            traits.append("reasonably diligent when needed")

        # Extraversion
        if self.extraversion > 0.7:
            traits.append("sociable and talkative, enjoying company and sharing news")
        elif self.extraversion < 0.3:
            traits.append("quiet and reserved, preferring solitude to crowds")
        else:
            traits.append("comfortable both alone and with others")

        # Agreeableness
        if self.agreeableness > 0.7:
            traits.append("warm and cooperative, tending to agree with others")
        elif self.agreeableness < 0.3:
            traits.append("blunt and independent-minded, unafraid to disagree")
        else:
            traits.append("sometimes agreeable, sometimes stubborn")

        # Neuroticism
        if self.neuroticism > 0.7:
            traits.append("emotionally sensitive, easily affected by strange or frightening events")
        elif self.neuroticism < 0.3:
            traits.append("calm and emotionally stable, rarely unsettled by events")
        else:
            traits.append("moderately sensitive to stress and surprises")

        trait_str = "; ".join(traits)
        return (
            f"{name} is a {age}-year-old {occupation} in a small village. "
            f"By nature, {name} is {trait_str}. "
            f"{name} has lived here all their life and knows most villagers well."
        )

    # ── Behavioral parameters ──────────────────────────────────────────────

    @property
    def talk_probability(self) -> float:
        """E↑ → more likely to initiate conversation each tick."""
        return 0.2 + 0.6 * self.extraversion

    @property
    def distortion_tendency(self) -> float:
        """N↑, A↓ → more likely to distort info when retelling.

        Low agreeableness = less faithful to source.
        High neuroticism = amplifies emotional content.
        """
        return 0.1 + 0.4 * self.neuroticism + 0.3 * (1.0 - self.agreeableness)

    @property
    def belief_resistance(self) -> float:
        """A↓, C↑ → harder to change beliefs once formed (P3 variable)."""
        return 0.3 * (1.0 - self.agreeableness) + 0.3 * self.conscientiousness

    @property
    def miracle_sensitivity(self) -> float:
        """N↑, O↑ → more likely to assign meaning to unusual events (P3)."""
        return 0.5 * self.neuroticism + 0.5 * self.openness

    @property
    def leadership_potential(self) -> float:
        """E↑, C↑, A↓ → social dominance traits (P4 variable)."""
        return 0.4 * self.extraversion + 0.3 * self.conscientiousness + 0.3 * (1.0 - self.agreeableness)
