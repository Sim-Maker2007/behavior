#!/usr/bin/env python3
"""
abc-check — ABC Compliance Verification CLI

Validates Agent Behavior Cards and scores implementation compliance
against the ABC specification.

Usage:
    python abc_check.py ./my-behavior/           # Full project check
    python abc_check.py ./abc-card.yaml --card    # Card-only validation
    python abc_check.py ./my-behavior/ --json     # JSON output
    python abc_check.py ./my-behavior/ --fix      # Show fix suggestions

Exit codes:
    0 = Certified (90+)
    1 = Compatible (70-89)
    2 = Aspirational (50-69)
    3 = Non-compliant (<50)
    4 = Error (invalid input)
"""

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml")
    sys.exit(4)


# =============================================================================
# COLORS & FORMATTING
# =============================================================================

class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    @staticmethod
    def disable():
        for attr in ['RESET', 'BOLD', 'DIM', 'RED', 'GREEN', 'YELLOW',
                      'BLUE', 'CYAN', 'WHITE']:
            setattr(Colors, attr, '')


def icon(passed: bool) -> str:
    return f"{Colors.GREEN}✅{Colors.RESET}" if passed else f"{Colors.RED}❌{Colors.RESET}"


def warn_icon() -> str:
    return f"{Colors.YELLOW}⚠️{Colors.RESET}"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CheckResult:
    name: str
    passed: bool
    points_earned: float
    points_possible: float
    details: str = ""
    fix_suggestion: str = ""
    sub_checks: list = field(default_factory=list)


@dataclass
class SubCheck:
    item: str
    passed: bool
    detail: str = ""


@dataclass
class ComplianceReport:
    card_name: str = ""
    card_version: str = ""
    spec_version: str = "0.1.0"
    project_path: str = ""
    card_path: str = ""

    # Scores
    card_validation_score: float = 0
    implementation_score: float = 0
    trust_score: float = 0
    overall_score: float = 0

    # Detailed results
    card_checks: list = field(default_factory=list)
    implementation_checks: list = field(default_factory=list)
    trust_checks: list = field(default_factory=list)

    # Summary
    level: str = ""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "card_name": self.card_name,
            "card_version": self.card_version,
            "spec_version": self.spec_version,
            "project_path": self.project_path,
            "scores": {
                "card_validation": round(self.card_validation_score, 1),
                "implementation": round(self.implementation_score, 1),
                "trust": round(self.trust_score, 1),
                "overall": round(self.overall_score, 1),
            },
            "level": self.level,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "checks": {
                "card": [self._check_to_dict(c) for c in self.card_checks],
                "implementation": [self._check_to_dict(c) for c in self.implementation_checks],
                "trust": [self._check_to_dict(c) for c in self.trust_checks],
            }
        }

    @staticmethod
    def _check_to_dict(check: CheckResult) -> dict:
        return {
            "name": check.name,
            "passed": check.passed,
            "points_earned": check.points_earned,
            "points_possible": check.points_possible,
            "details": check.details,
            "sub_checks": [
                {"item": s.item, "passed": s.passed, "detail": s.detail}
                for s in check.sub_checks
            ]
        }


# =============================================================================
# CARD VALIDATION
# =============================================================================

REQUIRED_TOP_LEVEL = ["abc_version", "identity", "problem_pattern", "behavior",
                       "domain_assumptions", "adaptation_points", "trust"]

REQUIRED_IDENTITY = ["name", "display_name", "version", "authors", "created"]
REQUIRED_PROBLEM_PATTERN = ["category", "description"]
REQUIRED_BEHAVIOR = ["trigger", "inputs", "outputs"]
REQUIRED_TRIGGER = ["type"]
REQUIRED_INPUT = ["name", "type", "description"]
REQUIRED_OUTPUT = ["name", "type", "description"]

VALID_CATEGORIES = [
    "constrained-resource-allocation",
    "anomaly-detection-and-response",
    "multi-stakeholder-negotiation",
    "information-synthesis-and-routing",
    "sequential-decision-under-uncertainty",
    "compliance-and-constraint-checking",
    "adaptive-communication",
    "pattern-matching-and-classification",
    "custom"
]

VALID_TRIGGER_TYPES = ["scheduled", "event-driven", "continuous", "on-demand"]
VALID_AP_TYPES = ["swappable_component", "configurable", "extensible"]
VALID_ASSUMPTION_STRENGTHS = ["hard", "soft"]
VALID_SEVERITIES = ["low", "medium", "high", "critical", "high_in_humanitarian"]

FAILURE_CATEGORIES = ["INPUT", "MODEL", "INTEGRATION", "SCALE",
                       "DOMAIN", "HUMAN", "SECURITY", "ETHICAL"]


