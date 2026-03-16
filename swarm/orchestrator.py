"""
Agent Swarm Orchestrator — The unified entry point.

Ties together:
  - OpenViking (shared context/memory)
  - MiroFish (multi-agent simulation)
  - ABC Cards (behavior definitions)

Pipeline:
  1. Load & select ABC behavior cards relevant to the prediction query
  2. Ingest seed materials into OpenViking for semantic retrieval
  3. Build agent profiles from selected cards
  4. Feed context + agents into MiroFish simulation
  5. Capture simulation state back into OpenViking at each step
  6. Return structured prediction results
"""

import json
import logging
from pathlib import Path
from typing import Callable, Optional

from swarm.config import SwarmConfig
from swarm.openviking_bridge import OpenVikingBridge, ContextEntry
from swarm.mirofish_adapter import MiroFishAdapter, PredictionResult, SimulationStep
from swarm.behavior_loader import BehaviorLoader, AgentProfile

logger = logging.getLogger(__name__)


class AgentSwarm:
    """
    Main orchestrator for the OpenViking + MiroFish + ABC agent swarm.

    Usage:
        swarm = AgentSwarm.from_config("swarm/swarm_config.yaml")
        swarm.ingest_seed_materials(["report.pdf", "data.csv", "https://example.com"])
        result = swarm.predict("What happens if X?")
        print(result.report)
    """

    def __init__(self, config: SwarmConfig):
        self.config = config
        self.context = OpenVikingBridge(config.openviking)
        self.simulator = MiroFishAdapter(config.mirofish)
        self.behaviors = BehaviorLoader(config.cards_directory)
        self._seed_uris: list[str] = []
        self._active_profiles: list[AgentProfile] = []

    @classmethod
    def from_config(cls, path: str) -> "AgentSwarm":
        """Create a swarm from a YAML config file."""
        config = SwarmConfig.from_yaml(path)
        return cls(config)

    @classmethod
    def from_env(cls) -> "AgentSwarm":
        """Create a swarm from environment variables."""
        config = SwarmConfig.from_env()
        return cls(config)

    def initialize(self) -> dict:
        """
        Initialize all subsystems and load behavior cards.
        Returns a status dict with component readiness.
        """
        status = {}

        # 1. Initialize OpenViking context layer
        self.context.initialize()
        status["openviking"] = "ready"

        # 2. Initialize MiroFish simulation engine
        self.simulator.initialize()
        status["mirofish"] = "connected" if self.simulator._connected else "local_fallback"

        # 3. Load ABC behavior cards
        card_count = self.behaviors.load_all_cards()
        status["behavior_cards"] = card_count

        logger.info("Swarm initialized: %s", status)
        return status

    def ingest_seed_materials(self, paths: list[str]) -> list[str]:
        """
        Ingest seed materials (files, URLs, directories) into the shared context.
        These become the "reality seeds" that ground the simulation.

        Returns list of viking:// URIs for the ingested materials.
        """
        uris = []
        for path in paths:
            uri = self.context.ingest_seed_material(path)
            uris.append(uri)
            logger.info("Ingested: %s → %s", path, uri)
        self._seed_uris.extend(uris)
        return uris

    def predict(
        self,
        query: str,
        cards: list[str] | None = None,
        on_step: Callable[[SimulationStep], None] | None = None,
    ) -> PredictionResult:
        """
        Run a prediction scenario.

        Args:
            query: Natural language prediction question
            cards: Optional list of specific ABC card names to use as agents.
                   If None, auto-selects based on query relevance.
            on_step: Optional callback for each simulation step

        Returns:
            PredictionResult with report, findings, risks, and recommendations
        """
        logger.info("Starting prediction: %s", query)

        # Step 1: Select relevant behavior cards
        if cards or self.config.selected_cards:
            profiles = self.behaviors.select_agents_for_query(
                query,
                max_agents=self.config.max_concurrent_agents,
                required_cards=cards or self.config.selected_cards,
            )
        else:
            profiles = self.behaviors.select_agents_for_query(
                query,
                max_agents=self.config.max_concurrent_agents,
            )
        self._active_profiles = profiles

        logger.info(
            "Selected %d agents: %s",
            len(profiles),
            [p.card_name for p in profiles],
        )

        # Step 2: Gather relevant context from OpenViking
        seed_context = self._gather_context(query)

        # Step 3: Build MiroFish agent configs from ABC profiles
        agent_configs = [
            self.behaviors.profile_to_mirofish_config(p)
            for p in profiles
        ]

        # Step 4: Store behavior cards in OpenViking for agent reference
        for profile in profiles:
            card_data = self.behaviors._cards.get(profile.card_name, {})
            try:
                import yaml
                card_yaml = yaml.dump(card_data)
            except ImportError:
                card_yaml = json.dumps(card_data, indent=2)
            self.context.store_behavior_card(profile.card_name, card_yaml)

        # Step 5: Run simulation with step capture
        def step_with_capture(step: SimulationStep):
            # Store each simulation step in OpenViking
            self.context.store_simulation_state(step.step_number, {
                "events": step.events,
                "actions": step.agent_actions,
                "state": step.world_state,
            })
            # Forward to user callback
            if on_step:
                on_step(step)

        result = self.simulator.build_simulation(
            query=query,
            seed_context=seed_context,
            agent_profiles=agent_configs,
            on_step=step_with_capture,
        )

        # Step 6: Store final results as shared observation
        self.context.store_shared_observation(
            f"Prediction completed for: {query}. "
            f"Confidence: {result.confidence}. "
            f"Key findings: {'; '.join(result.key_findings[:3])}",
            tags=["prediction-result", "completed"],
        )

        logger.info("Prediction complete. Confidence: %.2f", result.confidence)
        return result

    def get_active_agents(self) -> list[AgentProfile]:
        """Return the currently active agent profiles."""
        return self._active_profiles

    def search_context(self, query: str, top_k: int = 5) -> list[ContextEntry]:
        """Search across all stored context (seeds, state, memories)."""
        return self.context.search(query, top_k=top_k)

    def shutdown(self) -> None:
        """Clean shutdown of all subsystems."""
        self.context.shutdown()
        self.simulator.shutdown()
        logger.info("Swarm shut down")

    def _gather_context(self, query: str) -> list[dict]:
        """
        Retrieve relevant context from OpenViking for the prediction query.
        Uses tiered loading: L0 abstracts for all seeds, L1/L2 for relevant ones.
        """
        context_entries = []

        # Get abstracts for all seed materials (cheap L0 check)
        for uri in self._seed_uris:
            abstract = self.context.get_abstract(uri)
            context_entries.append({
                "uri": uri,
                "abstract": abstract,
                "content": abstract,  # Start with abstract
            })

        # Semantic search for most relevant seeds
        if self._seed_uris:
            search_results = self.context.search(
                query,
                namespace=OpenVikingBridge.NAMESPACE_SEEDS,
                top_k=5,
            )
            for result in search_results:
                # Upgrade to L1 overview for top results
                overview = self.context.get_overview(result.uri)
                context_entries.append({
                    "uri": result.uri,
                    "abstract": result.content[:200],
                    "content": overview or result.content,
                    "relevance_score": result.score,
                })

        # If no seeds ingested, provide empty context
        if not context_entries:
            context_entries.append({
                "uri": "viking://resources/none",
                "abstract": "No seed materials provided",
                "content": "Simulation will rely on agent knowledge and behavior cards only.",
            })

        return context_entries
