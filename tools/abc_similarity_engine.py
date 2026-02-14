"""
ABC Similarity Engine — Automated Cross-Domain Behavior Matching

Replaces subjective similarity scores with computed scores based on
multi-dimensional analysis of behavior cards.

The similarity score is NOT a single magic number. It's a composite
of multiple measurable dimensions, each capturing a different aspect
of how portable a behavior is across domains.

Usage:
    engine = ABCSimilarityEngine(anthropic_api_key="...")
    score = engine.compare(card_a, card_b)
    matches = engine.find_similar(card_a, registry)
"""

import json
import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# SIMILARITY DIMENSIONS
# =============================================================================
# Instead of one opaque number, we decompose similarity into measurable axes.
# Each dimension answers a specific question about portability.

@dataclass
class SimilarityBreakdown:
    """
    Multi-dimensional similarity score between two behavior cards.
    Each dimension is 0.0 to 1.0. The composite is a weighted combination.
    """

    # 1. Do they solve the same abstract problem?
    #    Computed by: LLM embedding cosine similarity of problem_pattern descriptions
    problem_pattern_similarity: float = 0.0

    # 2. Do they share the same sub-problem structure?
    #    Computed by: Jaccard similarity of sub_patterns lists
    sub_pattern_overlap: float = 0.0

    # 3. Are inputs/outputs structurally compatible?
    #    Computed by: Name + type matching of behavior.inputs and behavior.outputs
    io_structural_similarity: float = 0.0

    # 4. Do they use similar reasoning approaches?
    #    Computed by: LLM embedding similarity of reasoning.approach descriptions
    reasoning_similarity: float = 0.0

    # 5. How much adaptation is needed?
    #    Computed by: Ratio of assumptions that would need to change
    #    LOWER adaptation effort = HIGHER portability
    adaptation_portability: float = 0.0

    # 6. Are they composable in the same ecosystem?
    #    Computed by: Overlap in emitted/consumed events and delegate interfaces
    composition_compatibility: float = 0.0

    # The weights for the composite score
    # These are tunable — different registries might weight differently
    WEIGHTS = {
        "problem_pattern_similarity": 0.30,  # Most important: same problem?
        "sub_pattern_overlap": 0.15,
        "io_structural_similarity": 0.20,    # Can I actually plug it in?
        "reasoning_similarity": 0.10,
        "adaptation_portability": 0.15,      # How much work to fork?
        "composition_compatibility": 0.10,
    }

    @property
    def composite_score(self) -> float:
        """Weighted composite similarity score (0.0 to 1.0)."""
        total = 0.0
        for dim, weight in self.WEIGHTS.items():
            total += getattr(self, dim) * weight
        return round(total, 3)

    @property
    def explanation(self) -> str:
        """Human-readable explanation of the similarity score."""
        lines = [
            f"Composite Similarity: {self.composite_score:.2f}",
            f"",
            f"  Problem Pattern Match:     {self.problem_pattern_similarity:.2f}  "
            f"({'strong' if self.problem_pattern_similarity > 0.7 else 'moderate' if self.problem_pattern_similarity > 0.4 else 'weak'})",
            f"  Sub-Pattern Overlap:       {self.sub_pattern_overlap:.2f}  "
            f"({self._overlap_desc(self.sub_pattern_overlap)})",
            f"  I/O Structural Match:      {self.io_structural_similarity:.2f}  "
            f"({'compatible' if self.io_structural_similarity > 0.5 else 'needs adaptation'})",
            f"  Reasoning Approach:        {self.reasoning_similarity:.2f}  "
            f"({'similar' if self.reasoning_similarity > 0.6 else 'different'})",
            f"  Adaptation Portability:    {self.adaptation_portability:.2f}  "
            f"({'easy fork' if self.adaptation_portability > 0.7 else 'moderate effort' if self.adaptation_portability > 0.4 else 'significant rework'})",
            f"  Composition Compatibility: {self.composition_compatibility:.2f}  "
            f"({'plug-compatible' if self.composition_compatibility > 0.6 else 'needs integration work'})",
        ]
        return "\n".join(lines)

    @staticmethod
    def _overlap_desc(score):
        if score > 0.7:
            return "high overlap"
        elif score > 0.4:
            return "partial overlap"
        else:
            return "low overlap"

    def to_dict(self) -> dict:
        return {
            "composite_score": self.composite_score,
            "dimensions": {
                "problem_pattern_similarity": self.problem_pattern_similarity,
                "sub_pattern_overlap": self.sub_pattern_overlap,
                "io_structural_similarity": self.io_structural_similarity,
                "reasoning_similarity": self.reasoning_similarity,
                "adaptation_portability": self.adaptation_portability,
                "composition_compatibility": self.composition_compatibility,
            },
            "weights": self.WEIGHTS,
        }