def validate_card(card: dict) -> list[CheckResult]:
    """Validate a behavior card against the ABC schema."""
    checks = []

    # 1. Required top-level sections
    missing = [k for k in REQUIRED_TOP_LEVEL if k not in card]
    checks.append(CheckResult(
        name="Required top-level sections",
        passed=len(missing) == 0,
        points_earned=10 if len(missing) == 0 else max(0, 10 - len(missing) * 2),
        points_possible=10,
        details=f"Missing: {', '.join(missing)}" if missing else "All 7 required sections present",
        fix_suggestion=f"Add missing sections: {', '.join(missing)}" if missing else "",
        sub_checks=[
            SubCheck(item=k, passed=k in card, detail="present" if k in card else "MISSING")
            for k in REQUIRED_TOP_LEVEL
        ]
    ))

    # 2. Identity validation
    identity = card.get("identity", {})
    id_missing = [k for k in REQUIRED_IDENTITY if k not in identity]
    name_valid = bool(re.match(r'^[a-z0-9-]+$', identity.get("name", "")))
    version_valid = bool(re.match(r'^\d+\.\d+\.\d+$', identity.get("version", "")))

    id_subs = [
        SubCheck("required fields", len(id_missing) == 0,
                 f"Missing: {id_missing}" if id_missing else "all present"),
        SubCheck("name format (kebab-case)", name_valid,
                 identity.get("name", "(empty)")),
        SubCheck("version format (semver)", version_valid,
                 identity.get("version", "(empty)")),
    ]
    id_score = sum(1 for s in id_subs if s.passed) / len(id_subs) * 10
    checks.append(CheckResult(
        name="Identity section",
        passed=all(s.passed for s in id_subs),
        points_earned=round(id_score, 1),
        points_possible=10,
        sub_checks=id_subs,
    ))

    # 3. Problem pattern validation
    pp = card.get("problem_pattern", {})
    pp_missing = [k for k in REQUIRED_PROBLEM_PATTERN if k not in pp]
    category_valid = pp.get("category", "") in VALID_CATEGORIES
    has_sub_patterns = len(pp.get("sub_patterns", [])) > 0
    has_analogous = len(pp.get("analogous_domains", [])) > 0

    # Check analogous domains have similarity scores
    analogous = pp.get("analogous_domains", [])
    analogous_valid = all(
        "domain" in a and "similarity" in a and
        isinstance(a.get("similarity"), (int, float)) and
        0 <= a.get("similarity", -1) <= 1
        for a in analogous
    )

    pp_subs = [
        SubCheck("required fields", len(pp_missing) == 0,
                 f"Missing: {pp_missing}" if pp_missing else "present"),
        SubCheck("valid category", category_valid,
                 pp.get("category", "(empty)")),
        SubCheck("has sub_patterns", has_sub_patterns,
                 f"{len(pp.get('sub_patterns', []))} defined"),
        SubCheck("has analogous_domains", has_analogous,
                 f"{len(analogous)} defined"),
        SubCheck("analogous domains well-formed", analogous_valid or not analogous,
                 "all have domain + similarity (0-1)" if analogous_valid else "check format"),
    ]
    pp_score = sum(1 for s in pp_subs if s.passed) / len(pp_subs) * 10
    checks.append(CheckResult(
        name="Problem pattern section",
        passed=all(s.passed for s in pp_subs),
        points_earned=round(pp_score, 1),
        points_possible=10,
        sub_checks=pp_subs,
    ))

    # 4. Behavior specification
    behavior = card.get("behavior", {})
    trigger = behavior.get("trigger", {})
    inputs = behavior.get("inputs", [])
    outputs = behavior.get("outputs", [])
    reasoning = behavior.get("reasoning", {})

    trigger_valid = trigger.get("type", "") in VALID_TRIGGER_TYPES
    inputs_valid = all(
        all(k in inp for k in REQUIRED_INPUT) for inp in inputs
    ) if inputs else False
    outputs_valid = all(
        all(k in out for k in REQUIRED_OUTPUT) for out in outputs
    ) if outputs else False
    has_reasoning = bool(reasoning.get("method") or reasoning.get("approach"))

    beh_subs = [
        SubCheck("trigger type valid", trigger_valid,
                 trigger.get("type", "(missing)")),
        SubCheck("inputs well-formed", inputs_valid,
                 f"{len(inputs)} inputs defined"),
        SubCheck("outputs well-formed", outputs_valid,
                 f"{len(outputs)} outputs defined"),
        SubCheck("reasoning documented", has_reasoning,
                 reasoning.get("method", "(not documented)")),
    ]
    beh_score = sum(1 for s in beh_subs if s.passed) / len(beh_subs) * 15
    checks.append(CheckResult(
        name="Behavior specification",
        passed=all(s.passed for s in beh_subs),
        points_earned=round(beh_score, 1),
        points_possible=15,
        sub_checks=beh_subs,
    ))

    # 5. Domain assumptions
    assumptions = card.get("domain_assumptions", {})
    all_assumptions = []
    for cat in ["data_assumptions", "environment_assumptions", "authority_assumptions"]:
        all_assumptions.extend(assumptions.get(cat, []))

    has_assumptions = len(all_assumptions) > 0
    ids_valid = all(
        bool(re.match(r'^[A-Z]{2}-\d{3}$', a.get("id", "")))
        for a in all_assumptions
    ) if all_assumptions else False
    strengths_valid = all(
        a.get("strength", "") in VALID_ASSUMPTION_STRENGTHS
        for a in all_assumptions
    ) if all_assumptions else False
    has_adaptation_notes = all(
        bool(a.get("adaptation_note"))
        for a in all_assumptions
    ) if all_assumptions else False

    da_subs = [
        SubCheck("has assumptions documented", has_assumptions,
                 f"{len(all_assumptions)} total"),
        SubCheck("IDs follow format (XX-NNN)", ids_valid or not all_assumptions,
                 "all valid" if ids_valid else "check format"),
        SubCheck("strengths are hard/soft", strengths_valid or not all_assumptions,
                 "all valid" if strengths_valid else "check values"),
        SubCheck("adaptation notes present", has_adaptation_notes or not all_assumptions,
                 "all have notes" if has_adaptation_notes else "some missing"),
    ]
    da_score = sum(1 for s in da_subs if s.passed) / len(da_subs) * 15
    checks.append(CheckResult(
        name="Domain assumptions",
        passed=all(s.passed for s in da_subs),
        points_earned=round(da_score, 1),
        points_possible=15,
        sub_checks=da_subs,
    ))

    # 6. Adaptation points
    aps = card.get("adaptation_points", [])
    has_aps = len(aps) > 0
    ap_ids_valid = all(
        bool(re.match(r'^AP-\d{3}$', ap.get("id", "")))
        for ap in aps
    ) if aps else False
    ap_types_valid = all(
        ap.get("type", "") in VALID_AP_TYPES
        for ap in aps
    ) if aps else False
    swappable_have_interface = all(
        bool(ap.get("interface"))
        for ap in aps if ap.get("type") == "swappable_component"
    ) if aps else True
    swappable_have_alternatives = all(
        len(ap.get("suggested_alternatives", [])) > 0
        for ap in aps if ap.get("type") == "swappable_component"
    ) if aps else True
    configurable_have_params = all(
        len(ap.get("parameters", [])) > 0
        for ap in aps if ap.get("type") == "configurable"
    ) if aps else True

    ap_subs = [
        SubCheck("has adaptation points", has_aps,
                 f"{len(aps)} defined"),
        SubCheck("IDs follow format (AP-NNN)", ap_ids_valid or not aps,
                 "all valid" if ap_ids_valid else "check format"),
        SubCheck("types valid", ap_types_valid or not aps,
                 "all valid" if ap_types_valid else "check values"),
        SubCheck("swappable components have interface", swappable_have_interface,
                 "all have interface name"),
        SubCheck("swappable components have alternatives", swappable_have_alternatives,
                 "all have 1+ alternative"),
        SubCheck("configurable points have parameters", configurable_have_params,
                 "all have parameters"),
    ]
    ap_score = sum(1 for s in ap_subs if s.passed) / len(ap_subs) * 15
    checks.append(CheckResult(
        name="Adaptation points",
        passed=all(s.passed for s in ap_subs),
        points_earned=round(ap_score, 1),
        points_possible=15,
        sub_checks=ap_subs,
    ))

    # 7. Composition
    composition = card.get("composition", {})
    has_composition = bool(composition)
    has_emits = len(composition.get("emits", [])) > 0
    has_listens = len(composition.get("listens_to", [])) > 0
    emits_have_payload = all(
        bool(e.get("payload")) for e in composition.get("emits", [])
    ) if composition.get("emits") else True

    comp_subs = [
        SubCheck("composition section exists", has_composition, ""),
        SubCheck("emits events defined", has_emits,
                 f"{len(composition.get('emits', []))} events"),
        SubCheck("listens_to events defined", has_listens,
                 f"{len(composition.get('listens_to', []))} events"),
        SubCheck("emitted events have payloads", emits_have_payload, ""),
    ]
    comp_score = sum(1 for s in comp_subs if s.passed) / len(comp_subs) * 10
    checks.append(CheckResult(
        name="Composition interface",
        passed=all(s.passed for s in comp_subs),
        points_earned=round(comp_score, 1),
        points_possible=10,
        sub_checks=comp_subs,
    ))

    # 8. Provenance
    provenance = card.get("provenance", {})
    has_origin = bool(provenance.get("origin", {}).get("domain"))
    has_lineage = len(provenance.get("lineage", [])) > 0
    lineage_has_versions = all(
        bool(l.get("version") and l.get("date"))
        for l in provenance.get("lineage", [])
    ) if provenance.get("lineage") else True

    prov_subs = [
        SubCheck("origin domain documented", has_origin, ""),
        SubCheck("lineage history present", has_lineage,
                 f"{len(provenance.get('lineage', []))} versions"),
        SubCheck("lineage entries have version + date", lineage_has_versions, ""),
    ]
    prov_score = sum(1 for s in prov_subs if s.passed) / len(prov_subs) * 5
    checks.append(CheckResult(
        name="Provenance & lineage",
        passed=all(s.passed for s in prov_subs),
        points_earned=round(prov_score, 1),
        points_possible=5,
        sub_checks=prov_subs,
    ))

    return checks


