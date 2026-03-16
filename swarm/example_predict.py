#!/usr/bin/env python3
"""
Example: Running the Agent Swarm for Scenario Prediction

This script demonstrates the full pipeline:
  1. Initialize the swarm (OpenViking + MiroFish + ABC cards)
  2. Ingest seed materials (reports, data, URLs)
  3. Run a prediction query
  4. Process results

Prerequisites:
  pip install openviking pyyaml requests

  # Optional: start MiroFish for full simulation
  # cd MiroFish && docker compose up -d

  # Set API keys
  export LLM_API_KEY="your-key"
  export ZEP_API_KEY="your-zep-key"  # optional, for MiroFish memory
"""

import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from swarm import AgentSwarm
from swarm.config import SwarmConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("swarm-example")


def main():
    # --- 1. Initialize from config file or environment ---
    config_path = Path(__file__).parent / "swarm_config.yaml"
    if config_path.exists():
        swarm = AgentSwarm.from_config(str(config_path))
    else:
        swarm = AgentSwarm.from_env()

    status = swarm.initialize()
    logger.info("Swarm status: %s", status)

    # --- 2. Ingest seed materials ---
    # These ground the simulation in real data. Can be files, URLs, or directories.
    # Examples (uncomment as needed):
    #
    # swarm.ingest_seed_materials([
    #     "reports/quarterly-supply-chain-review.pdf",
    #     "data/commodity-prices-2025.csv",
    #     "https://example.com/geopolitical-risk-briefing",
    # ])

    # --- 3. Run prediction ---
    def on_step(step):
        """Optional: track simulation progress."""
        logger.info(
            "Step %d: %d events, %d agent actions",
            step.step_number,
            len(step.events),
            len(step.agent_actions),
        )

    result = swarm.predict(
        query="What happens if a major semiconductor shortage disrupts global supply chains for 6 months?",
        # cards=["supply-chain-disruption-detector", "crisis-simulation-planner"],  # optional: force specific agents
        on_step=on_step,
    )

    # --- 4. Process results ---
    print("\n" + "=" * 80)
    print("PREDICTION REPORT")
    print("=" * 80)
    print(f"\nQuery: {result.query}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Agents used: {len(result.agents_involved)}")

    if result.key_findings:
        print("\nKey Findings:")
        for i, finding in enumerate(result.key_findings, 1):
            print(f"  {i}. {finding}")

    if result.risk_factors:
        print("\nRisk Factors:")
        for risk in result.risk_factors:
            print(f"  - {risk}")

    if result.recommended_actions:
        print("\nRecommended Actions:")
        for action in result.recommended_actions:
            print(f"  - {action}")

    print(f"\nFull Report:\n{result.report}")

    # --- 5. Search context for follow-up ---
    follow_up = swarm.search_context("semiconductor supply chain impact")
    if follow_up:
        print("\nRelated context entries:")
        for entry in follow_up:
            print(f"  [{entry.score:.2f}] {entry.uri}")

    # --- 6. Clean up ---
    swarm.shutdown()


if __name__ == "__main__":
    main()
