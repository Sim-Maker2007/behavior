# Agent Behavior Card (ABC) Specification

## Version 0.1.0 — Draft

**Author:** ABC Registry Contributors
**Date:** February 2026
**Status:** Draft for community feedback

---

## 1. What is an Agent Behavior Card?

An Agent Behavior Card (ABC) is a standardized metadata document that describes **what an AI agent behavior does, how it does it, and what needs to change when you move it to a new domain.**

Think of it as:
- A **Model Card** (à la Mitchell et al., 2019) — but for agent *behaviors*, not model weights
- A **Dockerfile** — but instead of packaging software environments, it packages decision-making patterns
- A **README + API spec + migration guide** rolled into one

ABCs exist to solve a specific problem: right now, agent behaviors are locked inside the projects that created them. There's no way to discover that someone already solved your problem in a different industry, and no structured way to adapt their solution to your context.

---

## 2. Design Principles

1. **Problem-pattern first, not domain first.** An ABC describes the abstract problem being solved (e.g., "constrained resource allocation under uncertainty") before the specific domain (e.g., "warehouse inventory management").

2. **Adaptation points are explicit.** Every ABC clearly marks what assumptions are baked in and what needs to change for a new context. This is the most important and novel part of the spec.

3. **Machine-readable, human-understandable.** The schema is JSON/YAML for tooling, but every field has a plain-language purpose.

4. **Composability over completeness.** ABCs describe behaviors that can be combined, not monolithic agents. A single agent might implement multiple behavior cards.

5. **Trust through transparency.** ABCs include failure modes, known limitations, and ethical considerations — not just capabilities.

---

## 3. The Schema

### 3.1 Core Identity

```yaml
abc_version: "0.1.0"

identity:
  name: "inventory-rebalance-optimizer"
  display_name: "Inventory Rebalance Optimizer"
  version: "1.2.0"
  authors:
    - name: "ABC Contributors"
      org: "ABC Registry"
      contact: "hello@abcregistry.org"
  license: "Apache-2.0"
  created: "2026-02-13"
  updated: "2026-02-13"
  tags: ["optimization", "resource-allocation", "logistics"]
```

### 3.2 Problem Pattern

This is the key innovation — describing the *abstract pattern* the behavior addresses, independent of domain.

```yaml
problem_pattern:
  # The abstract class of problem this behavior solves
  category: "constrained-resource-allocation"

  # Plain language description of what this behavior does
  description: >
    Allocates finite resources across multiple locations to minimize
    stockouts while respecting budget constraints, lead times, and
    demand uncertainty.

  # The universal sub-problems this behavior addresses
  sub_patterns:
    - "demand-forecasting-under-uncertainty"
    - "multi-location-balancing"
    - "constraint-satisfaction"

  # Known analogous domains where this pattern applies
  analogous_domains:
    - domain: "humanitarian-aid-distribution"
      similarity: 0.82
      notes: >
        Medical supply allocation to field hospitals maps closely.
        Key difference: demand signals are weaker and more volatile.
    - domain: "energy-grid-balancing"
      similarity: 0.65
      notes: >
        Similar constraint structure but time horizons differ significantly.
        Energy requires sub-second decisions vs. daily/weekly for inventory.
```

### 3.3 Behavior Specification

```yaml
behavior:
  # What triggers this behavior
  trigger:
    type: "scheduled"  # or "event-driven", "continuous", "on-demand"
    conditions:
      - "daily at 06:00 UTC"
      - "on inventory_threshold_breach event"

  # What this behavior needs to function
  inputs:
    - name: "current_stock_levels"
      type: "map<location_id, map<item_id, quantity>>"
      required: true
      description: "Current inventory at each location"
      freshness: "< 4 hours"

    - name: "demand_signals"
      type: "map<location_id, map<item_id, forecast>>"
      required: true
      description: "Demand forecast per location per item"
      freshness: "< 24 hours"

    - name: "transfer_constraints"
      type: "constraint_set"
      required: true
      description: "Cost, time, and capacity limits on transfers"

    - name: "budget_envelope"
      type: "currency_amount"
      required: false
      description: "Maximum spend on transfers this cycle"
      default_behavior: "unconstrained"

  # What this behavior produces
  outputs:
    - name: "transfer_plan"
      type: "list<transfer_order>"
      description: "Ordered list of recommended transfers"
      confidence_included: true

    - name: "risk_assessment"
      type: "risk_report"
      description: "Projected stockout risks post-transfer"

    - name: "explanation"
      type: "natural_language"
      description: "Human-readable rationale for the plan"

  # Decision-making approach
  reasoning:
    method: "multi-objective-optimization"
    objectives:
      - "minimize projected stockouts (weight: 0.6)"
      - "minimize transfer cost (weight: 0.3)"
      - "minimize transfer complexity (weight: 0.1)"
    approach: >
      Uses rolling demand forecast with Monte Carlo uncertainty
      sampling, then applies constrained optimization to find
      Pareto-optimal transfer plans.
```

### 3.4 Domain Assumptions (Critical Section)