# =============================================================================
# TRUST VALIDATION
# =============================================================================

def validate_trust(card: dict) -> list[CheckResult]:
    """Validate the trust section against the Trust Framework."""
    checks = []
    trust = card.get("trust", {})

    # 1. Failure modes exist and are well-formed
    fms = trust.get("failure_modes", [])
    has_fms = len(fms) >= 3  # Minimum 3 failure modes
    fm_ids_valid = all(
        bool(re.match(r'^FM-\d{3}$', fm.get("id", "")))
        for fm in fms
    ) if fms else False
    fm_required_fields = ["id", "scenario", "impact", "severity"]
    fm_fields_present = all(
        all(k in fm for k in fm_required_fields)
        for fm in fms
    ) if fms else False
    fm_severities_valid = all(
        fm.get("severity", "") in VALID_SEVERITIES
        for fm in fms
    ) if fms else False

    fm_subs = [
        SubCheck("minimum 3 failure modes", has_fms,
                 f"{len(fms)} documented"),
        SubCheck("IDs follow format (FM-NNN)", fm_ids_valid or not fms, ""),
        SubCheck("required fields present", fm_fields_present, ""),
        SubCheck("severities valid", fm_severities_valid, ""),
    ]
    fm_score = sum(1 for s in fm_subs if s.passed) / len(fm_subs) * 20
    checks.append(CheckResult(
        name="Failure modes documented",
        passed=all(s.passed for s in fm_subs),
        points_earned=round(fm_score, 1),
        points_possible=20,
        sub_checks=fm_subs,
    ))

    # 2. Failure modes have mitigations
    fms_with_mitigation = [fm for fm in fms if fm.get("mitigation")]
    mitigation_coverage = len(fms_with_mitigation) / max(len(fms), 1)

    checks.append(CheckResult(
        name="Failure mode mitigations",
        passed=mitigation_coverage >= 1.0,
        points_earned=round(mitigation_coverage * 15, 1),
        points_possible=15,
        details=f"{len(fms_with_mitigation)}/{len(fms)} failure modes have mitigations",
        fix_suggestion="Add mitigation field to all failure modes" if mitigation_coverage < 1 else "",
    ))

    # 3. Failure mode category coverage
    fm_categories = set()
    for fm in fms:
        cat = fm.get("category", "")
        if cat:
            fm_categories.add(cat)
    # Also check for implied categories from scenario text
    category_keywords = {
        "INPUT": ["data", "stale", "missing", "input", "format"],
        "MODEL": ["forecast", "predict", "classif", "accuracy", "model"],
        "HUMAN": ["fatigue", "trust", "override", "ignore", "complacen"],
        "ETHICAL": ["bias", "equity", "fair", "discriminat", "vulnerable"],
    }
    implied_categories = set()
    for fm in fms:
        scenario = fm.get("scenario", "").lower()
        for cat, keywords in category_keywords.items():
            if any(kw in scenario for kw in keywords):
                implied_categories.add(cat)

    all_covered = fm_categories | implied_categories
    coverage = min(len(all_covered) / 4, 1.0)  # At least 4 categories

    checks.append(CheckResult(
        name="Failure category coverage",
        passed=len(all_covered) >= 4,
        points_earned=round(coverage * 10, 1),
        points_possible=10,
        details=f"{len(all_covered)} categories covered: {', '.join(sorted(all_covered)) if all_covered else 'none'}",
        fix_suggestion="Document failure modes across more categories (INPUT, MODEL, HUMAN, ETHICAL minimum)" if coverage < 1 else "",
    ))

    # 4. Ethical flags
    ethical_flags = trust.get("ethical_flags", [])
    has_ethical = len(ethical_flags) >= 1
    ethical_have_recommendation = all(
        bool(ef.get("recommendation"))
        for ef in ethical_flags
    ) if ethical_flags else True

    eth_subs = [
        SubCheck("ethical flags present", has_ethical,
                 f"{len(ethical_flags)} flags"),
        SubCheck("all have recommendations", ethical_have_recommendation, ""),
    ]
    eth_score = sum(1 for s in eth_subs if s.passed) / len(eth_subs) * 15
    checks.append(CheckResult(
        name="Ethical considerations",
        passed=all(s.passed for s in eth_subs),
        points_earned=round(eth_score, 1),
        points_possible=15,
        sub_checks=eth_subs,
    ))

    # 5. Performance expectations
    perf = trust.get("performance", {})
    has_scale = bool(perf.get("tested_scale"))
    has_latency = bool(perf.get("latency"))
    has_accuracy = bool(perf.get("accuracy"))
    has_degradation = bool(perf.get("known_degradation"))

    perf_subs = [
        SubCheck("tested_scale documented", has_scale, perf.get("tested_scale", "(missing)")),
        SubCheck("latency documented", has_latency, perf.get("latency", "(missing)")),
        SubCheck("accuracy documented", has_accuracy, str(perf.get("accuracy", "(missing)"))[:60]),
        SubCheck("known_degradation documented", has_degradation, ""),
    ]
    perf_score = sum(1 for s in perf_subs if s.passed) / len(perf_subs) * 15
    checks.append(CheckResult(
        name="Performance expectations",
        passed=all(s.passed for s in perf_subs),
        points_earned=round(perf_score, 1),
        points_possible=15,
        sub_checks=perf_subs,
    ))

    # 6. Observability
    obs = trust.get("observability", {})
    has_logging = bool(obs.get("logging"))
    has_explain = bool(obs.get("explainability"))
    has_repro = bool(obs.get("reproducibility"))

    obs_subs = [
        SubCheck("logging documented", has_logging, ""),
        SubCheck("explainability documented", has_explain, ""),
        SubCheck("reproducibility documented", has_repro, ""),
    ]
    obs_score = sum(1 for s in obs_subs if s.passed) / len(obs_subs) * 10
    checks.append(CheckResult(
        name="Observability",
        passed=all(s.passed for s in obs_subs),
        points_earned=round(obs_score, 1),
        points_possible=10,
        sub_checks=obs_subs,
    ))

    # 7. Domain-specific severity
    has_domain_severity = any(
        "severity_by_domain" in fm or "high_in_humanitarian" in str(fm.get("severity", ""))
        for fm in fms
    )
    checks.append(CheckResult(
        name="Domain-specific severity",
        passed=has_domain_severity,
        points_earned=5 if has_domain_severity else 0,
        points_possible=5,
        details="Domain-adjusted severity documented" if has_domain_severity else "No domain-specific severity found",
        fix_suggestion="Add severity_by_domain to failure modes that change severity across domains" if not has_domain_severity else "",
    ))

    # 8. Human oversight / kill switch (bonus)
    has_oversight = bool(trust.get("human_oversight"))
    has_kill_switch = bool(trust.get("kill_switch"))
    has_degradation = bool(trust.get("degradation_modes"))
    bonus_items = sum([has_oversight, has_kill_switch, has_degradation])

    checks.append(CheckResult(
        name="Operational guardrails (bonus)",
        passed=bonus_items >= 2,
        points_earned=round(bonus_items / 3 * 10, 1),
        points_possible=10,
        details=f"human_oversight: {'yes' if has_oversight else 'no'}, "
                f"kill_switch: {'yes' if has_kill_switch else 'no'}, "
                f"degradation_modes: {'yes' if has_degradation else 'no'}",
    ))

    return checks


