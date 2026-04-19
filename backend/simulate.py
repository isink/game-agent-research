"""CLI simulation runner — run experiments without Godot.

Usage:
    cd backend
    python simulate.py                          # 10 ticks, no miracle
    python simulate.py --ticks 20 --miracle rain
    python simulate.py --ticks 50 --miracle lightning --export

Output:
    - Live terminal output each tick
    - Optional JSON export to experiments/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="  [%(name)s] %(message)s",
)

from agents.village import Village


async def run(ticks: int, miracle_type: str | None, export: bool) -> None:
    village = Village()
    await village.initialize()

    print(f"\n{'='*60}")
    print(f"  REMNANTS OF THE DIVINE — Simulation")
    print(f"  Ticks: {ticks}  |  Miracle: {miracle_type or 'none'}")
    print(f"{'='*60}\n")

    # Print agent roster
    for a in village.agents:
        p = a.personality
        print(f"  {a.name:10s} ({a.occupation:20s})  "
              f"O={p.openness:.2f} C={p.conscientiousness:.2f} "
              f"E={p.extraversion:.2f} A={p.agreeableness:.2f} N={p.neuroticism:.2f}")
    print()

    # Inject miracle at tick 3 if requested
    if miracle_type:
        village.queue_miracle(miracle_type)
        print(f"  → Miracle '{miracle_type}' queued for tick 1\n")

    for t in range(1, ticks + 1):
        result = await village.tick()
        print(f"── Tick {t:03d} {'─'*50}")

        if result.miracle:
            m = result.miracle
            print(f"  ⚡ MIRACLE: {m['description']}")
            print(f"     Witnesses: {', '.join(m['witnesses'])}")

        for conv in result.conversations:
            drift_bar = "█" * int(conv["semantic_drift"] * 20)
            action_tag = f"[{conv.get('action_type', 'share_rumor')}]"
            print(f"  💬 {conv['sender']:8s} → {conv['receiver']:8s}  {action_tag:18s} drift={conv['semantic_drift']:.3f} [{drift_bar}]")
            if conv["semantic_drift"] > 0.15:
                print(f"     ORIGINAL:  \"{conv['original'][:70]}\"")
                print(f"     DISTORTED: \"{conv['distorted'][:70]}\"")

        # Reflections
        for ref in (result.reflections or []):
            print(f"  🔮 {ref['agent']} reflects:")
            for ins in ref["insights"]:
                print(f"     → {ins[:90]}")
            for topic, belief in ref["beliefs"].items():
                print(f"     🙏 BELIEF: {belief[:90]}")
            for proc in (ref.get("procedures") or []):
                print(f"     ⚙️  RITUAL:  {proc[:90]}")

        m = result.research_metrics
        print(f"  📊 avg_drift={m['avg_semantic_drift']:.4f}  "
              f"narratives={m['total_social_narratives']}  "
              f"events={m['total_distortion_events']}")

        belief_counts = m["agent_belief_counts"]
        if any(v > 0 for v in belief_counts.values()):
            print(f"  🙏 beliefs: " + "  ".join(f"{k}:{v}" for k, v in belief_counts.items() if v > 0))

        print()
        await asyncio.sleep(0.1)  # brief pause for readability

    # Final summary
    print(f"\n{'='*60}")
    print(f"  SIMULATION COMPLETE — {ticks} ticks")
    print(f"{'='*60}")
    print(f"\n  Drift by hop:")
    for hop, drift in village.distortion_engine.avg_drift_by_hop().items():
        print(f"    hop {hop}: {drift:.4f}")

    print(f"\n  Dominant narrative:")
    narratives = village.social_pool.get_dominant_narrative(tags=["miracle"])
    if narratives:
        print(f"    [{narratives[0].reinforcement_count}x] {narratives[0].social_version[:100]}")

    print(f"\n  Final beliefs:")
    for a in village.agents:
        if a.beliefs:
            print(f"    {a.name}: {list(a.beliefs.values())[0][:80]}")

    print(f"\n  Learned rituals (procedural memory):")
    for a in village.agents:
        procs = a.memory.procedures()
        if procs:
            print(f"    {a.name}: {procs[0].content[:80]}")

    print(f"\n  Memory tiers (episodic / semantic / procedural):")
    for a in village.agents:
        ep = sum(1 for n in a.memory.nodes if n.hermes_tier == "episodic")
        se = sum(1 for n in a.memory.nodes if n.hermes_tier == "semantic")
        pr = sum(1 for n in a.memory.nodes if n.hermes_tier == "procedural")
        print(f"    {a.name:10s}  episodic={ep}  semantic={se}  procedural={pr}")

    if export:
        out_dir = Path("experiments")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"sim_t{ticks}_{miracle_type or 'nomiracle'}.json"
        data = {
            "config": {"ticks": ticks, "miracle": miracle_type},
            "distortion_records": village.distortion_engine.export_records(),
            "social_narratives": village.social_pool.all_narratives(),
            "final_beliefs": {a.name: a.beliefs for a in village.agents},
            "final_procedures": {a.name: [p.content for p in a.memory.procedures()] for a in village.agents},
            "memory_tiers": {
                a.name: {
                    "episodic": sum(1 for n in a.memory.nodes if n.hermes_tier == "episodic"),
                    "semantic": sum(1 for n in a.memory.nodes if n.hermes_tier == "semantic"),
                    "procedural": sum(1 for n in a.memory.nodes if n.hermes_tier == "procedural"),
                }
                for a in village.agents
            },
            "metrics": village._research_metrics(),
        }
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"\n  ✓ Exported to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remnants of the Divine — CLI Simulation")
    parser.add_argument("--ticks", type=int, default=10)
    parser.add_argument("--miracle", type=str, default=None,
                        choices=["rain", "lightning", "harvest", "plague", "fire", "eclipse"])
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.ticks, args.miracle, args.export))


if __name__ == "__main__":
    main()
