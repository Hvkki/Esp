# Evidence-Conservative Inverter-Loss Correction

This publication is limited to calculation, evidence, oracle, validation, trace, test, and publication artifacts. Firmware source, configuration, and behavior are unchanged.

## Corrected conclusions

- **IRL40SC209 0.60 mΩ** is a `USER_SPECIFIED_TARGET`, not a manufacturer typical, maximum, guaranteed, direct, or measured value. The legacy IRL40T209 0.59/0.72 mΩ values remain `RELATED_PART` evidence only. The unresolved 1.3/1.7 mΩ rows remain separate `PENDING` records and are not selectable or consumable.
- Repository timing uses the compiled integer semantics `N=2285`, `H=1142`, raw intervals 1142/1143 ticks, period `2285/160000000 s`, and actual carrier `32000000/457 Hz`. The 70 kHz value is a nominal label.
- At p=10, q=114.2, k=114, and the complete adjusted event count is 16. At p=1 and p=0, the adjusted LV count is 8 and simultaneous tick-2284 SR events order OFF before ON.
- At p=1 and p=0, suppressed-pulse semantics, complete adjusted SR events/count, and complete aggregate adjusted events/count are safety-relevant, non-gating `UNAVAILABLE`. They are not empty, zero-transition, zero-switching, zero-gate-loss, or loss-free results.
- At p=0, only ideal commanded transfer/excitation is zero. The `LV_B_ON=1` implementation guard is owned exactly once by `LEG_COMMAND_TICK_ASYMMETRY`; unknown analog current, energy, and loss are not replaced by zero.
- Loaded 36 W and 42.8 W constants retain their loaded context and are not no-load facts. Every no-load category is classified independently.
- Realistic device comparison requires one immutable in-domain common Tref frozen before both gates and exactly two distinct immutable pre-realistic gate artifacts. A valid ineligibility authorizes progression only; it never claims completion, pass, or success. Invalid authorization makes dependent results `UNAVAILABLE` while unrelated results remain unchanged.

## Local non-gating evidence gaps

The repository contains no qualifying external artifact for direct exact-part IRL40SC209 manufacturer RDS(on), independent analog MODREF values, product settling thresholds/observations, a complete thermal model, complete exact-device 48 V qualification, independent hardware measurement, a complete-domain root certificate, or independent ESP-IDF suppressed-pulse semantics. Each gap remains visible on only its dependent decision as `PROVISIONAL`, `UNAVAILABLE`, or `UNPROVEN`; none is fabricated and none gates this bugfix acceptance.

## Status and trace

Results use canonical full-precision values and `MaterialResult` availability/freshness metadata. Missing ATS-v2 applicability makes only the affected numerical decision unavailable; no local tolerance is substituted. Synthetic fixtures are marked and cannot support real product, manufacturer, safety, or measured claims. Firmware implementation and hardware measurement are independent status axes.

Machine-readable baseline, preservation, oracle, and acceptance evidence is maintained by the self-contained standard-library tools in `docs/calc/`. The frozen preservation inventory covers all 67 required namespaced keys with non-vacuous evaluation.


## Final semantic-review hardening

The executable contracts now close the six bypasses found by final review:

- Comparison outcomes reference exact-schema prerequisite documents resolved from a trusted immutable-content registry. Controlled and endpoint validators recalculate eligibility and outputs from resolved content; stripped schemas, wrong artifact types, unrelated hashes, and invented policy/evidence are rejected.
- Enforced preservation sends every eligible `BASELINE_BEHAVIOR` input through both an immutable Git-commit baseline adapter and the current corrected implementation, then compares canonical outcomes. `NO_BASELINE_BEHAVIOR` routes execute field-specific behavioral assertions rather than presence checks.
- Firmware-derived timing and immutable expected timing use separate constructors. The expected p=10/1/0 vectors independently enumerate every event tick, class, device identity, edge, order, unavailable field, and p=0 residual owner.
- Dynamic thermal inputs must exactly match the physical values stored in a resolved hash-valid artifact. No-load reporting accepts only a validated settlement `MaterialResult`; a caller string cannot establish `SETTLED`.
- Qualification, firmware-control, hardware-control, and publication decisions resolve exact semantic content from the trusted registry. Publication fields are freshly derived from registered dependencies; empty bundles, invented text, and bare hashes cannot create available claims.
- `ArtifactRegistry` validates an exact, closed, acyclic dependency graph against each result’s declared dependency IDs and hashes. Missing, extra, unknown, self, cyclic, or hash-inconsistent edges are rejected before selection or consumption.

