# Agent Behavior Card Registry

**The Rosetta Stone for AI agent behaviors.**

Docker didn't invent containers — it invented a standard format for packaging and sharing them. The Agent Behavior Card (ABC) does the same thing for AI agent behaviors.

---

## The Problem

Everyone's building AI agents. Nobody's building the behavior description language — the metadata layer that makes them **composable** and **discoverable**.

Right now, if someone builds a great inventory optimization agent, there's no way to:

- **Describe** what it actually does in a machine-readable, portable way
- **Search** for it based on the problem pattern it solves, not the domain it was built for
- **Know** what needs to change when you move it to a new context

CrewAI lets you define agents. LangGraph lets you wire them. But none of them answer: *"Someone already solved a version of this problem in a different industry — how do I find it and adapt it?"*

**That discovery and translation layer is what this project builds.**

---

## What's an Agent Behavior Card?

Think of it as a **nutrition label for AI agent behaviors**. Just like you can pick up any food product anywhere in the world and read the same standardized label, an ABC creates a standardized description of:

- **What** the agent does (problem pattern, inputs, outputs)
- **How** it does it (reasoning method, objectives, composition)
- **What it assumes** (domain assumptions with hard/soft ratings)
- **Where it can be modified** (explicit adaptation points)
- **What can go wrong** (failure modes, ethical considerations)
- **Where it came from** (provenance and fork lineage)

### The Key Innovation: Problem Patterns

Instead of organizing behaviors by domain (retail, healthcare, logistics), ABCs organize by **abstract problem pattern**:

| Pattern | Description | Example Domains |
|---|---|---|
| `constrained-resource-allocation` | Distribute finite resources across competing needs | Inventory, aid, budgeting, energy |
| `anomaly-detection-and-response` | Identify outliers and trigger appropriate actions | Fraud, equipment failure, disease outbreak |
| `multi-stakeholder-negotiation` | Coordinate decisions across parties with different goals | Procurement, treaty negotiation, scheduling |
| `information-synthesis-and-routing` | Gather, summarize, and deliver info to right audience | News curation, intelligence briefing, triage |
| `sequential-decision-under-uncertainty` | Make chained decisions with incomplete information | Treatment planning, project management, trading |
| `compliance-and-constraint-checking` | Verify actions against rules and flag violations | Regulatory compliance, safety checks, QA |
| `adaptive-communication` | Tailor messaging to audience, language, and context | Customer support, field reporting, translation |
| `pattern-matching-and-classification` | Categorize inputs against known patterns | Diagnosis, damage assessment, document routing |

This means a crisis responder in Haiti can search *"constrained resource allocation"* and find behaviors built by retail companies, energy companies, and military logistics teams — then use the adaptation points to make it work for their context.

---

## Registry Contents

### Cards (25 behaviors across 8 pattern categories)