# =============================================================================
# IMPLEMENTATION VALIDATION
# =============================================================================

def validate_implementation(project_path: str, card: dict) -> list[CheckResult]:
    """Validate project implementation against card claims."""
    checks = []
    p = Path(project_path)

    # 1. Project structure
    expected_dirs = ["interfaces", "implementations", "config", "events", "core", "tests"]
    found_dirs = [d for d in expected_dirs if (p / d).is_dir()]
    # Also check common alternative structures
    alt_dirs = ["src", "lib", "test", "spec"]
    alt_found = [d for d in alt_dirs if (p / d).is_dir()]

    struct_subs = [
        SubCheck(d, (p / d).is_dir(),
                 "found" if (p / d).is_dir() else "missing")
        for d in expected_dirs
    ]
    struct_score = len(found_dirs) / len(expected_dirs) * 5
    checks.append(CheckResult(
        name="Project structure",
        passed=len(found_dirs) >= 4,
        points_earned=round(struct_score, 1),
        points_possible=5,
        details=f"{len(found_dirs)}/{len(expected_dirs)} standard directories found",
        fix_suggestion=f"Create missing directories: {', '.join(d for d in expected_dirs if d not in found_dirs)}" if found_dirs else "",
        sub_checks=struct_subs,
    ))

    # 2. Interface files exist for swappable APs
    aps = card.get("adaptation_points", [])
    swappable_aps = [ap for ap in aps if ap.get("type") == "swappable_component"]

    interface_subs = []
    for ap in swappable_aps:
        ap_name = ap.get("name", "unknown")
        interface_name = ap.get("interface", "")
        # Search for interface file
        patterns = [
            f"interfaces/*{ap_name}*",
            f"interfaces/*{interface_name.lower()}*",
            f"src/interfaces/*{ap_name}*",
            f"**/interface*{ap_name}*",
        ]
        found = False
        for pattern in patterns:
            if glob.glob(str(p / pattern), recursive=True):
                found = True
                break
        interface_subs.append(SubCheck(
            f"AP {ap.get('id', '???')}: {ap_name} ({interface_name})",
            found,
            "interface file found" if found else "no interface file"
        ))

    if swappable_aps:
        interfaces_found = sum(1 for s in interface_subs if s.passed)
        intf_score = interfaces_found / len(swappable_aps) * 15
    else:
        intf_score = 15  # No swappable APs = automatic pass
    checks.append(CheckResult(
        name="Interface files for swappable APs",
        passed=all(s.passed for s in interface_subs) if interface_subs else True,
        points_earned=round(intf_score, 1),
        points_possible=15,
        sub_checks=interface_subs,
        fix_suggestion="Create interface files in interfaces/ directory for each swappable AP" if intf_score < 15 else "",
    ))

    # 3. Multiple implementations per swappable AP
    impl_subs = []
    for ap in swappable_aps:
        ap_name = ap.get("name", "unknown")
        patterns = [
            f"implementations/**/*{ap_name}*",
            f"implementations/**/*{ap.get('interface', '').lower()}*",
            f"src/**/*{ap_name}*",
        ]
        found_files = set()
        for pattern in patterns:
            found_files.update(glob.glob(str(p / pattern), recursive=True))
        impl_subs.append(SubCheck(
            f"AP {ap.get('id', '???')}: {ap_name}",
            len(found_files) >= 2,
            f"{len(found_files)} implementations found"
        ))

    if swappable_aps:
        impls_ok = sum(1 for s in impl_subs if s.passed)
        impl_score = impls_ok / len(swappable_aps) * 15
    else:
        impl_score = 15
    checks.append(CheckResult(
        name="Multiple implementations (2+)",
        passed=all(s.passed for s in impl_subs) if impl_subs else True,
        points_earned=round(impl_score, 1),
        points_possible=15,
        sub_checks=impl_subs,
        fix_suggestion="Add at least 2 implementations per swappable AP in implementations/ directory" if impl_score < 15 else "",
    ))

    # 4. Swap tests exist
    test_patterns = [
        "tests/swap/**",
        "tests/*swap*",
        "tests/**/test_*swap*",
        "test/*swap*",
    ]
    swap_tests = set()
    for pattern in test_patterns:
        swap_tests.update(glob.glob(str(p / pattern), recursive=True))
    has_swap_tests = len(swap_tests) > 0

    checks.append(CheckResult(
        name="Swap tests exist",
        passed=has_swap_tests,
        points_earned=20 if has_swap_tests else 0,
        points_possible=20,
        details=f"{len(swap_tests)} swap test files found" if has_swap_tests else "No swap tests found",
        fix_suggestion="Create tests/swap/ directory with swap tests per the Implementation Guide" if not has_swap_tests else "",
    ))

    # 5. Config externalized
    config_patterns = [
        "config/**/*.yaml",
        "config/**/*.yml",
        "config/**/*.json",
        "config/**/*.py",
        "*.config.*",
    ]
    config_files = set()
    for pattern in config_patterns:
        config_files.update(glob.glob(str(p / pattern), recursive=True))
    has_config = len(config_files) > 0

    checks.append(CheckResult(
        name="Configuration externalized",
        passed=has_config,
        points_earned=10 if has_config else 0,
        points_possible=10,
        details=f"{len(config_files)} config files found" if has_config else "No external config files",
        fix_suggestion="Create config/ directory with externalized configuration per the Implementation Guide" if not has_config else "",
    ))

    # 6. Event schemas exist
    event_patterns = [
        "events/**/*.py",
        "events/**/*.ts",
        "events/**/*.json",
        "src/events/**",
    ]
    event_files = set()
    for pattern in event_patterns:
        event_files.update(glob.glob(str(p / pattern), recursive=True))

    emitted_events = card.get("composition", {}).get("emits", [])
    has_event_schemas = len(event_files) > 0 or len(emitted_events) == 0

    checks.append(CheckResult(
        name="Event schemas defined",
        passed=has_event_schemas,
        points_earned=5 if has_event_schemas else 0,
        points_possible=5,
        details=f"{len(event_files)} event schema files for {len(emitted_events)} emitted events",
        fix_suggestion="Create events/ directory with typed schemas for each emitted event" if not has_event_schemas else "",
    ))

    # 7. Assumption guard tests
    test_patterns_assumption = [
        "tests/assumptions/**",
        "tests/*assumption*",
        "tests/**/test_*da*",
        "tests/*guard*",
    ]
    assumption_tests = set()
    for pattern in test_patterns_assumption:
        assumption_tests.update(glob.glob(str(p / pattern), recursive=True))
    has_assumption_tests = len(assumption_tests) > 0

    checks.append(CheckResult(
        name="Assumption guard tests",
        passed=has_assumption_tests,
        points_earned=10 if has_assumption_tests else 0,
        points_possible=10,
        details=f"{len(assumption_tests)} assumption test files found" if has_assumption_tests else "No assumption tests",
        fix_suggestion="Create tests/assumptions/ with tests for hard assumption guards" if not has_assumption_tests else "",
    ))

    # 8. Isolation tests
    isolation_patterns = [
        "tests/isolation/**",
        "tests/*isolation*",
        "tests/*standalone*",
        "tests/**/test_*standalone*",
    ]
    isolation_tests = set()
    for pattern in isolation_patterns:
        isolation_tests.update(glob.glob(str(p / pattern), recursive=True))
    has_isolation = len(isolation_tests) > 0

    # Check if there are optional delegates
    delegates = card.get("composition", {}).get("delegates_to", [])
    optional_delegates = [d for d in delegates if not d.get("required", True)]

    needs_isolation = len(optional_delegates) > 0
    checks.append(CheckResult(
        name="Composition isolation tests",
        passed=has_isolation or not needs_isolation,
        points_earned=5 if (has_isolation or not needs_isolation) else 0,
        points_possible=5,
        details=f"{len(isolation_tests)} isolation tests for {len(optional_delegates)} optional delegates",
        fix_suggestion="Create tests/isolation/ to verify behavior works without optional delegates" if (not has_isolation and needs_isolation) else "",
    ))

    # 9. ABC card file present in project
    card_files = glob.glob(str(p / "abc-card.*")) + glob.glob(str(p / "abc_card.*"))
    has_card_in_project = len(card_files) > 0

    checks.append(CheckResult(
        name="ABC card in project root",
        passed=has_card_in_project,
        points_earned=5 if has_card_in_project else 0,
        points_possible=5,
        details="abc-card.yaml found" if has_card_in_project else "No abc-card file in project root",
        fix_suggestion="Place your abc-card.yaml in the project root directory" if not has_card_in_project else "",
    ))

    # 10. No hardcoded magic numbers (basic static analysis)
    # Scan core/ and src/ for common anti-patterns
    source_files = (
        glob.glob(str(p / "core/**/*.py"), recursive=True) +
        glob.glob(str(p / "src/**/*.py"), recursive=True) +
        glob.glob(str(p / "core/**/*.ts"), recursive=True) +
        glob.glob(str(p / "src/**/*.ts"), recursive=True)
    )

    magic_number_count = 0
    hardcoded_examples = []
    magic_pattern = re.compile(r'(?:if|>|<|>=|<=|==)\s*\d+\.?\d*(?!\s*[,\]\)])')

    for sf in source_files[:20]:  # Limit scan
        try:
            with open(sf) as f:
                for i, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped.startswith('#') or stripped.startswith('//'):
                        continue
                    matches = magic_pattern.findall(stripped)
                    if matches and not any(skip in stripped.lower()
                                           for skip in ['import', 'version', 'range', 'len(']):
                        magic_number_count += len(matches)
                        if len(hardcoded_examples) < 3:
                            hardcoded_examples.append(f"  {os.path.basename(sf)}:{i}: {stripped[:80]}")
        except Exception:
            pass

    no_magic = magic_number_count <= 5  # Allow a few
    checks.append(CheckResult(
        name="No hardcoded magic numbers (basic scan)",
        passed=no_magic,
        points_earned=10 if no_magic else max(0, 10 - magic_number_count),
        points_possible=10,
        details=f"{magic_number_count} potential magic numbers found" + (
            "\n" + "\n".join(hardcoded_examples) if hardcoded_examples else ""),
        fix_suggestion="Move hardcoded values to configuration. See Implementation Guide anti-patterns." if not no_magic else "",
    ))

    return checks