# =============================================================================
# CARD PARSER
# =============================================================================

@dataclass
class ParsedCard:
    """Extracted fields from a behavior card relevant to similarity."""
    name: str = ""
    problem_category: str = ""
    problem_description: str = ""
    sub_patterns: list = field(default_factory=list)
    input_names: list = field(default_factory=list)
    input_types: list = field(default_factory=list)
    output_names: list = field(default_factory=list)
    output_types: list = field(default_factory=list)
    reasoning_method: str = ""
    reasoning_approach: str = ""
    objectives: list = field(default_factory=list)
    assumption_ids: list = field(default_factory=list)
    assumption_strengths: dict = field(default_factory=dict)
    adaptation_point_ids: list = field(default_factory=list)
    adaptation_point_types: dict = field(default_factory=dict)
    emitted_events: list = field(default_factory=list)
    consumed_events: list = field(default_factory=list)
    delegate_interfaces: list = field(default_factory=list)


def parse_card(card_data: dict) -> ParsedCard:
    """Parse a behavior card dict into fields for similarity computation."""
    parsed = ParsedCard()

    # Identity
    identity = card_data.get("identity", {})
    parsed.name = identity.get("name", "")

    # Problem pattern
    pp = card_data.get("problem_pattern", {})
    parsed.problem_category = pp.get("category", "")
    parsed.problem_description = pp.get("description", "")
    parsed.sub_patterns = pp.get("sub_patterns", [])

    # Behavior I/O
    behavior = card_data.get("behavior", {})
    for inp in behavior.get("inputs", []):
        parsed.input_names.append(inp.get("name", ""))
        parsed.input_types.append(inp.get("type", ""))
    for out in behavior.get("outputs", []):
        parsed.output_names.append(out.get("name", ""))
        parsed.output_types.append(out.get("type", ""))

    # Reasoning
    reasoning = behavior.get("reasoning", {})
    parsed.reasoning_method = reasoning.get("method", "")
    parsed.reasoning_approach = reasoning.get("approach", "")
    parsed.objectives = reasoning.get("objectives", [])

    # Domain assumptions
    assumptions = card_data.get("domain_assumptions", {})
    for category in ["data_assumptions", "environment_assumptions", "authority_assumptions"]:
        for assumption in assumptions.get(category, []):
            aid = assumption.get("id", "")
            parsed.assumption_ids.append(aid)
            parsed.assumption_strengths[aid] = assumption.get("strength", "soft")

    # Adaptation points
    for ap in card_data.get("adaptation_points", []):
        apid = ap.get("id", "")
        parsed.adaptation_point_ids.append(apid)
        parsed.adaptation_point_types[apid] = ap.get("type", "")

    # Composition
    composition = card_data.get("composition", {})
    for event in composition.get("emits", []):
        parsed.emitted_events.append(event.get("event", ""))
    for event in composition.get("listens_to", []):
        parsed.consumed_events.append(event.get("event", ""))
    for delegate in composition.get("delegates_to", []):
        parsed.delegate_interfaces.append(delegate.get("interface", ""))

    return parsed


# =============================================================================
# SIMILARITY COMPUTATIONS (Non-LLM dimensions)
# =============================================================================

