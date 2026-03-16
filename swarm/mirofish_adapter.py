"""
MiroFish Simulation Adapter — Interfaces with MiroFish's multi-agent prediction engine.

MiroFish's 5-stage pipeline:
  1. Graph Construction — extract reality seeds, build GraphRAG
  2. Environment Setup — entity extraction, character profiles, ConfigAgent
  3. Simulation Launch — dual-platform parallel simulation with temporal memory
  4. Report Generation — ReportAgent produces forecast reports
  5. Deep Interaction — converse with simulated agents

This adapter:
  - Feeds seed materials and ABC behavior profiles into MiroFish's pipeline
  - Captures simulation state at each step for OpenViking storage
  - Extracts prediction results and agent interactions
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from swarm.config import MiroFishConfig

logger = logging.getLogger(__name__)


@dataclass
class SimulationAgent:
    """An agent within the MiroFish simulation."""
    agent_id: str
    name: str
    role: str
    behavior_card: str  # ABC card name driving this agent
    personality: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)


@dataclass
class SimulationStep:
    """A single step in the simulation timeline."""
    step_number: int
    timestamp: str
    events: list[dict] = field(default_factory=list)
    agent_actions: list[dict] = field(default_factory=list)
    world_state: dict = field(default_factory=dict)


@dataclass
class PredictionResult:
    """The output of a completed simulation run."""
    query: str
    scenario_description: str
    simulation_steps: list[SimulationStep] = field(default_factory=list)
    report: str = ""
    confidence: float = 0.0
    key_findings: list[str] = field(default_factory=list)
    risk_factors: list[dict] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    agents_involved: list[SimulationAgent] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


class MiroFishAdapter:
    """
    Orchestrates MiroFish's simulation pipeline with ABC-driven agent behaviors.

    If MiroFish is not available (not running or not installed), provides a
    structured simulation framework that can be run locally using LLM calls.
    """

    def __init__(self, config: MiroFishConfig):
        self.config = config
        self._session = None
        self._connected = False

    def initialize(self) -> None:
        """Attempt to connect to MiroFish backend."""
        try:
            import requests
            resp = requests.get(f"{self.config.backend_url}/health", timeout=5)
            if resp.status_code == 200:
                self._connected = True
                logger.info("MiroFish backend connected at %s", self.config.backend_url)
                return
        except Exception as e:
            logger.debug("MiroFish connection failed: %s", e)

        logger.warning(
            "MiroFish backend not available at %s — "
            "using local LLM-based simulation fallback. "
            "Start MiroFish with: docker compose up -d",
            self.config.backend_url,
        )
        self._connected = False

    def build_simulation(
        self,
        query: str,
        seed_context: list[dict],
        agent_profiles: list[dict],
        on_step: Callable[[SimulationStep], None] | None = None,
    ) -> PredictionResult:
        """
        Run the full prediction pipeline.

        Args:
            query: The prediction question (e.g., "What if oil prices spike 40%?")
            seed_context: List of context entries from OpenViking
                          [{"uri": ..., "content": ..., "abstract": ...}]
            agent_profiles: ABC-derived agent configurations
                           [{"card_name": ..., "role": ..., "behavior": ...}]
            on_step: Optional callback invoked after each simulation step

        Returns:
            PredictionResult with report, findings, and full simulation trace
        """
        if self._connected:
            return self._run_mirofish_pipeline(query, seed_context, agent_profiles, on_step)
        else:
            return self._run_local_simulation(query, seed_context, agent_profiles, on_step)

    def _run_mirofish_pipeline(
        self, query, seed_context, agent_profiles, on_step
    ) -> PredictionResult:
        """Drive MiroFish's actual backend through its API."""
        import requests

        # Stage 1: Upload seed materials for graph construction
        seed_payload = {
            "materials": [
                {"content": ctx.get("content", ""), "metadata": ctx}
                for ctx in seed_context
            ],
            "prediction_query": query,
        }
        resp = requests.post(
            f"{self.config.backend_url}/api/simulation/create",
            json=seed_payload,
            timeout=60,
        )
        resp.raise_for_status()
        sim_id = resp.json().get("simulation_id")

        # Stage 2: Inject agent profiles derived from ABC cards
        for profile in agent_profiles:
            requests.post(
                f"{self.config.backend_url}/api/simulation/{sim_id}/agents",
                json={
                    "name": profile.get("role", "agent"),
                    "personality": profile.get("behavior", {}),
                    "behavior_card": profile.get("card_name", ""),
                },
                timeout=30,
            )

        # Stage 3: Launch simulation
        resp = requests.post(
            f"{self.config.backend_url}/api/simulation/{sim_id}/start",
            json={
                "steps": self.config.simulation_steps,
                "max_agents": self.config.max_simulation_agents,
            },
            timeout=300,
        )
        resp.raise_for_status()

        # Poll for results
        steps = []
        for _ in range(self.config.simulation_steps * 2):
            status = requests.get(
                f"{self.config.backend_url}/api/simulation/{sim_id}/status",
                timeout=30,
            ).json()

            if status.get("state") == "completed":
                break

            if status.get("latest_step"):
                step = self._parse_step(status["latest_step"])
                steps.append(step)
                if on_step:
                    on_step(step)

            time.sleep(2)

        # Stage 4: Get report
        report_resp = requests.get(
            f"{self.config.backend_url}/api/simulation/{sim_id}/report",
            timeout=60,
        ).json()

        return PredictionResult(
            query=query,
            scenario_description=report_resp.get("scenario", ""),
            simulation_steps=steps,
            report=report_resp.get("report", ""),
            confidence=report_resp.get("confidence", 0.0),
            key_findings=report_resp.get("findings", []),
            risk_factors=report_resp.get("risks", []),
            recommended_actions=report_resp.get("actions", []),
            raw_data=report_resp,
        )

    def _run_local_simulation(
        self, query, seed_context, agent_profiles, on_step
    ) -> PredictionResult:
        """
        Local fallback: structures the simulation as a series of LLM calls
        without requiring MiroFish's full infrastructure.
        """
        agents = []
        for i, profile in enumerate(agent_profiles):
            agents.append(SimulationAgent(
                agent_id=f"agent-{i:03d}",
                name=profile.get("role", f"Agent {i}"),
                role=profile.get("role", "observer"),
                behavior_card=profile.get("card_name", ""),
                personality=profile.get("behavior", {}),
            ))

        # Build structured simulation prompt
        context_summary = "\n".join(
            f"- {ctx.get('abstract', ctx.get('content', '')[:200])}"
            for ctx in seed_context[:10]
        )

        agent_summary = "\n".join(
            f"- {a.name} ({a.behavior_card}): {json.dumps(a.personality.get('trigger', {}))}"
            for a in agents
        )

        simulation_prompt = self._build_simulation_prompt(
            query, context_summary, agent_summary
        )

        # In local mode, return the structured prompt as the report
        # The actual LLM call is delegated to the orchestrator which owns the LLM client
        return PredictionResult(
            query=query,
            scenario_description=f"Local simulation for: {query}",
            simulation_steps=[],
            report=simulation_prompt,
            confidence=0.0,
            key_findings=[],
            risk_factors=[],
            recommended_actions=[],
            agents_involved=agents,
            raw_data={
                "mode": "local_fallback",
                "seed_context_count": len(seed_context),
                "agent_count": len(agents),
                "simulation_prompt": simulation_prompt,
            },
        )

    def _build_simulation_prompt(
        self, query: str, context_summary: str, agent_summary: str
    ) -> str:
        return f"""## Agent Swarm Simulation Request

### Prediction Query
{query}

### Seed Context (from OpenViking)
{context_summary}

### Swarm Agents (from ABC Behavior Cards)
{agent_summary}

### Instructions
You are running a multi-agent simulation. Each agent above has a defined behavior
pattern from an ABC card. Simulate {self.config.simulation_steps} time steps where:

1. Each agent perceives the current world state through their behavioral lens
2. Agents take actions according to their behavior specifications
3. Actions create cascading effects that other agents respond to
4. Track emergent patterns, conflicts, and convergences

Produce a structured prediction report with:
- Scenario narrative (what unfolds step by step)
- Key findings (3-5 most significant predictions)
- Risk factors (what could go wrong, with probability estimates)
- Recommended actions (what should stakeholders do)
- Confidence assessment (how reliable is this prediction)
"""

    def _parse_step(self, raw_step: dict) -> SimulationStep:
        return SimulationStep(
            step_number=raw_step.get("step", 0),
            timestamp=raw_step.get("timestamp", ""),
            events=raw_step.get("events", []),
            agent_actions=raw_step.get("actions", []),
            world_state=raw_step.get("state", {}),
        )

    def shutdown(self) -> None:
        if self._session is not None:
            self._session.close()
