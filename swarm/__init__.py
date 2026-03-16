"""
Agent Swarm — OpenViking + MiroFish + ABC Behavior Cards

A complete agent swarm system for scenario prediction and simulation.

- OpenViking: Shared context database and memory (viking:// filesystem)
- MiroFish: Multi-agent simulation engine (OASIS-based parallel worlds)
- ABC Cards: Portable behavior definitions that configure agent roles

Usage:
    from swarm import AgentSwarm

    swarm = AgentSwarm.from_config("swarm/swarm_config.yaml")
    swarm.initialize()
    swarm.ingest_seed_materials(["report.pdf", "dataset.csv"])

    result = swarm.predict("What happens if supply chain disruption hits?")
    print(result.report_markdown)

    answer = swarm.interview_agent(result, agent_id=1, question="Why did you predict that?")
    swarm.shutdown()
"""

from swarm.orchestrator import AgentSwarm
from swarm.config import SwarmConfig

__all__ = ["AgentSwarm", "SwarmConfig"]
__version__ = "0.1.0"
