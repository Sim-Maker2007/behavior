"""
OpenViking Context Bridge — Shared memory and context layer for the agent swarm.

OpenViking provides:
- viking:// virtual filesystem for organizing all agent context
- L0/L1/L2 tiered loading (abstract → overview → full content)
- Semantic search across all ingested materials
- Session-based memory that persists across simulation steps

This bridge maps swarm concepts to OpenViking's filesystem:
    viking://resources/seed-materials/    ← user-uploaded docs, reports, data
    viking://resources/simulation-state/  ← MiroFish world state snapshots
    viking://memories/agent-{id}/         ← per-agent memory from simulation
    viking://memories/swarm-shared/       ← shared observations across agents
    viking://skills/behaviors/            ← loaded ABC behavior cards
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

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

    If OpenViking is not installed, falls back to a local in-memory store
    so the swarm can still run (without persistent semantic search).
    """

    NAMESPACE_SEEDS = "viking://resources/seed-materials"
    NAMESPACE_STATE = "viking://resources/simulation-state"
    NAMESPACE_AGENT_MEM = "viking://memories/agent-{agent_id}"
    NAMESPACE_SHARED = "viking://memories/swarm-shared"
    NAMESPACE_BEHAVIORS = "viking://skills/behaviors"

    def __init__(self, config: OpenVikingConfig):
        self.config = config
        self._client = None
        self._fallback_store: dict[str, list[ContextEntry]] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Connect to OpenViking or set up fallback store."""
        try:
            import openviking as ov
            if self.config.mode == "local":
                self._client = ov.OpenViking(path=self.config.workspace_path)
            else:
                self._client = ov.SyncHTTPClient(url=self.config.server_url)
            self._client.initialize()
            logger.info("OpenViking connected (%s mode)", self.config.mode)
        except ImportError:
            logger.warning(
                "openviking package not installed — using in-memory fallback. "
                "Install with: pip install openviking"
            )
            self._client = None
        self._initialized = True

    def ingest_seed_material(self, path: str) -> str:
        """
        Ingest a file, URL, or directory as seed material for simulation.
        Returns the viking:// URI for the ingested resource.
        """
        self._ensure_initialized()
        if self._client is not None:
            result = self._client.add_resource(path=path)
            uri = result.get("root_uri", f"{self.NAMESPACE_SEEDS}/{Path(path).name}")
            self._client.wait_processed()
            logger.info("Ingested seed material: %s → %s", path, uri)
            return uri
        else:
            uri = f"{self.NAMESPACE_SEEDS}/{Path(path).name}"
            content = self._read_local_file(path)
            self._fallback_put(uri, content)
            return uri

    def store_simulation_state(self, step: int, state: dict) -> str:
        """Snapshot the simulation world state at a given step."""
        self._ensure_initialized()
        uri = f"{self.NAMESPACE_STATE}/step-{step:04d}"
        payload = json.dumps(state, default=str)
        if self._client is not None:
            self._client.add_resource(path=f"data:application/json,{payload}")
        else:
            self._fallback_put(uri, payload)
        return uri

    def store_agent_memory(self, agent_id: str, memory: dict) -> str:
        """Store or update an individual agent's memory."""
        self._ensure_initialized()
        uri = self.NAMESPACE_AGENT_MEM.format(agent_id=agent_id)
        payload = json.dumps(memory, default=str)
        if self._client is not None:
            self._client.add_resource(path=f"data:application/json,{payload}")
        else:
            self._fallback_put(uri, payload)
        return uri

    def store_shared_observation(self, observation: str, tags: list[str] | None = None) -> str:
        """Add a shared observation visible to all swarm agents."""
        self._ensure_initialized()
        uri = f"{self.NAMESPACE_SHARED}/{hash(observation) & 0xFFFFFFFF:08x}"
        entry = {"observation": observation, "tags": tags or []}
        payload = json.dumps(entry)
        if self._client is not None:
            self._client.add_resource(path=f"data:application/json,{payload}")
        else:
            self._fallback_put(uri, payload)
        return uri

    def store_behavior_card(self, card_name: str, card_yaml: str) -> str:
        """Store an ABC behavior card in the skills namespace."""
        self._ensure_initialized()
        uri = f"{self.NAMESPACE_BEHAVIORS}/{card_name}"
        if self._client is not None:
            self._client.add_resource(path=f"data:text/yaml,{card_yaml}")
        else:
            self._fallback_put(uri, card_yaml)
        return uri

    def search(self, query: str, namespace: str | None = None, top_k: int = 5) -> list[ContextEntry]:
        """
        Semantic search across stored context.
        Optionally scoped to a namespace (e.g., seed materials only).
        """
        self._ensure_initialized()
        if self._client is not None:
            target_uri = namespace or "viking://"
            results = self._client.find(query, target_uri=target_uri)
            return [
                ContextEntry(
                    uri=r.uri,
                    content=self._client.read(r.uri) if hasattr(r, "uri") else "",
                    score=getattr(r, "score", 0.0),
                )
                for r in (results.resources if hasattr(results, "resources") else [])[:top_k]
            ]
        else:
            return self._fallback_search(query, namespace, top_k)

    def get_abstract(self, uri: str) -> str:
        """Get L0 one-sentence abstract of a resource."""
        self._ensure_initialized()
        if self._client is not None:
            return self._client.abstract(uri)
        entries = self._fallback_store.get(uri, [])
        if entries:
            return entries[0].content[:200] + "..."
        return ""

    def get_overview(self, uri: str) -> str:
        """Get L1 core overview (~2k tokens) of a resource."""
        self._ensure_initialized()
        if self._client is not None:
            return self._client.overview(uri)
        entries = self._fallback_store.get(uri, [])
        if entries:
            return entries[0].content[:2000]
        return ""

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.close()
            logger.info("OpenViking connection closed")

    # -- Internal helpers --

    def _ensure_initialized(self):
        if not self._initialized:
            self.initialize()

    def _read_local_file(self, path: str) -> str:
        p = Path(path)
        if p.exists() and p.is_file():
            return p.read_text(errors="replace")
        return f"[Reference: {path}]"

    def _fallback_put(self, uri: str, content: str):
        entry = ContextEntry(uri=uri, content=content)
        self._fallback_store.setdefault(uri, []).append(entry)

    def _fallback_search(self, query: str, namespace: str | None, top_k: int) -> list[ContextEntry]:
        """Simple keyword search fallback when OpenViking is not available."""
        query_terms = set(query.lower().split())
        scored = []
        for uri, entries in self._fallback_store.items():
            if namespace and not uri.startswith(namespace):
                continue
            for entry in entries:
                content_lower = entry.content.lower()
                hits = sum(1 for t in query_terms if t in content_lower)
                if hits > 0:
                    entry.score = hits / len(query_terms)
                    scored.append(entry)
        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:top_k]
