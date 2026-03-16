"""
OpenViking Context Bridge — Shared memory and context layer for the agent swarm.

Uses the real OpenViking Python SDK to provide:
- viking:// virtual filesystem for organizing all agent context
- L0/L1/L2 tiered loading (abstract -> overview -> full content)
- Semantic search across all ingested materials
- Session-based memory that persists across simulation steps

Filesystem layout:
    viking://resources/seed-materials/    <- user-uploaded docs, reports, data
    viking://resources/simulation-state/  <- MiroFish world state snapshots
    viking://memories/agent-{id}/         <- per-agent memory from simulation
    viking://memories/swarm-shared/       <- shared observations across agents
    viking://skills/behaviors/            <- loaded ABC behavior cards

Requires: pip install openviking
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import openviking as ov

from swarm.config import OpenVikingConfig

logger = logging.getLogger(__name__)


@dataclass
class ContextEntry:
    """A piece of context stored in the Viking filesystem."""
    uri: str
    content: str
    level: str = "L2"  # L0=abstract, L1=overview, L2=full
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


class OpenVikingBridge:
    """
    Wraps the OpenViking client to provide swarm-specific context operations.
    Connects in local (embedded) or remote (HTTP server) mode.
    """

    NAMESPACE_SEEDS = "viking://resources/seed-materials"
    NAMESPACE_STATE = "viking://resources/simulation-state"
    NAMESPACE_AGENT_MEM = "viking://memories/agent-{agent_id}"
    NAMESPACE_SHARED = "viking://memories/swarm-shared"
    NAMESPACE_BEHAVIORS = "viking://skills/behaviors"

    def __init__(self, config: OpenVikingConfig):
        self.config = config
        self._client = None
        self._session = None

    def initialize(self) -> None:
        """Connect to OpenViking in the configured mode."""
        if self.config.mode == "local":
            self._client = ov.SyncOpenViking(path=self.config.workspace_path)
        else:
            self._client = ov.SyncHTTPClient(url=self.config.server_url)
        self._client.initialize()

        # Create namespace directories
        for ns in [self.NAMESPACE_SEEDS, self.NAMESPACE_STATE,
                    self.NAMESPACE_SHARED, self.NAMESPACE_BEHAVIORS]:
            try:
                self._client.mkdir(ns)
            except Exception:
                pass  # Already exists

        # Create a session for swarm interactions
        self._session = self._client.session()

        logger.info("OpenViking initialized (%s mode)", self.config.mode)

    def ingest_seed_material(self, path: str) -> str:
        """
        Ingest a file, URL, or directory as seed material for simulation.
        Returns the viking:// URI for the ingested resource.
        """
        result = self._client.add_resource(
            path=path,
            parent=self.NAMESPACE_SEEDS,
            reason="Seed material for agent swarm simulation",
            wait=True,
            build_index=True,
            summarize=True,
        )
        uri = result["root_uri"]
        logger.info("Ingested seed material: %s -> %s", path, uri)
        return uri

    def store_simulation_state(self, step: int, state: dict) -> str:
        """Snapshot the simulation world state at a given step."""
        payload = json.dumps(state, default=str)
        # Write state as a JSON resource under simulation-state namespace
        uri = f"{self.NAMESPACE_STATE}/step-{step:04d}.json"
        result = self._client.add_resource(
            path=f"data:application/json,{payload}",
            to=uri,
            reason=f"Simulation state at step {step}",
            build_index=True,
        )
        return result.get("root_uri", uri)

    def store_agent_memory(self, agent_id: str, memory: dict) -> str:
        """Store or update an individual agent's memory."""
        ns = self.NAMESPACE_AGENT_MEM.format(agent_id=agent_id)
        try:
            self._client.mkdir(ns)
        except Exception:
            pass
        payload = json.dumps(memory, default=str)
        result = self._client.add_resource(
            path=f"data:application/json,{payload}",
            parent=ns,
            reason=f"Agent {agent_id} memory update",
        )
        return result.get("root_uri", ns)

    def store_shared_observation(self, observation: str, tags: list[str] | None = None) -> str:
        """Add a shared observation visible to all swarm agents."""
        entry = {"observation": observation, "tags": tags or []}
        payload = json.dumps(entry)
        result = self._client.add_resource(
            path=f"data:application/json,{payload}",
            parent=self.NAMESPACE_SHARED,
            reason="Shared swarm observation",
            build_index=True,
        )
        return result.get("root_uri", self.NAMESPACE_SHARED)

    def store_behavior_card(self, card_name: str, card_yaml: str) -> str:
        """Store an ABC behavior card in the skills namespace."""
        result = self._client.add_resource(
            path=f"data:text/yaml,{card_yaml}",
            to=f"{self.NAMESPACE_BEHAVIORS}/{card_name}.yaml",
            reason=f"ABC behavior card: {card_name}",
            build_index=True,
            summarize=True,
        )
        return result.get("root_uri", f"{self.NAMESPACE_BEHAVIORS}/{card_name}")

    def search(self, query: str, namespace: str | None = None, top_k: int = 5) -> list[ContextEntry]:
        """Semantic search across stored context, optionally scoped to a namespace."""
        target_uri = namespace or "viking://"
        results = self._client.find(query, target_uri=target_uri, limit=top_k)
        entries = []
        for r in results.resources:
            content = self._client.read(r.uri)
            entries.append(ContextEntry(
                uri=r.uri,
                content=content,
                score=r.score,
            ))
        return entries

    def get_abstract(self, uri: str) -> str:
        """Get L0 one-sentence abstract of a resource."""
        return self._client.abstract(uri)

    def get_overview(self, uri: str) -> str:
        """Get L1 core overview (~2k tokens) of a resource."""
        return self._client.overview(uri)

    def read(self, uri: str) -> str:
        """Get full L2 content of a resource."""
        return self._client.read(uri)

    def add_session_message(self, role: str, content: str) -> None:
        """Add a message to the swarm session for memory extraction."""
        self._session.add_message(role=role, content=content)

    def commit_session(self) -> dict:
        """Commit the session to extract long-term memories."""
        return self._session.commit()

    def shutdown(self) -> None:
        """Close OpenViking connection."""
        if self._client is not None:
            self._client.close()
            logger.info("OpenViking connection closed")
