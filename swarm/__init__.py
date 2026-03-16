"""
Agent Swarm Integration — OpenViking + MiroFish + ABC Behavior Cards

Combines:
- OpenViking: Shared context database and memory layer (viking:// filesystem)
- MiroFish: Multi-agent simulation engine for predictive scenario modeling
- ABC Cards: Portable behavior definitions that configure swarm agent roles

Usage:
    from swarm import AgentSwarm

    swarm = AgentSwarm.from_config("swarm/swarm_config.yaml")
    swarm.ingest_seed_materials(["report.pdf", "dataset.csv"])
    result = swarm.predict("What happens if supply chain disruption hits Southeast Asia?")
    print(result.report)
"""

from swarm.orchestrator import AgentSwarm
from swarm.config import SwarmConfig

__all__ = ["AgentSwarm", "SwarmConfig"]
__version__ = "0.1.0"
