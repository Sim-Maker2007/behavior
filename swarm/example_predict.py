#!/usr/bin/env python3
"""
Example: Full Agent Swarm Prediction

Runs the complete pipeline:
  1. Initialize swarm (OpenViking + MiroFish + ABC cards)
  2. Ingest seed materials
  3. Run prediction (ontology -> graph -> simulate -> report)
  4. Interview individual agents
  5. Chat with report agent for follow-up

Prerequisites:
  ./swarm/setup.sh                     # Install everything
  cp swarm/.env.example swarm/.env     # Add your API keys
  docker compose -f swarm/docker-compose.yaml up -d  # Start services
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from swarm import AgentSwarm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("swarm-example")


def main():
    # --- 1. Initialize ---
    config_path = Path(__file__).parent / "swarm_config.yaml"
    swarm = AgentSwarm.from_config(str(config_path))

    status = swarm.initialize()
    print(f"Swarm ready: {status}")
    print(f"  OpenViking: {status['openviking']}")
    print(f"  MiroFish:   {status['mirofish']}")
    print(f"  Cards:      {status['behavior_cards']} behavior cards loaded")

    # --- 2. Ingest seed materials ---
    # Upload files that ground the simulation in reality.
    # Supports: PDF, Markdown, TXT, CSV, URLs, directories
    seed_files = [
        # "reports/quarterly-supply-chain-review.pdf",
        # "data/commodity-prices-2025.csv",
        # "https://example.com/geopolitical-risk-briefing.md",
    ]
    if seed_files:
        uris = swarm.ingest_seed_materials(seed_files)
        print(f"\nIngested {len(uris)} seed materials")

    # --- 3. Run prediction ---
    def on_step(step):
        print(f"  [Step {step.step_number}] {len(step.agent_actions)} agent actions")

    print("\nRunning prediction...")
    result = swarm.predict(
        query=(
            "What happens if a major semiconductor shortage disrupts "
            "global supply chains for 6 months?"
        ),
        # Optionally force specific agent behaviors:
        # cards=["supply-chain-disruption-detector", "crisis-simulation-planner"],
        on_step=on_step,
    )

    # --- 4. Print results ---
    print("\n" + "=" * 80)
    print("PREDICTION REPORT")
    print("=" * 80)
    print(f"Project:      {result.project_id}")
    print(f"Simulation:   {result.simulation_id}")
    print(f"Report:       {result.report_id}")
    print(f"Agents used:  {len(result.agents_involved)}")
    print(f"Sim steps:    {len(result.simulation_steps)}")

    if result.key_findings:
        print("\nKey Findings:")
        for i, finding in enumerate(result.key_findings, 1):
            print(f"  {i}. {finding[:200]}")

    print(f"\n--- Full Report ---\n{result.report_markdown}")

    # --- 5. Interview agents ---
    if result.agents_involved:
        agent = result.agents_involved[0]
        print(f"\nInterviewing agent {agent.agent_id} ({agent.name})...")
        answer = swarm.interview_agent(
            result,
            agent_id=int(agent.agent_id),
            question="What was your key observation during the simulation?",
        )
        print(f"Agent response: {answer}")

    # --- 6. Follow-up chat ---
    print("\nChatting with report agent...")
    chat_response = swarm.chat(
        "What are the three most likely cascading effects, and which industries "
        "would be hit first?"
    )
    print(f"Report agent: {chat_response.get('response', '')}")

    # --- 7. Search context ---
    print("\nSearching OpenViking context...")
    results = swarm.search_context("semiconductor impact timeline")
    for entry in results:
        print(f"  [{entry.score:.2f}] {entry.uri}: {entry.content[:100]}...")

    # --- 8. Commit long-term memory ---
    swarm.commit_memory()

    # --- 9. Cleanup ---
    swarm.shutdown()
    print("\nDone.")


if __name__ == "__main__":
    main()