# =============================================================================
# REPORT GENERATION
# =============================================================================

def calculate_score(checks: list[CheckResult]) -> float:
    total_earned = sum(c.points_earned for c in checks)
    total_possible = sum(c.points_possible for c in checks)
    if total_possible == 0:
        return 0
    return round(total_earned / total_possible * 100, 1)


def determine_level(score: float) -> str:
    if score >= 90:
        return "ABC Certified"
    elif score >= 70:
        return "ABC Compatible"
    elif score >= 50:
        return "ABC Aspirational"
    else:
        return "Non-compliant"


def level_color(level: str) -> str:
    if "Certified" in level:
        return Colors.GREEN
    elif "Compatible" in level:
        return Colors.YELLOW
    elif "Aspirational" in level:
        return Colors.YELLOW
    else:
        return Colors.RED


def print_report(report: ComplianceReport, show_details: bool = True,
                 show_fixes: bool = False):
    """Print a formatted compliance report to stdout."""

    c = Colors
    w = 56

    print()
    print(f"{c.CYAN}┌{'─' * w}┐{c.RESET}")
    print(f"{c.CYAN}│{c.BOLD}{c.WHITE} ABC Compliance Report{' ' * (w - 22)}│{c.RESET}")
    print(f"{c.CYAN}│{c.RESET} Card: {c.BOLD}{report.card_name}{c.RESET}"
          f"{' ' * max(1, w - 7 - len(report.card_name))}│")
    print(f"{c.CYAN}│{c.RESET} Version: {report.card_version}  |  "
          f"Spec: {report.spec_version}"
          f"{' ' * max(1, w - 24 - len(report.card_version) - len(report.spec_version))}│")
    if report.project_path:
        path_display = report.project_path[:w - 9]
        print(f"{c.CYAN}│{c.RESET} Path: {path_display}"
              f"{' ' * max(1, w - 7 - len(path_display))}│")
    print(f"{c.CYAN}├{'─' * w}┤{c.RESET}")

    # Card validation
    if report.card_checks:
        print(f"{c.CYAN}│{c.BOLD} Card Validation{' ' * (w - 16)}│{c.RESET}")
        for check in report.card_checks:
            status = icon(check.passed)
            name = check.name[:35]
            score = f"{check.points_earned:.0f}/{check.points_possible:.0f}"
            padding = w - 5 - len(name) - len(score)
            print(f"{c.CYAN}│{c.RESET}  {status} {name}{' ' * max(1, padding)}{score} │")

            if show_details and check.sub_checks:
                for sub in check.sub_checks:
                    sub_icon = f"{c.GREEN}·{c.RESET}" if sub.passed else f"{c.RED}·{c.RESET}"
                    sub_text = f"{sub.item[:40]}"
                    print(f"{c.CYAN}│{c.RESET}     {sub_icon} {c.DIM}{sub_text}{c.RESET}"
                          f"{' ' * max(1, w - 8 - len(sub_text))}│")

            if show_fixes and check.fix_suggestion:
                fix = check.fix_suggestion[:w - 10]
                print(f"{c.CYAN}│{c.RESET}     {c.YELLOW}→ {fix}{c.RESET}"
                      f"{' ' * max(1, w - 8 - len(fix))}│")

        cv_score = f"{report.card_validation_score:.0f}/100"
        print(f"{c.CYAN}│{c.RESET}  {'Card Score:':>38} {c.BOLD}{cv_score}{c.RESET}"
              f"{' ' * max(1, w - 46 - len(cv_score))}│")
        print(f"{c.CYAN}├{'─' * w}┤{c.RESET}")

    # Trust validation
    if report.trust_checks:
        print(f"{c.CYAN}│{c.BOLD} Trust & Safety{' ' * (w - 15)}│{c.RESET}")
        for check in report.trust_checks:
            status = icon(check.passed)
            name = check.name[:35]
            score = f"{check.points_earned:.0f}/{check.points_possible:.0f}"
            padding = w - 5 - len(name) - len(score)
            print(f"{c.CYAN}│{c.RESET}  {status} {name}{' ' * max(1, padding)}{score} │")

            if show_fixes and check.fix_suggestion:
                fix = check.fix_suggestion[:w - 10]
                print(f"{c.CYAN}│{c.RESET}     {c.YELLOW}→ {fix}{c.RESET}"
                      f"{' ' * max(1, w - 8 - len(fix))}│")

        ts_score = f"{report.trust_score:.0f}/100"
        print(f"{c.CYAN}│{c.RESET}  {'Trust Score:':>38} {c.BOLD}{ts_score}{c.RESET}"
              f"{' ' * max(1, w - 47 - len(ts_score))}│")
        print(f"{c.CYAN}├{'─' * w}┤{c.RESET}")

    # Implementation validation
    if report.implementation_checks:
        print(f"{c.CYAN}│{c.BOLD} Implementation Compliance{' ' * (w - 26)}│{c.RESET}")
        for check in report.implementation_checks:
            status = icon(check.passed)
            name = check.name[:35]
            score = f"{check.points_earned:.0f}/{check.points_possible:.0f}"
            padding = w - 5 - len(name) - len(score)
            print(f"{c.CYAN}│{c.RESET}  {status} {name}{' ' * max(1, padding)}{score} │")

            if show_fixes and check.fix_suggestion:
                fix = check.fix_suggestion[:w - 10]
                print(f"{c.CYAN}│{c.RESET}     {c.YELLOW}→ {fix}{c.RESET}"
                      f"{' ' * max(1, w - 8 - len(fix))}│")

        is_score = f"{report.implementation_score:.0f}/100"
        print(f"{c.CYAN}│{c.RESET}  {'Implementation Score:':>38} {c.BOLD}{is_score}{c.RESET}"
              f"{' ' * max(1, w - 47 - len(is_score))}│")
        print(f"{c.CYAN}├{'─' * w}┤{c.RESET}")

    # Overall
    lc = level_color(report.level)
    overall = f"{report.overall_score:.0f}/100"
    print(f"{c.CYAN}│{c.RESET}")
    print(f"{c.CYAN}│{c.RESET}  {c.BOLD}Overall Score: {overall}  —  "
          f"{lc}{report.level}{c.RESET}")
    print(f"{c.CYAN}│{c.RESET}")

    if report.suggestions:
        print(f"{c.CYAN}│{c.RESET}  {c.YELLOW}Top actions:{c.RESET}")
        for s in report.suggestions[:3]:
            print(f"{c.CYAN}│{c.RESET}    → {s[:w - 7]}")

    print(f"{c.CYAN}└{'─' * w}┘{c.RESET}")
    print()