| # | Card | Pattern | Origin → Fork |
|---|---|---|---|
| 01 | [Inventory Rebalance Optimizer](cards/01-inventory-rebalance-optimizer.yaml) | `constrained-resource-allocation` | Retail → Humanitarian aid distribution |
| 02 | [Workforce Shift Scheduler](cards/02-workforce-shift-scheduler.yaml) | `constrained-resource-allocation` | Retail scheduling → Disaster volunteer coordination |
| 03 | [Budget Envelope Allocator](cards/03-budget-envelope-allocator.yaml) | `constrained-resource-allocation` | Marketing budget → Emergency fund distribution |
| 04 | [Fleet Route Optimizer](cards/04-fleet-route-optimizer.yaml) | `constrained-resource-allocation` | Delivery logistics → Humanitarian convoy routing |
| 05 | [Pattern Anomaly Detector](cards/05-pattern-anomaly-detector.yaml) | `anomaly-detection-and-response` | E-commerce fraud → Disease outbreak surveillance |
| 06 | [Equipment Health Monitor](cards/06-equipment-health-monitor.yaml) | `anomaly-detection-and-response` | Predictive maintenance → Post-disaster infrastructure assessment |
| 07 | [Supply Chain Disruption Detector](cards/07-supply-chain-disruption-detector.yaml) | `anomaly-detection-and-response` | Retail supply chain → Food security early warning |
| 08 | [Communication Triage & Router](cards/08-comms-triage-router.yaml) | `information-synthesis-and-routing` | Customer support → Crisis communication triage |
| 09 | [Regulatory Compliance Checker](cards/09-regulatory-compliance-checker.yaml) | `compliance-and-constraint-checking` | Financial AML/KYC → Humanitarian donor compliance |
| 10 | [Daily Intelligence Briefer](cards/10-daily-intelligence-briefer.yaml) | `information-synthesis-and-routing` | Competitive intelligence → Humanitarian sitrep generation |
| 11 | [Multi-Party Resource Negotiator](cards/11-multi-party-negotiator.yaml) | `multi-stakeholder-negotiation` | Supplier pricing → Humanitarian cluster coordination |
| 12 | [Patient Risk Stratifier](cards/12-patient-risk-stratifier.yaml) | `pattern-matching-and-classification` | Insurance risk scoring → Community health prioritization |
| 13 | [Environmental Impact Monitor](cards/13-environmental-impact-monitor.yaml) | `anomaly-detection-and-response` | Corporate ESG → Climate adaptation warning |
| 14 | [Safety Incident Predictor](cards/14-safety-incident-predictor.yaml) | `sequential-decision-under-uncertainty` | Workplace safety → Conflict escalation early warning |
| 15 | [Project Risk Cascade Planner](cards/15-project-risk-cascade-planner.yaml) | `sequential-decision-under-uncertainty` | Construction management → Disaster recovery planning |
| 16 | [Customer Journey Orchestrator](cards/16-customer-journey-orchestrator.yaml) | `sequential-decision-under-uncertainty` | E-commerce funnel → Refugee resettlement pathway |
| 17 | [Dynamic Pricing Engine](cards/17-dynamic-pricing-engine.yaml) | `sequential-decision-under-uncertainty` | E-commerce pricing → Humanitarian cash transfer optimization |
| 18 | [Travel Disruption Manager](cards/18-travel-disruption-manager.yaml) | `information-synthesis-and-routing` | Corporate travel → Mass displacement routing |
| 19 | [Adaptive Content Personalizer](cards/19-adaptive-content-personalizer.yaml) | `adaptive-communication` | Marketing personalization → Public health messaging |
| 20 | [Data Privacy Guardian](cards/20-data-privacy-guardian.yaml) | `compliance-and-constraint-checking` | GDPR compliance → Humanitarian beneficiary data protection |
| 21 | [Visual Damage Assessor](cards/21-visual-damage-assessor.yaml) | `pattern-matching-and-classification` | Insurance photo assessment → Satellite disaster assessment |
| 22 | [Document Intelligence Extractor](cards/22-document-intelligence-extractor.yaml) | `pattern-matching-and-classification` | Invoice processing → Humanitarian document processing |
| 23 | [Infrastructure Capacity Planner](cards/23-infrastructure-capacity-planner.yaml) | `constrained-resource-allocation` | Cloud auto-scaling → Refugee camp planning |
| 24 | [Sentiment & Feedback Analyzer](cards/24-sentiment-and-feedback-analyzer.yaml) | `information-synthesis-and-routing` | Brand sentiment → Community perception monitoring |
| 25 | [Crisis Simulation & Scenario Planner](cards/25-crisis-simulation-planner.yaml) | `sequential-decision-under-uncertainty` | Financial stress testing → Humanitarian contingency planning |

### Schema & Spec

- [`schema/abc-schema-v0.1.0.json`](schema/abc-schema-v0.1.0.json) — JSON Schema for validation
- [`spec/agent-behavior-card-spec.md`](spec/agent-behavior-card-spec.md) — Full specification document

---

## Quick Start

### Read a card

Each YAML file is self-documenting. Start with the `problem_pattern` section to understand what it solves, then look at `adaptation_points` to see where you can modify it.

### Validate a card

```bash
# Using ajv-cli
npm install -g ajv-cli
ajv validate -s schema/abc-schema-v0.1.0.json -d cards/01-inventory-rebalance-optimizer.yaml
```

### Write your own card

1. Pick the problem pattern that best describes your agent's behavior
2. Copy an existing card from the same pattern category as a template
3. Fill in your domain-specific details
4. Document your adaptation points — what can be swapped or configured?
5. Be honest about failure modes and limitations
6. Submit a PR

---

## Contributing

We want behavior cards from every domain. The whole point is cross-domain discovery.

### How to contribute

1. Fork this repo
2. Create your card in the `cards/` directory
3. Use the naming convention: `XX-descriptive-name.yaml`
4. Validate against the schema
5. Submit a PR with a brief description of the fork story (origin → adaptation)

### What makes a good card

- **At least one cross-domain fork story** — if your card only makes sense in one domain, it doesn't demonstrate the thesis
- **Honest failure modes** — this isn't marketing, it's engineering documentation
- **Specific adaptation points** — don't just say "this can be adapted," show exactly where and how
- **Real-world grounding** — based on actual behaviors, not hypothetical ones

### Card numbering

Numbers 01-25 are reserved for the initial registry seeding. Community contributions start at 26+.

---

## Roadmap

- [x] Define the ABC specification (v0.1.0)
- [x] Create JSON Schema for validation
- [x] Seed registry with 25 example cards
- [x] Build searchable registry website
- [x] Reach 25 cards across all 8 pattern categories
- [ ] Define the formal adaptation protocol
- [ ] Automated compatibility scoring
- [ ] Community-contributed cards
- [ ] Adaptation-as-a-Service pilot

---

## License

- **Specification & Schema:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Example Cards:** [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)

Use it, fork it, adapt it. That's the whole point.

---

**Built by [ABC Registry Contributors](https://github.com/abc-registry)** — Because one team's solution shouldn't die in a silo when it could save lives in a refugee camp six months later.
