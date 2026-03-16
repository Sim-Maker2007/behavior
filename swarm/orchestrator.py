"""
Agent Swarm Orchestrator — The unified entry point.

Full pipeline:
  1. Load ABC behavior cards and select relevant agents for the query
  2. Ingest seed materials into OpenViking for semantic retrieval
  3. Write seed files to disk for MiroFish upload
  4. Run MiroFish pipeline (ontology -> graph -> simulate -> report)
  5. Capture simulation state back into OpenViking at each step
  6. Use OpenViking sessions to build long-term memory across predictions
  7. Return structured prediction results with full report

Requires both OpenViking and MiroFish to be running.
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Callable, Optional

import yaml

from swarm.config import SwarmConfig
from swarm.openviking_bridge import OpenVikingBridge, ContextEntry
from swarm.mirofish_adapter import MiroFishAdapter, PredictionResult, SimulationStep
from swarm.behavior_loader import BehaviorLoader, AgentProfile

logger = logging.getLogger(__name__)


class AgentSwarm:
    """
    Orchestrates OpenViking + MiroFish + ABC behavior cards into a unified
    agent swarm for scenario prediction and simulation.

    Usage:
        swarm = AgentSwarm.from_config("swarm/swarm_config.yaml")
        status = swarm.initialize()

        swarm.ingest_seed_materials(["report.pdf", "data.csv"])
        result = swarm.predict("What happens if X?")

        print(result.report_markdown)
        answer = swarm.interview_agent(result, agent_id=1, question="Why?")
        swarm.shutdown()
    """

    def __init__(self, config: SwarmConfig):
        self.config = config
        self.context = OpenVikingBridge(config.openviking)
        self.simulator = MiroFishAdapter(config.mirofish)
        self.behaviors = BehaviorLoader(config.cards_directory)
        self._seed_uris: list[str] = []
        self._seed_files: list[str] = []
        self._active_profiles: list[AgentProfile] = []
        self._last_result: PredictionResult | None = None

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
        Initialize all three subsystems. Returns status dict.
        Raises if any subsystem fails to connect.
        """
        status = {}

        # 1. OpenViking context layer
        self.context.initialize()
        status["openviking"] = "ready"

        # 2. MiroFish simulation engine
        self.simulator.initialize()
        status["mirofish"] = "ready"

        # 3. ABC behavior cards
        card_count = self.behaviors.load_all_cards()
        status["behavior_cards"] = card_count

        logger.info("Swarm initialized: %s", status)
        return status

    def ingest_seed_materials(self, paths: list[str]) -> list[str]:
        """
        Ingest seed materials into OpenViking AND track files for MiroFish upload.

        Args:
            paths: List of file paths, URLs, or directories

        Returns:
            List of viking:// URIs for the ingested materials
        """
        uris = []
        for path in paths:
            # Ingest into OpenViking for semantic search
            uri = self.context.ingest_seed_material(path)
            uris.append(uri)

            # Track local files for MiroFish upload
            p = Path(path)
            if p.exists() and p.is_file():
                self._seed_files.append(str(p.resolve()))

            logger.info("Ingested: %s -> %s", path, uri)

        self._seed_uris.extend(uris)
        return uris

    def predict(
        self,
        query: str,
        cards: list[str] | None = None,
        project_name: str = "swarm-prediction",
        on_step: Callable[[SimulationStep], None] | None = None,
    ) -> PredictionResult:
        """
        Run a full prediction scenario.

        1. Selects relevant ABC cards as agent behavior templates
        2. Gathers context from OpenViking
        3. Builds additional context from behavior cards
        4. Runs MiroFish full pipeline (graph -> sim -> report)
        5. Stores results back in OpenViking

        Args:
            query: Natural language prediction question
            cards: Optional list of specific ABC card names to use
            project_name: Name for the MiroFish project
            on_step: Optional callback for simulation progress

        Returns:
            PredictionResult with full report, findings, and agent data
        """
        logger.info("=== Starting prediction: %s ===", query)

        # Step 1: Select relevant behavior cards
        profiles = self.behaviors.select_agents_for_query(
            query,
            max_agents=self.config.max_concurrent_agents,
            required_cards=cards or self.config.selected_cards or None,
        )
        self._active_profiles = profiles
        logger.info("Selected %d agent behaviors: %s",
                     len(profiles), [p.card_name for p in profiles])

        # Step 2: Build additional context from ABC cards + OpenViking search
        additional_context = self._build_additional_context(query, profiles)

        # Step 3: Store behavior cards in OpenViking for cross-referencing
        for profile in profiles:
            card_data = self.behaviors._cards.get(profile.card_name, {})
            self.context.store_behavior_card(
                profile.card_name,
                yaml.dump(card_data, default_flow_style=False),
            )

        # Step 4: Wrap on_step to also capture state in OpenViking
        def step_with_capture(step: SimulationStep):
            self.context.store_simulation_state(step.step_number, {
                "timestamp": step.timestamp,
                "events": step.events,
                "actions": step.agent_actions,
                "state": step.world_state,
            })
            if on_step:
                on_step(step)

        # Step 5: Run the full MiroFish pipeline
        result = self.simulator.run_full_pipeline(
            seed_files=self._seed_files,
            query=query,
            project_name=project_name,
            additional_context=additional_context,
            on_step=step_with_capture,
        )

        # Step 6: Store results in OpenViking session for long-term memory
        self.context.add_session_message(
            role="user",
            content=f"Prediction query: {query}",
        )
        self.context.add_session_message(
            role="assistant",
            content=(
                f"Prediction result (sim={result.simulation_id}): "
                f"{result.report_markdown[:2000]}"
            ),
        )

        self.context.store_shared_observation(
            f"Prediction completed for: {query}. "
            f"Agents: {[p.card_name for p in profiles]}. "
            f"Findings: {'; '.join(result.key_findings[:3])}",
            tags=["prediction-result", result.simulation_id],
        )

        self._last_result = result
        logger.info("=== Prediction complete: sim=%s report=%s ===",
                     result.simulation_id, result.report_id)
        return result

    def interview_agent(
        self,
        result: PredictionResult,
        agent_id: int,
        question: str,
    ) -> str:
        """Ask a question to a specific agent from a completed simulation."""
        response = self.simulator.interview_agent(
            simulation_id=result.simulation_id,
            agent_id=agent_id,
            question=question,
        )
        # Store interview in OpenViking
        self.context.store_shared_observation(
            f"Interview agent {agent_id} in sim {result.simulation_id}: "
            f"Q: {question} A: {response[:500]}",
            tags=["interview", result.simulation_id],
        )
        return response

    def chat(self, message: str, chat_history: list[dict] | None = None) -> dict:
        """
        Chat with the report agent about the last prediction.
        Returns {"response": ..., "tool_calls": ..., "sources": ...}
        """
        if not self._last_result:
            raise RuntimeError("No prediction has been run yet. Call predict() first.")
        return self.simulator.chat_with_report(
            simulation_id=self._last_result.simulation_id,
            message=message,
            chat_history=chat_history,
        )

    def search_context(self, query: str, top_k: int = 5) -> list[ContextEntry]:
        """Search across all stored context (seeds, state, memories, behaviors)."""
        return self.context.search(query, top_k=top_k)

    def get_active_agents(self) -> list[AgentProfile]:
        """Return the currently active agent profiles."""
        return self._active_profiles

    def commit_memory(self) -> dict:
        """Commit the current session to extract long-term memories."""
        return self.context.commit_session()

    def shutdown(self) -> None:
        """Clean shutdown of all subsystems."""
        self.context.shutdown()
        self.simulator.shutdown()
        logger.info("Swarm shut down")

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _build_additional_context(
        self, query: str, profiles: list[AgentProfile]
    ) -> str:
        """
        Build additional context string from:
        - OpenViking semantic search results on the query
        - ABC behavior card summaries for selected agents
        """
        parts = []

        # OpenViking context from seed materials
        if self._seed_uris:
            results = self.context.search(
                query,
                namespace=OpenVikingBridge.NAMESPACE_SEEDS,
                top_k=5,
            )
            if results:
                parts.append("=== Relevant Context from Seed Materials ===")
                for entry in results:
                    abstract = entry.content[:300] if entry.content else ""
                    parts.append(f"[{entry.uri}] (score={entry.score:.2f}): {abstract}")
                parts.append("")

        # ABC behavior card context
        if profiles:
            parts.append("=== Agent Behavior Profiles (ABC Cards) ===")
            for p in profiles:
                parts.append(
                    f"- {p.display_name} ({p.problem_pattern}): "
                    f"triggers={json.dumps(p.triggers, default=str)[:200]}, "
                    f"reasoning={p.reasoning_approach[:200]}"
                )
            parts.append("")

        return "\n".join(parts)