# =============================================================================
# MAIN
# =============================================================================

def find_card(path: str) -> Optional[str]:
    """Find the ABC card file in a project directory."""
    p = Path(path)
    candidates = [
        p / "abc-card.yaml",
        p / "abc-card.yml",
        p / "abc_card.yaml",
        p / "abc_card.yml",
    ]
    # Also search for any .yaml file with abc_version in it
    for c in candidates:
        if c.exists():
            return str(c)

    # Search all yaml files in root
    for f in p.glob("*.yaml"):
        try:
            with open(f) as fh:
                content = yaml.safe_load(fh)
                if isinstance(content, dict) and "abc_version" in content:
                    return str(f)
        except Exception:
            pass
    for f in p.glob("*.yml"):
        try:
            with open(f) as fh:
                content = yaml.safe_load(fh)
                if isinstance(content, dict) and "abc_version" in content:
                    return str(f)
        except Exception:
            pass

    return None


def run_check(path: str, card_only: bool = False, json_output: bool = False,
              show_fixes: bool = False, no_color: bool = False) -> ComplianceReport:
    """Run the full compliance check."""

    if no_color:
        Colors.disable()

    p = Path(path)
    report = ComplianceReport()

    # Determine if path is a card file or project directory
    if p.is_file() or card_only:
        card_path = str(p)
        project_path = None
    elif p.is_dir():
        card_path = find_card(str(p))
        project_path = str(p)
        if not card_path:
            print(f"{Colors.RED}ERROR: No ABC card found in {path}{Colors.RESET}")
            print(f"  Looked for: abc-card.yaml, abc_card.yaml, or any .yaml with abc_version")
            sys.exit(4)
    else:
        print(f"{Colors.RED}ERROR: Path not found: {path}{Colors.RESET}")
        sys.exit(4)

    # Load card
    try:
        with open(card_path) as f:
            card = yaml.safe_load(f)
    except Exception as e:
        print(f"{Colors.RED}ERROR: Failed to parse {card_path}: {e}{Colors.RESET}")
        sys.exit(4)

    if not isinstance(card, dict):
        print(f"{Colors.RED}ERROR: Card is not a valid YAML mapping{Colors.RESET}")
        sys.exit(4)

    report.card_name = card.get("identity", {}).get("display_name",
                       card.get("identity", {}).get("name", "Unknown"))
    report.card_version = card.get("identity", {}).get("version", "?.?.?")
    report.card_path = card_path
    report.project_path = project_path or ""

    # 1. Validate card
    report.card_checks = validate_card(card)
    report.card_validation_score = calculate_score(report.card_checks)

    # 2. Validate trust
    report.trust_checks = validate_trust(card)
    report.trust_score = calculate_score(report.trust_checks)

    # 3. Validate implementation (if project directory)
    if project_path and not card_only:
        report.implementation_checks = validate_implementation(project_path, card)
        report.implementation_score = calculate_score(report.implementation_checks)
        # Overall = weighted combination
        report.overall_score = (
            report.card_validation_score * 0.30 +
            report.trust_score * 0.30 +
            report.implementation_score * 0.40
        )
    else:
        # Card-only mode: average of card + trust
        report.overall_score = (
            report.card_validation_score * 0.55 +
            report.trust_score * 0.45
        )

    report.level = determine_level(report.overall_score)

    # Generate suggestions
    all_checks = report.card_checks + report.trust_checks + report.implementation_checks
    failed = [c for c in all_checks if not c.passed]
    failed.sort(key=lambda c: c.points_possible - c.points_earned, reverse=True)
    report.suggestions = [c.fix_suggestion for c in failed if c.fix_suggestion][:5]

    # Output
    if json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report, show_details=True, show_fixes=show_fixes)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="ABC Compliance Checker — Validate Agent Behavior Cards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  abc-check ./my-behavior/              Full project compliance check
  abc-check ./abc-card.yaml --card      Card-only validation
  abc-check ./my-behavior/ --json       JSON output for CI/CD
  abc-check ./my-behavior/ --fix        Show fix suggestions
  abc-check ./cards/ --batch            Check all cards in directory
        """
    )
    parser.add_argument("path", help="Path to project directory or card file")
    parser.add_argument("--card", action="store_true",
                        help="Card-only validation (skip implementation checks)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--fix", action="store_true",
                        help="Show fix suggestions for failed checks")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable colored output")
    parser.add_argument("--batch", action="store_true",
                        help="Check all .yaml card files in directory")

    args = parser.parse_args()

    if args.batch:
        # Batch mode: check all cards in directory
        p = Path(args.path)
        if not p.is_dir():
            print(f"ERROR: {args.path} is not a directory")
            sys.exit(4)

        cards = list(p.glob("*.yaml")) + list(p.glob("*.yml"))
        results = []
        for card_file in sorted(cards):
            try:
                with open(card_file) as f:
                    content = yaml.safe_load(f)
                if isinstance(content, dict) and "abc_version" in content:
                    report = run_check(str(card_file), card_only=True,
                                       json_output=False, show_fixes=args.fix,
                                       no_color=args.no_color)
                    results.append((card_file.name, report))
            except Exception as e:
                print(f"{Colors.YELLOW}Skipping {card_file.name}: {e}{Colors.RESET}")

        if not args.json:
            # Print summary table
            print(f"\n{Colors.BOLD}{'=' * 70}")
            print(f"BATCH SUMMARY: {len(results)} cards checked")
            print(f"{'=' * 70}{Colors.RESET}\n")
            print(f"  {'Card':<40} {'Score':>6}  {'Level'}")
            print(f"  {'─' * 40} {'─' * 6}  {'─' * 20}")
            for name, report in results:
                lc = level_color(report.level)
                print(f"  {name:<40} {report.overall_score:>5.0f}  "
                      f"{lc}{report.level}{Colors.RESET}")
            print()

        if args.json:
            batch_output = {
                "total_cards": len(results),
                "results": [
                    {"file": name, **report.to_dict()}
                    for name, report in results
                ]
            }
            print(json.dumps(batch_output, indent=2))

        # Exit code based on worst result
        if results:
            worst = min(r.overall_score for _, r in results)
            if worst >= 90: sys.exit(0)
            elif worst >= 70: sys.exit(1)
            elif worst >= 50: sys.exit(2)
            else: sys.exit(3)
        sys.exit(0)

    else:
        report = run_check(args.path, card_only=args.card,
                           json_output=args.json, show_fixes=args.fix,
                           no_color=args.no_color)

        # Exit code
        if report.overall_score >= 90: sys.exit(0)
        elif report.overall_score >= 70: sys.exit(1)
        elif report.overall_score >= 50: sys.exit(2)
        else: sys.exit(3)


if __name__ == "__main__":
    main()