Adversarial regression tests reproduce each final-review probe. Frozen Property 1 and frozen Property 2 source artifacts remain byte-for-byte unchanged. Enforced preservation evaluates 69 eligible cases, including three independent bridge-conduction cases, and aggregate acceptance remains non-vacuous while preserving every intentionally non-gating external evidence gap.


## Independent re-review corrections

Four confirmed bypasses are now closed. Immutable content hashes are treated only as identity: a separately signed, closed, type-specific trust root must grant the exact artifact ID/version/type/hash and enforce the required owner and approval before comparison, thermal, qualification, control, or publication code can resolve it. Caller-minted artifacts, owner text, rejected approvals, unsigned roots, and ungranted hashes cannot create available decisions.

Preservation key `TOP_LEVEL:3.2` now executes five nontrivial cases through the frozen commit's parsed `I_pri_rms` assignment and the corrected `fixed_ratio_primary_current` production API. The cases cover three turn ratios and multiple battery voltages; canonical primary current remains fixed for each physical ratio. The baseline and current paths no longer use the same local expression.

A settled no-load report now requires a fresh registry result emitted by `classify_settling`. That result has a producer provenance seal and exact dependencies on trusted ATS-v2, product-threshold, and observation artifacts. Copying its threshold ID/hash or constructing an equivalent `MaterialResult` does not establish `SETTLED`.

Finally, `ArtifactRegistry.validate_current` recursively checks every result dependency for freshness, current hashes, trust, and consumability. A fresh descendant of a stale or unavailable intermediate result is rejected. Adversarial regressions exercise these rules across comparison, thermal, qualification, control, publication, settling/no-load, and transitive result consumption.


## Closed trust-root hardening

The repository no longer contains a private signing exponent or any API that accepts caller artifacts and returns a newly signed or newly granted trust root. Trust verification now recognizes only two exact externally pre-signed manifests: an empty production root and one closed `SYNTHETIC_TEST_ONLY` fixture manifest whose immutable grant tuples are fixed by artifact ID, version, type, and content hash. Public-key material and fixed signatures can verify those manifests but cannot authorize a new artifact identity or a modified grant.

The synthetic fixture root preserves positive comparison, thermal, settlement, qualification, control, and publication contract tests without creating real evidence. Results produced from that root are non-gating; synthetic qualification and publication are rejected when requested as real claims, and synthetic comparison authorization cannot support a real comparison claim. Adversarial tests copy required owner/approval strings, calculate valid artifact hashes, inspect every repository constant, alter a preauthorized artifact, and recompute the root content hash; all attempts remain unauthorized because the fixed external signature and exact closed manifest no longer match.


## Exact-root and transitive synthetic-provenance closure

The final two adversarial findings are closed. Every registry entry point and every comparison, thermal, qualification, control, publication, and settlement decision now requires the exact `ArtifactRegistry` and exact `ArtifactTrustRoot` concrete types. The fixed manifest, signature, policies, grants, and closed dependency DAG are revalidated at each trust boundary. A subclass or duck-typed root that overrides validation or always returns authorization is rejected before it can resolve evidence or produce a decision.

`MaterialResult` and `GateAuthorization` now carry immutable `synthetic_provenance`. `material_result`, `derive_result`, recomputation, comparison authorization, thermal, settlement, qualification, controls, no-load reporting, and publication preserve it transitively and force every synthetic result to remain non-gating. Registry validation checks ancestry, so a non-synthetic wrapper around a synthetic result is invalid even when direct hashes and freshness appear current. Real comparison, qualification, and publication claims reject synthetic provenance rather than relying only on a caller marker.

Direct regressions inject an adversarial always-authorize trust-root subclass into all six decision families and attempt synthetic laundering through a wrapper result. The 52-test unit/property/integration suite, frozen exploration, enforced preservation (73/73 evaluated), all 16 acceptance gates, and complete firmware path/hash equality pass. No firmware source, configuration, or behavior changed.