def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard index between two sets."""
    if not set_a and not set_b:
        return 1.0  # Both empty = identical
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def normalized_token_overlap(list_a: list, list_b: list) -> float:
    """
    Token-level overlap between lists of strings.
    Splits each string into tokens and computes Jaccard on the token sets.
    More flexible than exact string matching.
    """
    def tokenize(strings):
        tokens = set()
        for s in strings:
            # Split on non-alphanumeric, lowercase
            words = re.findall(r'[a-z]+', s.lower())
            tokens.update(words)
        return tokens

    tokens_a = tokenize(list_a)
    tokens_b = tokenize(list_b)
    return jaccard_similarity(tokens_a, tokens_b)


def compute_sub_pattern_overlap(card_a: ParsedCard, card_b: ParsedCard) -> float:
    """Dimension 2: Sub-pattern structural overlap."""
    set_a = set(card_a.sub_patterns)
    set_b = set(card_b.sub_patterns)

    # Exact match Jaccard
    exact = jaccard_similarity(set_a, set_b)

    # Token-level similarity (catches partial matches like
    # "demand-forecasting-under-uncertainty" vs "forecasting-with-uncertainty")
    token = normalized_token_overlap(card_a.sub_patterns, card_b.sub_patterns)

    # Blend: weight token overlap higher since exact matches are rare across domains
    return round(0.4 * exact + 0.6 * token, 3)


def compute_io_similarity(card_a: ParsedCard, card_b: ParsedCard) -> float:
    """Dimension 3: Input/output structural compatibility."""
    # Compare input names (token overlap)
    input_name_sim = normalized_token_overlap(card_a.input_names, card_b.input_names)

    # Compare input types (token overlap)
    input_type_sim = normalized_token_overlap(card_a.input_types, card_b.input_types)

    # Compare output names
    output_name_sim = normalized_token_overlap(card_a.output_names, card_b.output_names)

    # Compare output types
    output_type_sim = normalized_token_overlap(card_a.output_types, card_b.output_types)

    # Count similarity (similar number of inputs/outputs suggests similar complexity)
    count_diff = abs(len(card_a.input_names) - len(card_b.input_names)) + \
                 abs(len(card_a.output_names) - len(card_b.output_names))
    max_count = max(len(card_a.input_names) + len(card_a.output_names),
                    len(card_b.input_names) + len(card_b.output_names), 1)
    count_sim = 1.0 - (count_diff / max_count)

    return round(
        0.25 * input_name_sim +
        0.15 * input_type_sim +
        0.25 * output_name_sim +
        0.15 * output_type_sim +
        0.20 * count_sim,
        3
    )


def compute_adaptation_portability(card_a: ParsedCard, card_b: ParsedCard) -> float:
    """
    Dimension 5: How much adaptation would be needed?

    Looks at the ratio of hard vs soft assumptions and the number/type
    of adaptation points. More swappable components = easier to port.
    """
    # What fraction of assumptions are "soft" (easier to adapt)?
    a_soft = sum(1 for s in card_a.assumption_strengths.values() if s == "soft")
    a_total = max(len(card_a.assumption_strengths), 1)
    a_softness = a_soft / a_total

    b_soft = sum(1 for s in card_b.assumption_strengths.values() if s == "soft")
    b_total = max(len(card_b.assumption_strengths), 1)
    b_softness = b_soft / b_total

    # Average softness — higher = more portable
    avg_softness = (a_softness + b_softness) / 2

    # What fraction of adaptation points are swappable (vs just configurable)?
    a_swappable = sum(1 for t in card_a.adaptation_point_types.values()
                      if t == "swappable_component")
    a_ap_total = max(len(card_a.adaptation_point_types), 1)

    b_swappable = sum(1 for t in card_b.adaptation_point_types.values()
                      if t == "swappable_component")
    b_ap_total = max(len(card_b.adaptation_point_types), 1)

    swappability = ((a_swappable / a_ap_total) + (b_swappable / b_ap_total)) / 2

    # More adaptation points = more designed-for-portability
    ap_count_score = min((len(card_a.adaptation_point_ids) +
                          len(card_b.adaptation_point_ids)) / 8, 1.0)

    return round(
        0.35 * avg_softness +
        0.40 * swappability +
        0.25 * ap_count_score,
        3
    )


def compute_composition_compatibility(card_a: ParsedCard, card_b: ParsedCard) -> float:
    """Dimension 6: Can they plug into the same ecosystem?"""
    # Event overlap (do they speak the same event language?)
    all_events_a = set(card_a.emitted_events + card_a.consumed_events)
    all_events_b = set(card_b.emitted_events + card_b.consumed_events)
    event_overlap = normalized_token_overlap(list(all_events_a), list(all_events_b))

    # Do they emit events the other consumes? (direct composability)
    a_emits = set(card_a.emitted_events)
    b_consumes = set(card_b.consumed_events)
    b_emits = set(card_b.emitted_events)
    a_consumes = set(card_a.consumed_events)

    direct_a_to_b = len(a_emits & b_consumes) / max(len(b_consumes), 1)
    direct_b_to_a = len(b_emits & a_consumes) / max(len(a_consumes), 1)
    direct_composability = max(direct_a_to_b, direct_b_to_a)

    # Delegate interface overlap
    interface_overlap = normalized_token_overlap(
        card_a.delegate_interfaces, card_b.delegate_interfaces
    )

    return round(
        0.40 * event_overlap +
        0.35 * direct_composability +
        0.25 * interface_overlap,
        3
    )


# =============================================================================
# LLM-POWERED DIMENSIONS (using Claude API)
# =============================================================================

async def compute_llm_similarity(text_a: str, text_b: str, dimension: str,
                                  api_key: Optional[str] = None) -> float:
    """
    Use Claude to compute semantic similarity between two text descriptions.

    Instead of embeddings (which require a separate embedding model),
    we ask Claude directly to assess similarity on a specific dimension.
    This is more interpretable and doesn't require managing embedding infra.
    """
    if not api_key:
        # Fallback to token overlap when no API key
        tokens_a = set(re.findall(r'[a-z]+', text_a.lower()))
        tokens_b = set(re.findall(r'[a-z]+', text_b.lower()))
        return round(jaccard_similarity(tokens_a, tokens_b), 3)

    import httpx

    prompt = f"""You are an expert in AI agent behavior analysis. Score the semantic similarity between these two descriptions on a scale of 0.00 to 1.00.

