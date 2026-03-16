"""
MiroFish Simulation Adapter — Drives MiroFish's real Flask API.

MiroFish pipeline (all via HTTP):
  1. POST /api/graph/ontology/generate   — upload seed files, get ontology
  2. POST /api/graph/build               — build knowledge graph in Zep
  3. POST /api/simulation/create         — create simulation from project
  4. POST /api/simulation/prepare        — generate agent profiles from graph
  5. POST /api/simulation/start          — launch OASIS multi-agent sim
  6. POST /api/report/generate           — produce prediction report
  7. POST /api/simulation/interview      — ask individual agents questions
  8. POST /api/report/chat               — chat with report agent

Requires: MiroFish backend running at configured URL (default localhost:5001)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from swarm.config import MiroFishConfig

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds between status checks
POLL_TIMEOUT = 600  # max seconds to wait for async tasks


@dataclass
class SimulationAgent:
    """An agent within the MiroFish simulation."""
    agent_id: str
    name: str
    role: str
    behavior_card: str
    personality: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)


@dataclass
class SimulationStep:
    """A snapshot from the running simulation."""
    step_number: int
    timestamp: str
    events: list[dict] = field(default_factory=list)
    agent_actions: list[dict] = field(default_factory=list)
    world_state: dict = field(default_factory=dict)


@dataclass
class PredictionResult:
    """Complete output from a simulation run."""
    query: str
    project_id: str = ""
    simulation_id: str = ""
    report_id: str = ""
    scenario_description: str = ""
    simulation_steps: list[SimulationStep] = field(default_factory=list)
    report_markdown: str = ""
    confidence: float = 0.0
    key_findings: list[str] = field(default_factory=list)
    risk_factors: list[dict] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    agents_involved: list[SimulationAgent] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


class MiroFishAdapter:
    """
    Drives MiroFish's complete pipeline through its REST API.
    No fallbacks — requires MiroFish backend to be running.
    """

    def __init__(self, config: MiroFishConfig):
        self.config = config
        self.base_url = config.backend_url.rstrip("/")

    def initialize(self) -> None:
        """Verify MiroFish backend is reachable."""
        resp = requests.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            raise ConnectionError(f"MiroFish health check failed: {data}")
        logger.info("MiroFish backend connected at %s", self.base_url)

    # -------------------------------------------------------------------------
    # Stage 1: Graph Construction
    # -------------------------------------------------------------------------

    def create_project(
        self,
        seed_files: list[str],
        simulation_requirement: str,
        project_name: str = "swarm-prediction",
        additional_context: str = "",
    ) -> dict:
        """
        Upload seed materials and generate ontology.
        Returns: {"project_id": ..., "ontology": ..., "analysis_summary": ...}
        """
        files = []
        for fpath in seed_files:
            p = Path(fpath)
            if p.exists():
                files.append(("files", (p.name, open(p, "rb"))))

        data = {
            "simulation_requirement": simulation_requirement,
            "project_name": project_name,
        }
        if additional_context:
            data["additional_context"] = additional_context

        resp = requests.post(
            f"{self.base_url}/api/graph/ontology/generate",
            files=files or None,
            data=data,
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()

        if not result.get("success"):
            raise RuntimeError(f"Ontology generation failed: {result.get('error')}")

        logger.info("Project created: %s", result["data"]["project_id"])
        return result["data"]

    def build_graph(
        self,
        project_id: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> str:
        """
        Build knowledge graph from project materials.
        Waits for completion. Returns graph_id.
        """
        resp = requests.post(
            f"{self.base_url}/api/graph/build",
            json={
                "project_id": project_id,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("success"):
            raise RuntimeError(f"Graph build failed: {result.get('error')}")

        task_id = result["data"]["task_id"]
        logger.info("Graph build started: task=%s", task_id)

        # Poll until complete
        graph_id = self._poll_task(task_id)

        # Get graph_id from project
        project = requests.get(
            f"{self.base_url}/api/graph/project/{project_id}",
            timeout=30,
        ).json()
        graph_id = project.get("data", {}).get("graph_id", graph_id)
        logger.info("Graph built: %s", graph_id)
        return graph_id

    # -------------------------------------------------------------------------
    # Stage 2: Simulation Setup
    # -------------------------------------------------------------------------

    def create_simulation(
        self,
        project_id: str,
        graph_id: str | None = None,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> str:
        """Create a simulation instance. Returns simulation_id."""
        payload = {
            "project_id": project_id,
            "enable_twitter": enable_twitter,
            "enable_reddit": enable_reddit,
        }
        if graph_id:
            payload["graph_id"] = graph_id

        resp = requests.post(
            f"{self.base_url}/api/simulation/create",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("success"):
            raise RuntimeError(f"Simulation create failed: {result.get('error')}")

        sim_id = result["data"]["simulation_id"]
        logger.info("Simulation created: %s", sim_id)
        return sim_id

    def prepare_simulation(
        self,
        simulation_id: str,
        entity_types: list[str] | None = None,
        use_llm_for_profiles: bool = True,
        parallel_profile_count: int = 5,
    ) -> dict:
        """
        Generate agent profiles from knowledge graph entities.
        Waits for completion. Returns preparation details.
        """
        payload = {
            "simulation_id": simulation_id,
            "use_llm_for_profiles": use_llm_for_profiles,
            "parallel_profile_count": parallel_profile_count,
        }
        if entity_types:
            payload["entity_types"] = entity_types

        resp = requests.post(
            f"{self.base_url}/api/simulation/prepare",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("success"):
            raise RuntimeError(f"Simulation prepare failed: {result.get('error')}")

        task_id = result["data"]["task_id"]
        logger.info(
            "Simulation prep started: task=%s, expected_entities=%s",
            task_id,
            result["data"].get("expected_entities_count"),
        )

        # Poll until complete
        self._poll_prepare(simulation_id, task_id)

        logger.info("Simulation prepared: %s", simulation_id)
        return result["data"]

    # -------------------------------------------------------------------------
    # Stage 3: Run Simulation
    # -------------------------------------------------------------------------

    def start_simulation(
        self,
        simulation_id: str,
        on_step: Callable[[SimulationStep], None] | None = None,
    ) -> list[SimulationStep]:
        """
        Launch the OASIS simulation and monitor until completion.
        Returns list of simulation steps captured.
        """
        resp = requests.post(
            f"{self.base_url}/api/simulation/start",
            json={"simulation_id": simulation_id},
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("success"):
            raise RuntimeError(f"Simulation start failed: {result.get('error')}")

        logger.info("Simulation started: pid=%s", result["data"].get("process_pid"))

        # Monitor simulation progress
        steps = []
        last_action_count = 0
        elapsed = 0

        while elapsed < POLL_TIMEOUT:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            status = requests.get(
                f"{self.base_url}/api/simulation/{simulation_id}/run-status/detail",
                timeout=30,
            ).json()

            state = status.get("data", {})
            runner_status = state.get("status", "")

            # Capture new actions as steps
            actions = state.get("recent_actions", [])
            if len(actions) > last_action_count:
                new_actions = actions[last_action_count:]
                step = SimulationStep(
                    step_number=len(steps),
                    timestamp=state.get("current_time", ""),
                    agent_actions=new_actions,
                    world_state={"round": state.get("current_round", 0)},
                )
                steps.append(step)
                last_action_count = len(actions)
                if on_step:
                    on_step(step)

            if runner_status in ("completed", "finished", "stopped", "error"):
                break

            logger.debug(
                "Sim progress: round=%s actions=%s status=%s",
                state.get("current_round"),
                state.get("total_actions"),
                runner_status,
            )

        logger.info("Simulation finished: %d steps captured", len(steps))
        return steps

    def get_simulation_actions(self, simulation_id: str, limit: int = 500) -> list[dict]:
        """Get all actions from a completed simulation."""
        resp = requests.get(
            f"{self.base_url}/api/simulation/{simulation_id}/actions",
            params={"limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("actions", [])

    def get_agent_stats(self, simulation_id: str) -> dict:
        """Get per-agent statistics from simulation."""
        resp = requests.get(
            f"{self.base_url}/api/simulation/{simulation_id}/agent-stats",
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})

    # -------------------------------------------------------------------------
    # Stage 4: Report Generation
    # -------------------------------------------------------------------------

    def generate_report(self, simulation_id: str) -> dict:
        """
        Generate prediction report from simulation results.
        Waits for completion. Returns report data.
        """
        resp = requests.post(
            f"{self.base_url}/api/report/generate",
            json={"simulation_id": simulation_id},
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("success"):
            raise RuntimeError(f"Report generation failed: {result.get('error')}")

        report_id = result["data"]["report_id"]
        task_id = result["data"]["task_id"]
        logger.info("Report generation started: report=%s task=%s", report_id, task_id)

        # Poll until complete
        self._poll_report(simulation_id, task_id)

        # Fetch the final report
        report_resp = requests.get(
            f"{self.base_url}/api/report/{report_id}",
            timeout=30,
        )
        report_resp.raise_for_status()
        report_data = report_resp.json().get("data", {})

        logger.info("Report generated: %s", report_id)
        return report_data

    # -------------------------------------------------------------------------
    # Stage 5: Interaction
    # -------------------------------------------------------------------------

    def interview_agent(
        self,
        simulation_id: str,
        agent_id: int,
        question: str,
    ) -> str:
        """Interview a specific simulated agent. Returns the agent's response."""
        resp = requests.post(
            f"{self.base_url}/api/simulation/interview",
            json={
                "simulation_id": simulation_id,
                "agent_id": agent_id,
                "question": question,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("response", "")

    def chat_with_report(
        self,
        simulation_id: str,
        message: str,
        chat_history: list[dict] | None = None,
    ) -> dict:
        """Chat with the report agent for follow-up analysis."""
        resp = requests.post(
            f"{self.base_url}/api/report/chat",
            json={
                "simulation_id": simulation_id,
                "message": message,
                "chat_history": chat_history or [],
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})

    # -------------------------------------------------------------------------
    # Full Pipeline
    # -------------------------------------------------------------------------

    def run_full_pipeline(
        self,
        seed_files: list[str],
        query: str,
        project_name: str = "swarm-prediction",
        additional_context: str = "",
        on_step: Callable[[SimulationStep], None] | None = None,
    ) -> PredictionResult:
        """
        Run the complete MiroFish pipeline end-to-end:
          ontology -> graph -> sim create -> prepare -> run -> report
        """
        # Stage 1: Ontology + Graph
        project = self.create_project(
            seed_files=seed_files,
            simulation_requirement=query,
            project_name=project_name,
            additional_context=additional_context,
        )
        project_id = project["project_id"]

        graph_id = self.build_graph(project_id)

        # Stage 2: Create + Prepare Simulation
        sim_id = self.create_simulation(project_id, graph_id)
        self.prepare_simulation(sim_id)

        # Stage 3: Run Simulation
        steps = self.start_simulation(sim_id, on_step=on_step)

        # Stage 4: Generate Report
        report_data = self.generate_report(sim_id)

        # Gather agent info
        agent_stats = self.get_agent_stats(sim_id)
        agents = [
            SimulationAgent(
                agent_id=str(a.get("agent_id", i)),
                name=a.get("name", f"Agent-{i}"),
                role=a.get("role", "participant"),
                behavior_card="",
                personality=a,
            )
            for i, a in enumerate(agent_stats.get("agents", []))
        ]

        return PredictionResult(
            query=query,
            project_id=project_id,
            simulation_id=sim_id,
            report_id=report_data.get("report_id", ""),
            scenario_description=report_data.get("outline", ""),
            simulation_steps=steps,
            report_markdown=report_data.get("markdown_content", ""),
            key_findings=self._extract_findings(report_data),
            agents_involved=agents,
            raw_data=report_data,
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _poll_task(self, task_id: str) -> str:
        """Poll a generic graph task until completion."""
        elapsed = 0
        while elapsed < POLL_TIMEOUT:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = requests.get(
                f"{self.base_url}/api/graph/task/{task_id}",
                timeout=30,
            )
            data = resp.json().get("data", {})
            status = data.get("status", "")
            if status == "completed":
                return data.get("result", {}).get("graph_id", "")
            if status == "failed":
                raise RuntimeError(f"Task {task_id} failed: {data.get('message')}")
            logger.debug("Task %s: %s (%s%%)", task_id, status, data.get("progress", 0))
        raise TimeoutError(f"Task {task_id} timed out after {POLL_TIMEOUT}s")

    def _poll_prepare(self, simulation_id: str, task_id: str) -> None:
        """Poll simulation preparation until completion."""
        elapsed = 0
        while elapsed < POLL_TIMEOUT:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = requests.post(
                f"{self.base_url}/api/simulation/prepare/status",
                json={"task_id": task_id, "simulation_id": simulation_id},
                timeout=30,
            )
            data = resp.json().get("data", {})
            status = data.get("status", "")
            if status in ("completed", "ready"):
                return
            if status == "failed":
                raise RuntimeError(f"Prepare failed: {data.get('message')}")
            logger.debug("Prepare %s: %s%%", simulation_id, data.get("progress", 0))
        raise TimeoutError(f"Prepare {simulation_id} timed out")

    def _poll_report(self, simulation_id: str, task_id: str) -> None:
        """Poll report generation until completion."""
        elapsed = 0
        while elapsed < POLL_TIMEOUT:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = requests.post(
                f"{self.base_url}/api/report/generate/status",
                json={"task_id": task_id, "simulation_id": simulation_id},
                timeout=30,
            )
            data = resp.json().get("data", {})
            status = data.get("status", "")
            if status in ("completed", "ready"):
                return
            if status == "failed":
                raise RuntimeError(f"Report generation failed: {data.get('message')}")
            logger.debug("Report %s: %s%%", simulation_id, data.get("progress", 0))
        raise TimeoutError(f"Report {simulation_id} timed out")

    def _extract_findings(self, report_data: dict) -> list[str]:
        """Extract key findings from report sections."""
        findings = []
        for section in report_data.get("sections", []):
            title = section.get("title", "").lower()
            if any(kw in title for kw in ["finding", "conclusion", "key", "summary"]):
                findings.append(section.get("content", "")[:500])
        return findings

    def shutdown(self) -> None:
        """No persistent connections to close."""
        pass