This is where portability lives or dies. Every assumption that's baked into the behavior must be surfaced.

```yaml
domain_assumptions:
  # Assumptions about the data environment
  data_assumptions:
    - id: "DA-001"
      assumption: "Demand follows seasonal patterns with historical data available"
      strength: "hard"  # hard = behavior breaks without this, soft = degrades gracefully
      adaptation_note: >
        In crisis/humanitarian contexts, demand is shock-driven not seasonal.
        Replace seasonal model with surge detection + needs assessment feeds.

    - id: "DA-002"
      assumption: "Inventory data is digitized and updated within 4 hours"
      strength: "hard"
      adaptation_note: >
        Many humanitarian warehouses use manual tracking. Requires either
        digitization step or tolerance for 24-48h data latency.

    - id: "DA-003"
      assumption: "Item taxonomy is stable and well-defined"
      strength: "soft"
      adaptation_note: >
        Aid supply taxonomies vary by organization. Map to standard
        humanitarian clusters (WASH, Shelter, Health, etc.)

  # Assumptions about the operating environment
  environment_assumptions:
    - id: "EA-001"
      assumption: "Transfer routes are known and relatively stable"
      strength: "hard"
      adaptation_note: >
        In crisis zones, routes change daily. Requires integration with
        real-time logistics/access data (e.g., OCHA access maps).

    - id: "EA-002"
      assumption: "Single currency, stable pricing"
      strength: "soft"
      adaptation_note: >
        Multi-currency and volatile pricing in global humanitarian ops.
        Add currency normalization layer.

  # Assumptions about decision authority
  authority_assumptions:
    - id: "AA-001"
      assumption: "Agent can recommend but human approves transfers over $10K"
      strength: "hard"
      adaptation_note: >
        Humanitarian contexts often require cluster-level coordination
        approval. Expand approval workflow to multi-stakeholder.

    - id: "AA-002"
      assumption: "Single organization controls all inventory"
      strength: "hard"
      adaptation_note: >
        Humanitarian supply chains involve multiple orgs (UN, NGOs, govts).
        Requires federated inventory visibility without full data sharing.
```

### 3.5 Adaptation Points

Explicit hooks where the behavior is designed to be modified.

```yaml
adaptation_points:
  - id: "AP-001"
    name: "demand_model"
    type: "swappable_component"
    current: "seasonal_arima_forecast"
    interface: "DemandPredictor"
    description: >
      The demand forecasting component. Swap for domain-appropriate
      forecasting. Interface requires: predict(location, item, horizon) → forecast
    suggested_alternatives:
      - name: "crisis_surge_detector"
        for_domain: "humanitarian"
        description: "Uses news feeds, displacement data, and epidemiological signals"
      - name: "weather_demand_model"
        for_domain: "agriculture"
        description: "Uses weather forecasts and crop cycle data"

  - id: "AP-002"
    name: "constraint_solver"
    type: "configurable"
    parameters:
      - name: "optimization_horizon"
        current: "7 days"
        range: "1 hour — 90 days"
      - name: "objective_weights"
        current: { stockout: 0.6, cost: 0.3, complexity: 0.1 }
        notes: "In humanitarian contexts, weight stockout much higher (0.9+)"

  - id: "AP-003"
    name: "explanation_language"
    type: "swappable_component"
    current: "english_business_report"
    interface: "ExplanationGenerator"
    description: >
      Generates human-readable explanations. Swap for multilingual
      support or different audience levels (field worker vs. HQ).
    suggested_alternatives:
      - name: "multilingual_field_report"
        for_domain: "humanitarian"
        description: "Generates explanations in local languages using Tarjimly-style translation"
```

### 3.6 Composition Interface

How this behavior connects with other agent behaviors.

```yaml
composition:
  # What this behavior can delegate to
  delegates_to:
    - behavior: "route-optimizer"
      interface: "RouteOptimizer"
      purpose: "Optimizes physical transfer routes once plan is decided"
      required: false

    - behavior: "anomaly-detector"
      interface: "AnomalyDetector"
      purpose: "Flags unusual demand patterns before optimization runs"
      required: false

  # What can orchestrate this behavior
  orchestrated_by:
    - pattern: "supply-chain-coordinator"
      role: "Calls this behavior as part of daily supply chain cycle"

  # Events this behavior emits
  emits:
    - event: "transfer_plan_ready"
      payload: "transfer_plan"
      description: "Emitted when a new plan is generated"

    - event: "stockout_risk_critical"
      payload: "risk_assessment"
      description: "Emitted when projected stockout exceeds threshold"

  # Events this behavior listens to
  listens_to:
    - event: "inventory_updated"
      source: "inventory-tracker"
      action: "Refreshes current stock data"

    - event: "demand_spike_detected"
      source: "anomaly-detector"
      action: "Triggers immediate re-optimization"
```

### 3.7 Trust & Safety