Dimension being scored: {dimension}

Description A:
{text_a}

Description B:
{text_b}

Scoring guide:
- 0.90-1.00: Nearly identical problem/approach, just different terminology
- 0.70-0.89: Same core pattern, meaningful structural differences
- 0.50-0.69: Related patterns with significant differences
- 0.30-0.49: Loosely related, some shared sub-problems
- 0.00-0.29: Fundamentally different problems/approaches

Respond with ONLY a JSON object: {{"score": 0.XX, "reasoning": "one sentence"}}"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30.0,
            )
            data = response.json()
            text = data["content"][0]["text"]
            result = json.loads(text)
            return round(float(result["score"]), 3)
    except Exception as e:
        print(f"LLM similarity failed ({e}), falling back to token overlap")
        tokens_a = set(re.findall(r'[a-z]+', text_a.lower()))
        tokens_b = set(re.findall(r'[a-z]+', text_b.lower()))
        return round(jaccard_similarity(tokens_a, tokens_b), 3)


# =============================================================================
# MAIN ENGINE
# =============================================================================

class ABCSimilarityEngine:
    """
    Computes multi-dimensional similarity between behavior cards.

    Can operate in two modes:
    - Offline mode (no API key): Uses token overlap for text dimensions
    - Online mode (with API key): Uses Claude for semantic similarity
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def compare_async(self, card_a: dict, card_b: dict) -> SimilarityBreakdown:
        """Compare two behavior cards and return detailed similarity breakdown."""
        a = parse_card(card_a)
        b = parse_card(card_b)

        breakdown = SimilarityBreakdown()

        # Dimension 1: Problem pattern (LLM-powered)
        breakdown.problem_pattern_similarity = await compute_llm_similarity(
            f"Category: {a.problem_category}\n{a.problem_description}",
            f"Category: {b.problem_category}\n{b.problem_description}",
            "abstract problem pattern similarity (ignore domain, focus on the underlying computational/logical pattern)",
            self.api_key
        )

        # Dimension 2: Sub-pattern overlap (computed)
        breakdown.sub_pattern_overlap = compute_sub_pattern_overlap(a, b)

        # Dimension 3: I/O structural similarity (computed)
        breakdown.io_structural_similarity = compute_io_similarity(a, b)

        # Dimension 4: Reasoning approach (LLM-powered)
        reasoning_a = f"{a.reasoning_method}: {a.reasoning_approach}"
        reasoning_b = f"{b.reasoning_method}: {b.reasoning_approach}"
        breakdown.reasoning_similarity = await compute_llm_similarity(
            reasoning_a, reasoning_b,
            "reasoning methodology similarity (do they use similar decision-making approaches?)",
            self.api_key
        )

        # Dimension 5: Adaptation portability (computed)
        breakdown.adaptation_portability = compute_adaptation_portability(a, b)

        # Dimension 6: Composition compatibility (computed)
        breakdown.composition_compatibility = compute_composition_compatibility(a, b)

        return breakdown

    def compare(self, card_a: dict, card_b: dict) -> SimilarityBreakdown:
        """Synchronous wrapper for compare_async."""
        return asyncio.run(self.compare_async(card_a, card_b))

    async def find_similar_async(self, card: dict, registry: list[dict],
                                  min_score: float = 0.3,
                                  max_results: int = 10) -> list[dict]:
        """Find similar behaviors in a registry."""
        results = []
        for candidate in registry:
            if candidate.get("identity", {}).get("name") == \
               card.get("identity", {}).get("name"):
                continue  # Skip self

            breakdown = await self.compare_async(card, candidate)
            if breakdown.composite_score >= min_score:
                results.append({
                    "card": candidate.get("identity", {}).get("name", "unknown"),
                    "display_name": candidate.get("identity", {}).get("display_name", ""),
                    "score": breakdown.composite_score,
                    "breakdown": breakdown.to_dict(),
                    "explanation": breakdown.explanation,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]

    def find_similar(self, card: dict, registry: list[dict],
                     min_score: float = 0.3,
                     max_results: int = 10) -> list[dict]:
        """Synchronous wrapper for find_similar_async."""
        return asyncio.run(self.find_similar_async(card, registry, min_score, max_results))


# =============================================================================
# DEMO: Run similarity on our existing cards
# =============================================================================

if __name__ == "__main__":
    import yaml
    import glob
    import os

    print("=" * 60)
    print("ABC Similarity Engine — Demo")
    print("=" * 60)
    print()

    # Load all cards
    card_dir = os.path.join(os.path.dirname(__file__), "cards")
    if not os.path.isdir(card_dir):
        card_dir = "/home/claude/abc-registry-v0.1.0/cards"

    cards = {}
    for filepath in sorted(glob.glob(os.path.join(card_dir, "*.yaml"))):
        with open(filepath) as f:
            try:
                card = yaml.safe_load(f)
                name = card.get("identity", {}).get("name", os.path.basename(filepath))
                cards[name] = card
            except Exception as e:
                print(f"  Skipping {filepath}: {e}")

    print(f"Loaded {len(cards)} cards")
    print()

    # Run in offline mode (no API key needed for demo)
    engine = ABCSimilarityEngine(api_key=None)

    # Compare specific pairs to show the engine working
    test_pairs = [
        # Same category — should be high similarity
        ("inventory-rebalance-optimizer", "budget-envelope-allocator"),
        # Same category but different — moderate similarity
        ("pattern-anomaly-detector", "supply-chain-disruption-detector"),
        # Different category — should be lower but non-zero
        ("comms-triage-router", "data-privacy-gate"),
        # Very different — should be low
        ("workforce-shift-scheduler", "visual-damage-assessor"),
    ]

    # Also try all-vs-all for cards that exist
    available_names = list(cards.keys())
    print(f"Available cards: {available_names}")
    print()

    # Compare all pairs
    print("=" * 60)
    print("PAIRWISE SIMILARITY MATRIX")
    print("=" * 60)
    print()

    compared = set()
    results = []

    for name_a in available_names:
        for name_b in available_names:
            if name_a >= name_b:
                continue
            pair_key = (name_a, name_b)
            if pair_key in compared:
                continue
            compared.add(pair_key)

            breakdown = engine.compare(cards[name_a], cards[name_b])
            results.append((name_a, name_b, breakdown))

    # Sort by composite score
    results.sort(key=lambda x: x[2].composite_score, reverse=True)

    print(f"{'Card A':<35} {'Card B':<35} {'Score':>6}  {'Pattern':>7}  {'I/O':>5}  {'Port':>5}")
    print("-" * 100)
    for name_a, name_b, breakdown in results:
        short_a = name_a[:33]
        short_b = name_b[:33]
        print(
            f"{short_a:<35} {short_b:<35} "
            f"{breakdown.composite_score:>5.2f}  "
            f"{breakdown.problem_pattern_similarity:>6.2f}  "
            f"{breakdown.io_structural_similarity:>5.2f}  "
            f"{breakdown.adaptation_portability:>5.2f}"
        )

    # Show detailed breakdown for the top match
    if results:
        print()
        print("=" * 60)
        print(f"DETAILED: Top match")
        print("=" * 60)
        top = results[0]
        print(f"\n{top[0]}  ↔  {top[1]}\n")
        print(top[2].explanation)
