# Contributing to the Agent Behavior Card Registry

Thanks for your interest in contributing. The whole thesis of this project is that agent behaviors become more valuable when they're shared across domains — so every contribution strengthens the ecosystem.

## How to Contribute a Behavior Card

### 1. Choose your behavior

Any AI agent behavior that solves a real problem. It doesn't need to be deployed in production — but it should be grounded in a real use case, not a hypothetical one.

### 2. Identify the problem pattern

Map your behavior to one of the 8 standard categories:

- `constrained-resource-allocation`
- `anomaly-detection-and-response`
- `multi-stakeholder-negotiation`
- `information-synthesis-and-routing`
- `sequential-decision-under-uncertainty`
- `compliance-and-constraint-checking`
- `adaptive-communication`
- `pattern-matching-and-classification`

If none fit, use `custom` and describe the pattern. If enough people submit the same custom pattern, we'll add it to the taxonomy.

### 3. Write the card

Use an existing card from `cards/` as your template. The schema is documented in `spec/agent-behavior-card-spec.md` and validated by `schema/abc-schema-v0.1.0.json`.

Every card must include:

- **At least one cross-domain analog** with a similarity score and notes
- **At least two adaptation points** showing where the behavior can be modified
- **Honest failure modes** — not marketing, engineering documentation
- **A fork story** — where did this behavior come from, and where else could it go?

### 4. Name your file

Format: `XX-descriptive-name.yaml`

- Numbers 01-25 are reserved for initial seeding
- Community contributions start at 26+

### 5. Validate

```bash
ajv validate -s schema/abc-schema-v0.1.0.json -d cards/your-card.yaml
```

### 6. Submit a PR

Include in your PR description:

- One-sentence summary of what the behavior does
- The fork story: origin domain → potential adaptation domain
- Why you think this pattern is portable across domains

## Improving Existing Cards

Found a gap in an existing card? Great:

- Add a new `analogous_domain` you've identified
- Improve an `adaptation_note` with practical experience
- Add a `failure_mode` you've encountered
- Suggest a new `adaptation_point`

## Proposing Schema Changes

The spec is v0.1.0 — it will evolve. If you think a field is missing or a structure should change:

1. Open an issue describing the gap
2. Show an example of what the change would look like in an actual card
3. Explain why the current schema can't handle your use case

## Code of Conduct

Be constructive. The goal is building something useful for both commercial and humanitarian builders. Treat every contributor's domain expertise with respect.
