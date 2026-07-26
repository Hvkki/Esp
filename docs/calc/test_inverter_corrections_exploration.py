#!/usr/bin/env python3
"""Frozen Property 1 exploration/fix test for inverter-loss corrections.

The file is intentionally created and hashed before the corrected implementation.
It fails on the unfixed baseline, then must pass unchanged against the correction.

**Validates: Requirements 1.1-1.12, 2.1-2.42, 3.11, 3.12**
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALC = Path(__file__).resolve().parent
if str(CALC) not in sys.path:
    sys.path.insert(0, str(CALC))

FIXTURES = (
    {"fixture_id":"EVID-SC209-060","branch":"evidenceClassOrConflictContractInvalid","input":{"subject":"IRL40SC209","rds_mohm":"3/5","legacy_label":"manufacturer"},"expected":"USER_SPECIFIED_TARGET"},
    {"fixture_id":"EVID-T209-059-072","branch":"evidenceClassOrConflictContractInvalid","input":{"subject":"IRL40T209","rds_mohm":["59/100","18/25"],"used_for":"IRL40SC209"},"expected":"RELATED_PART"},
    {"fixture_id":"EVID-PENDING-13-17","branch":"rawPendingEvidenceConsumed","input":{"rows_mohm":["13/10","17/10"],"ConflictStatus":"PENDING"},"expected":"INELIGIBLE_FOR_CONSUMPTION"},
    {"fixture_id":"TIMING-P10","branch":"digitalTimingDiffersFromFixedOracle","input":{"p":10,"legacy_N":2286,"legacy_H":1143,"legacy_adjusted_count":15},"expected":{"N":2285,"H":1142,"k":114,"adjusted_count":16}},
    {"fixture_id":"TIMING-P1","branch":"unavailableAdjustedSrOrAggregateWasCoercedToEmptyZeroOrLossFree","input":{"p":1,"legacy_sr_b_order":["ON","OFF"],"legacy_adjusted_lv_count":0},"expected":{"adjusted_lv_count":8,"sr_b_order":["OFF","ON"],"adjusted_sr":"UNAVAILABLE"}},
    {"fixture_id":"TIMING-P0","branch":"zeroCommandErasesActualResidual","input":{"p":0,"legacy_actual_loss":0},"expected":{"adjusted_lv_count":8,"owner":"LEG_COMMAND_TICK_ASYMMETRY","aggregate":"UNAVAILABLE"}},
    {"fixture_id":"ANALOG-MISSING","branch":"analogOrSettlingDecisionUsesUnapprovedDefault","input":{"modref":None},"expected":"UNAVAILABLE_NON_GATING"},
    {"fixture_id":"SETTLING-CALLER","branch":"analogOrSettlingDecisionUsesUnapprovedDefault","input":{"caller_settled":True,"thresholds":None},"expected":"TRANSITION_UNAVAILABLE_NON_GATING"},
    {"fixture_id":"NOLOAD-LOADED-CONSTANTS","branch":"staleRoundedOrUnsupportedResultPublished","input":{"loaded_watts":[36.0,42.8],"load_state":"NO_LOAD"},"expected":"REJECT_PROMOTION"},
    {"fixture_id":"QUAL-48-INCOMPLETE","branch":"syntheticEvidenceSupportsRealClaim","input":{"voltage":48,"exact_device_bundle":None},"expected":"UNAVAILABLE_NON_GATING"},
    {"fixture_id":"THERMAL-ROOT","branch":"thermalModeOrUniquenessClaimInvalid","input":{"seed_agreement":True,"root_certificate":None},"expected":"UNPROVEN"},
    {"fixture_id":"BOUNDARY-EXCLUDED","branch":"excludedFieldInfluencesInverter","input":{"mutated":"battery.internal_resistance"},"expected":"EXACT_INVERTER_INVARIANCE"},
    {"fixture_id":"GATE-TREF-LATE","branch":"comparisonGateArtifactCodeCardinalityPrerequisiteOrOrderInvalid","input":{"T_ref":{"value":75,"unit":"degC","frozen_before_gates":False}},"expected":"UNRESOLVED_DEPENDENTS_UNAVAILABLE"},
    {"fixture_id":"GATE-CONTROLLED-ZERO","branch":"comparisonGateArtifactCodeCardinalityPrerequisiteOrOrderInvalid","input":{"gate":"CONTROLLED_THREEFOLD","irms":0,"conduction_nonempty":True,"canonical_code":"INELIGIBLE"},"expected":"INELIGIBLE_ZERO_IRMS"},
    {"fixture_id":"GATE-ENDPOINT-NOCASE","branch":"comparisonGateArtifactCodeCardinalityPrerequisiteOrOrderInvalid","input":{"gate":"ENDPOINT_SENSITIVITY","eligible_cases":0,"policy":None},"expected":"UNRESOLVED_NOT_INELIGIBLE"},
    {"fixture_id":"MATERIAL-STALE","branch":"MaterialResultLatticeOrFreshnessViolated","input":{"dependency_hash_changed":True,"freshness":"FRESH"},"expected":"STALE_BLOCKED"},
    {"fixture_id":"PUBLICATION-UNSAFE","branch":"staleRoundedOrUnsupportedResultPublished","input":{"freshness":"STALE","rounded_input":True},"expected":"REJECT"},
)


def baseline_counterexamples() -> list[dict]:
    review = (ROOT / "docs/REVIEW.md").read_text(encoding="utf-8")
    comparison = (ROOT / "docs/COMPARISON.md").read_text(encoding="utf-8")
    config = (ROOT / "firmware/main/inv_config.h").read_text(encoding="utf-8")
    failures = []
    checks = {
        "EVID-SC209-060": "0.59 мОм typ / 0.72 мОм max" in review,
        "TIMING-P10": "2286 при 70 кГц" in config,
        "NOLOAD-LOADED-CONSTANTS": "42.8 Вт не залежать від навантаження" in comparison,
        "QUAL-48-INCOMPLETE": "IRL40SC209\*" in review,
    }
    by_id = {f["fixture_id"]: f for f in FIXTURES}
    for fixture_id, observed in checks.items():
        if observed:
            f = by_id[fixture_id]
            payload = json.dumps(f["input"], sort_keys=True, separators=(",", ":"))
            failures.append({
                "fixture_id": fixture_id,
                "bug_condition_branch": f["branch"],
                "canonical_input": payload,
                "actual_behavior": "legacy unsupported/incorrect claim present",
                "expected_behavior": f["expected"],
                "affected_artifact_ids_hashes": [
                    "docs/REVIEW.md:" + hashlib.sha256(review.encode()).hexdigest(),
                    "docs/COMPARISON.md:" + hashlib.sha256(comparison.encode()).hexdigest(),
                    "firmware/main/inv_config.h:" + hashlib.sha256(config.encode()).hexdigest(),
                ],
                "exact_failure": "expectedBehavior(result) is false on frozen baseline",
            })
    return failures


class FrozenConservativePipelineProperty(unittest.TestCase):
    def test_property_1_conservative_corrected_pipeline(self) -> None:
        try:
            from inverter_corrections import evaluate_exploration_fixture
        except ImportError:
            failures = baseline_counterexamples()
            self.fail("FROZEN_BASELINE_COUNTEREXAMPLES=" + json.dumps(failures, sort_keys=True))

        failures = []
        for fixture in FIXTURES:
            result = evaluate_exploration_fixture(fixture)
            if not result.get("expected_behavior_satisfied", False):
                failures.append(result)
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main(verbosity=2)