```yaml
trust:
  # Known failure modes
  failure_modes:
    - id: "FM-001"
      scenario: "Stale inventory data (>24h)"
      impact: "Transfer plan based on wrong stock levels"
      severity: "high"
      mitigation: "Staleness check on inputs; refuse to plan if data too old"

    - id: "FM-002"
      scenario: "Demand forecast completely wrong (black swan)"
      impact: "Suboptimal allocation, potential stockouts"
      severity: "medium"
      mitigation: "Safety stock buffers; human review of large transfers"

    - id: "FM-003"
      scenario: "Optimization suggests concentrating resources in few locations"
      impact: "Equity concerns — some locations get nothing"
      severity: "high_in_humanitarian"
      mitigation: "Minimum allocation constraints per location"

  # Ethical considerations
  ethical_flags:
    - context: "humanitarian"
      concern: "Optimization without equity constraints can deprioritize hard-to-reach populations"
      recommendation: "Add minimum service level per location regardless of cost efficiency"

    - context: "humanitarian"
      concern: "Automated decisions about aid allocation carry life-or-death weight"
      recommendation: "Mandatory human-in-the-loop for all final decisions; agent recommends only"

  # Performance expectations
  performance:
    tested_scale: "50 locations, 500 SKUs, 7-day horizon"
    latency: "< 30 seconds for full optimization"
    accuracy: "Demand forecast MAPE < 15% on seasonal data"
    known_degradation: "Accuracy drops significantly with < 6 months historical data"

  # Audit trail
  observability:
    logging: "All inputs, outputs, and decision rationale logged"
    explainability: "Natural language explanation generated for every plan"
    reproducibility: "Given same inputs and random seed, produces identical output"
```

### 3.8 Provenance & Lineage

```yaml
provenance:
  # Where this behavior came from
  origin:
    domain: "retail"
    organization: "RetailCo"
    original_use_case: "Rebalancing seasonal consumer goods across multiple store locations"

  # Fork/adaptation history
  lineage:
    - version: "1.0.0"
      domain: "retail"
      date: "2026-01-15"
      notes: "Original implementation for retail stores"

    - version: "1.1.0"
      domain: "retail"
      date: "2026-02-01"
      notes: "Added weather-adjusted demand forecasting"
      adaptation_points_changed: ["AP-001"]

    - version: "1.2.0"
      domain: "humanitarian-aid"
      date: "2026-02-13"
      notes: "Forked for humanitarian supply chain pilot"
      adaptation_points_changed: ["AP-001", "AP-002", "AP-003"]
      assumptions_changed: ["DA-001", "DA-002", "EA-001", "AA-002"]

  # Compatibility
  compatibility:
    frameworks:
      - name: "CrewAI"
        version: ">=0.28"
        integration: "CrewAI Tool wrapper available"
      - name: "LangGraph"
        version: ">=0.1"
        integration: "LangGraph node implementation available"
      - name: "AutoGen"
        version: ">=0.2"
        integration: "AutoGen skill registration"
```

---

## 4. Schema Taxonomy — Problem Pattern Categories

A starting vocabulary for categorizing agent behaviors by abstract problem pattern:

| Category | Description | Example Domains |
|---|---|---|
| `constrained-resource-allocation` | Distribute finite resources across competing needs | Inventory, aid, budgeting, energy |
| `anomaly-detection-and-response` | Identify outliers and trigger appropriate actions | Fraud, equipment failure, disease outbreak |
| `multi-stakeholder-negotiation` | Coordinate decisions across parties with different goals | Procurement, treaty negotiation, scheduling |
| `information-synthesis-and-routing` | Gather, summarize, and deliver info to right audience | News curation, intelligence briefing, triage |
| `sequential-decision-under-uncertainty` | Make chained decisions with incomplete information | Treatment planning, project management, trading |
| `compliance-and-constraint-checking` | Verify actions against rules and flag violations | Regulatory compliance, safety checks, quality assurance |
| `adaptive-communication` | Tailor messaging to audience, language, and context | Customer support, field reporting, translation |
| `pattern-matching-and-classification` | Categorize inputs against known patterns | Diagnosis, damage assessment, document routing |

---

## 5. Discovery — How ABCs Enable Search

With standardized behavior cards, a registry can support queries like:

- *"Show me all behaviors that solve `constrained-resource-allocation` problems"*
- *"Find behaviors originally built for retail that have been adapted to humanitarian contexts"*
- *"Which behaviors have `swappable_component` adaptation points for demand forecasting?"*
- *"Show me behaviors compatible with CrewAI that handle multi-stakeholder coordination"*

This turns agent behaviors from isolated code into a **searchable, composable ecosystem.**

---

## 6. What's Next

1. **Validate the schema** — Publish this spec, get feedback from agent builders
2. **Create 5-10 example ABCs** — Seed with real behaviors across domains
3. **Build a simple registry** — GitHub repo or lightweight web app for discovery
4. **Define the adaptation protocol** — Formalize the process of forking + adapting a behavior card
5. **Explore automated compatibility scoring** — Can an LLM read two ABCs and estimate adaptation effort?

---

## License

This specification is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Use it, fork it, adapt it.
