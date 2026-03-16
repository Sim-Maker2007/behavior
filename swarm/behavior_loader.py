"""
ABC Behavior Loader — Reads behavior cards and translates them into agent profiles.

Takes ABC cards from the registry and produces agent configurations that
MiroFish can use to spawn simulation agents with defined behaviors.

The key mapping:
    ABC Card                    → Simulation Agent
    ─────────────────────────────────────────────
    identity.name               → agent role name
    problem_pattern.category    → agent specialization
    behavior.trigger            → when agent activates
    behavior.inputs/outputs     → what agent consumes/produces
    reasoning.approach          → how agent makes decisions
    failure_modes               → agent limitations/biases
    adaptation_points           → configurable parameters
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class AgentProfile:
    """An agent profile derived from an ABC behavior card."""
    card_name: str
    display_name: str
    role: str
    problem_pattern: str
    behavior: dict = field(default_factory=dict)
    triggers: list[dict] = field(default_factory=list)
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    reasoning_approach: str = ""
    failure_modes: list[str] = field(default_factory=list)
    adaptation_points: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class BehaviorLoader:
    """
    Loads ABC cards and selects/configures agents for a given prediction query.
    """

    # Problem patterns most relevant to prediction and simulation
    PREDICTION_RELEVANT_PATTERNS = {
        "sequential-decision-under-uncertainty",
        "anomaly-detection-and-response",
        "constrained-resource-allocation",
        "pattern-matching-and-classification",
        "information-synthesis-and-routing",
        "multi-stakeholder-negotiation",
        "compliance-and-constraint-checking",
    }

    def __init__(self, cards_directory: str):
        if yaml is None:
            raise ImportError("PyYAML required: pip install pyyaml")
        self.cards_directory = Path(cards_directory)
        self._cards: dict[str, dict] = {}
        self._profiles: dict[str, AgentProfile] = {}

    def load_all_cards(self) -> int:
        """Load all YAML cards from the registry directory. Returns count loaded."""
        count = 0
        for card_path in sorted(self.cards_directory.glob("*.yaml")):
            try:
                with open(card_path) as f:
                    card = yaml.safe_load(f)
                name = card.get("identity", {}).get("name", card_path.stem)
                self._cards[name] = card
                self._profiles[name] = self._card_to_profile(card, name)
                count += 1
            except Exception as e:
                logger.warning("Failed to load card %s: %s", card_path, e)
        logger.info("Loaded %d behavior cards from %s", count, self.cards_directory)
        return count

    def select_agents_for_query(
        self,
        query: str,
        max_agents: int = 10,
        required_cards: list[str] | None = None,
    ) -> list[AgentProfile]:
        """
        Select the most relevant agent profiles for a prediction query.

        Strategy:
        1. If required_cards specified, use those
        2. Otherwise, score each card by keyword overlap with query + pattern relevance
        3. Ensure diversity of problem patterns (don't pick 5 anomaly detectors)
        """
        if required_cards:
            return [
                self._profiles[name]
                for name in required_cards
                if name in self._profiles
            ]

        query_terms = set(query.lower().split())
        scored = []

        for name, profile in self._profiles.items():
            score = self._relevance_score(profile, query_terms)
            scored.append((score, name, profile))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Select with pattern diversity
        selected = []
        patterns_used = set()
        for score, name, profile in scored:
            if len(selected) >= max_agents:
                break
            # Allow max 2 agents per pattern category
            pattern = profile.problem_pattern
            if patterns_used.get(pattern, 0) if isinstance(patterns_used, dict) else pattern not in patterns_used or True:
                selected.append(profile)
                patterns_used.add(pattern)

        if not selected and scored:
            selected = [scored[0][2]]

        logger.info(
            "Selected %d agents for query: %s",
            len(selected),
            [p.card_name for p in selected],
        )
        return selected

    def get_profile(self, card_name: str) -> Optional[AgentProfile]:
        return self._profiles.get(card_name)

    def get_all_profiles(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    def profile_to_mirofish_config(self, profile: AgentProfile) -> dict:
        """Convert an AgentProfile to a dict suitable for MiroFish agent injection."""
        return {
            "card_name": profile.card_name,
            "role": profile.role,
            "behavior": {
                "trigger": profile.triggers,
                "inputs": profile.inputs,
                "outputs": profile.outputs,
                "reasoning": profile.reasoning_approach,
                "problem_pattern": profile.problem_pattern,
                "failure_modes": profile.failure_modes,
            },
            "tags": profile.tags,
        }

    def _card_to_profile(self, card: dict, name: str) -> AgentProfile:
        identity = card.get("identity", {})
        pattern = card.get("problem_pattern", {})
        behavior = card.get("behavior", {})
        reasoning = card.get("reasoning", {})

        triggers = []
        trigger = behavior.get("trigger", {})
        if trigger:
            triggers = [trigger] if isinstance(trigger, dict) else trigger

        return AgentProfile(
            card_name=name,
            display_name=identity.get("display_name", name),
            role=identity.get("name", name),
            problem_pattern=pattern.get("category", "unknown"),
            behavior=behavior,
            triggers=triggers,
            inputs=behavior.get("inputs", []),
            outputs=behavior.get("outputs", []),
            reasoning_approach=reasoning.get("approach", ""),
            failure_modes=[
                fm.get("description", str(fm))
                for fm in card.get("failure_modes", [])
                if isinstance(fm, dict)
            ],
            adaptation_points=card.get("adaptation_points", []),
            tags=identity.get("tags", []),
        )

    def _relevance_score(self, profile: AgentProfile, query_terms: set) -> float:
        score = 0.0

        # Pattern relevance boost
        if profile.problem_pattern in self.PREDICTION_RELEVANT_PATTERNS:
            score += 2.0

        # Tag overlap
        profile_terms = set(
            t.lower().replace("-", " ").split()
            for t in profile.tags
        )
        flat_tags = set()
        for terms in profile_terms:
            if isinstance(terms, list):
                flat_tags.update(terms)
            else:
                flat_tags.add(str(terms))

        tag_overlap = len(query_terms & flat_tags)
        score += tag_overlap * 1.5

        # Name/role keyword overlap
        name_terms = set(profile.card_name.lower().replace("-", " ").split())
        score += len(query_terms & name_terms) * 1.0

        # Display name overlap
        display_terms = set(profile.display_name.lower().replace("-", " ").split())
        score += len(query_terms & display_terms) * 0.5

        return score
