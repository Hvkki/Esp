# Inverter Loss Calculation Corrections Bugfix Design

## Overview

This design implements `bugfix.md` as an evidence-preserving calculation, validation, and publication pipeline. It changes no firmware and invents no manufacturer, hardware, analog-reference, settling-threshold, thermal, qualification, or control evidence. Missing or invalid external artifacts remain local, safe, and non-gating as `PROVISIONAL` or `UNAVAILABLE`; they are never replaced by code defaults.

The implementation is artifact-driven and pure after validation:

```text
immutable artifact registry
  ├─ evidence catalog and adjudication history
  ├─ ATS-v2, product thresholds, digital oracle, optional analog MODREF
  ├─ residual applicability matrix
  ├─ legacy inventory and capture adapters
  ├─ allowed/excluded boundary inventory
  └─ firmware before/after manifest
                 |
                 v
canonical validation -> selection -> InverterInput -> pure inverter solver
                 |                              |
                 |                              v
                 |                  residual and no-load aggregation
                 |                              |
                 v                              v
       timing/analog acceptance       thermal/comparison/qualification
                 \                              /
                  -> MaterialResult dependency DAG -> publisher
                                                      |
                                           optional downstream-only
                                             system composition
```

Every artifact is addressed by immutable ID, version, and content hash. Approval identity and applicability are artifact data. Artifact absence never activates fallback constants or alternate policy.

## Glossary

- **Bug_Condition (C)**: Any input or artifact state that permits evidence overstatement, under-specified timing, false zeroing, stale consumption, boundary leakage, unsupported thermal/qualification claims, double counting, preservation gaps, or firmware drift.
- **Property (P)**: The required corrected behavior: a canonical, fresh, traced result or a safely propagated non-gating `PROVISIONAL`/`UNAVAILABLE` result.
- **Preservation**: Frozen comparison with real legacy behavior when available, or explicit `NO_BASELINE_BEHAVIOR` routing to fix checking.
- **EvidenceClass**: The source-strength classification, independent of conflict status.
- **ConflictStatus**: The immutable field-level conflict/adjudication lifecycle.
- **MaterialResult**: The mandatory availability, freshness, dependency, canonical-value, and trace envelope for every material value or status.
- **ATS-v2**: The sole approved numerical acceptance-policy artifact.
- **Digital timing oracle**: The hand-reviewed repository timing reference; it establishes digital events only.
- **Analog MODREF**: Independently reviewed per-field analog expected values and tolerances.
- **Residual source**: A uniquely owned typed source of actual differential excitation, stored energy, or heat.
- **Canonical equality**: Exact equality under requirement 2.42, never display or rounded equality.
- **Synthetic qualification**: Logic-only test evidence marked `SYNTHETIC_TEST_ONLY` throughout its dependency graph.
- **Canonical gate code**: The exact gate-specific `canonical_code` value from the applicable closed ineligibility enum; generic strings, aliases, and cross-gate codes are invalid.

## Bug Details

### Bug Condition

The bug manifests whenever the pipeline can consume unsupported evidence or policy, derive expectations from the implementation under test, erase actual residual behavior, contaminate the inverter boundary, overclaim thermal/control/qualification facts, double-count losses, or perform vacuous preservation.

**Formal Specification:**

```text
FUNCTION isBugCondition(input)
  INPUT: CalculationEvidenceAcceptanceOrPublicationRequest
  OUTPUT: boolean

  RETURN evidenceClassOrConflictContractInvalid(input)
      OR rawPendingEvidenceConsumed(input)
      OR MaterialResultLatticeOrFreshnessViolated(input)
      OR canonicalRepresentationInvalid(input)
      OR digitalTimingDiffersFromFixedOracle(input)
      OR unavailableAdjustedSrOrAggregateWasCoercedToEmptyZeroOrLossFree(input)
      OR analogOrSettlingDecisionUsesUnapprovedDefault(input)
      OR zeroCommandErasesActualResidual(input)
      OR residualApplicabilityOrOwnershipInvalid(input)
      OR legacyManifestOrCoverageInvalid(input)
      OR excludedFieldInfluencesInverter(input)
      OR thermalModeOrUniquenessClaimInvalid(input)
      OR comparisonGateArtifactCodeCardinalityPrerequisiteOrOrderInvalid(input)
      OR syntheticEvidenceSupportsRealClaim(input)
      OR firmwareAndHardwareEvidenceCoupled(input)
      OR firmwareManifestChanged(input)
      OR staleRoundedOrUnsupportedResultPublished(input)
END FUNCTION
```

```text
FUNCTION expectedBehavior(result)
  INPUT: MaterialResultGraph
  OUTPUT: boolean

  RETURN evidenceAndConflictDimensionsAreValid(result)
     AND allMaterialResultsFollowAvailabilityFreshnessLattice(result)
     AND allNumbersAndEventsAreCanonical(result)
     AND digitalAcceptanceMatchesAvailableOracleFieldsExactly(result)
     AND unavailableTimingSemanticsRemainExplicitNonZeroableAndNonGating(result)
     AND analogAndSettlingDecisionsUseOnlyApprovedArtifacts(result)
     AND residualSourcesAreClosedUniquelyOwnedAndNonoverlapping(result)
     AND inverterBoundaryIsExactlyIsolated(result)
     AND closedGateSpecificOutcomeAndProgressionContractsHold(result)
     AND thermalComparisonQualificationAndControlContractsHold(result)
     AND preservationUsesFrozenManifestRouting(result)
     AND firmwareBeforeAfterManifestsAreExactlyEqual(result)
END FUNCTION
```

### Examples

- Without direct exact-part manufacturer evidence, `IRL40SC209=0.60 mΩ` is only a `USER_SPECIFIED_TARGET`; it is not typical, maximum, guaranteed, measured, or direct.
- IRL40T209 `0.59/0.72 mΩ` records remain `RELATED_PART`; shared-die rationale cannot promote them to direct IRL40SC209 evidence.
- A raw conflicting `1.3/1.7 mΩ` row may omit class only while pending and cannot be selected, calculated, qualified, or published.
- At p=0, ideal phase is zero but repository timing has `LV_B_ON=1`; the one-tick residual is owned by `LEG_COMMAND_TICK_ASYMMETRY`, while analog current and loss remain unavailable absent independent evidence.
- At p=1 and p=0, the one-tick raw SR pulse does not justify a claimed dead-time-adjusted SR sequence: suppressed-pulse semantics, complete adjusted SR events/count, and complete aggregate adjusted events/count remain safety-relevant, non-gating `UNAVAILABLE`, never empty or zero.
- Missing ATS-v2 or approved product thresholds leaves the settled decision unavailable and the case in `TRANSITION`; no local threshold is selected.
- Multi-seed thermal agreement is not uniqueness, and a synthetic lower-voltage fixture is not real qualification evidence.
- A controlled zero-current/nonempty-conduction case uses only `canonical_code=INELIGIBLE_ZERO_IRMS`; an endpoint artifact with missing evidence or policy cannot use `INELIGIBLE_NO_POSITIVE_CURRENT_CASE` and leaves the gate unresolved.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Supported nonzero-load cases retain every applicable inverter-domain loss category and the fixed physical transformer-ratio current relation.
- Eligible bridge conduction remains `Irms²×2×RDS(on,Tj)/m`.
- Battery, charger, C-rate, and round-trip analysis remains downstream-only system composition.
- Missing evidence remains explicitly uncertain or unavailable; active and transition physics are not erased.
- Device qualification remains independent of RDS(on), and scenario comparisons retain the exact closed boundary tuple.
- Unvalidated outputs remain calculated/modelled, complete hot starts remain `HOT_START_TRANSIENT`, and the 0.60 mΩ target retains `USER_SPECIFIED_TARGET`. One finite in-domain `T_ref` is frozen before either gate; `CONTROLLED_THREEFOLD` and `ENDPOINT_SENSITIVITY` each retain exactly one distinct immutable pre-realistic-execution artifact and one gate-specific closed outcome, with no artifact reuse or additional gate-outcome artifact. Valid ineligibility provides a valid closed-union outcome authorizing progression only and never completion, pass, or success; downstream realistic-result availability is classified independently and cannot upgrade or relabel the ineligibility artifact. Every invalid artifact, code, predicate, prerequisite, or ordering state leaves the gate unresolved, blocks progression, and makes each MaterialResult dependent on that workflow authorization unavailable.

**Scope:**

Only the frozen `SpecBaselineOwner`-approved manifest determines applicability for top-level requirements 3.1–3.12 and every closed nested evidence/output key. `BASELINE_BEHAVIOR` compares eligible cases with immutable canonical observations. `NO_BASELINE_BEHAVIOR` prohibits a fabricated observation and requires eligible fix-check evidence. Missing mappings, runtime applicability decisions, adapter drift, non-frozen sampling, or zero evaluated cases fail preservation.

## Hypothesized Root Cause

1. Conflict and evidence strength were represented as one dimension rather than independent fields with class-specific metadata.
2. Material values lacked a single availability/freshness/canonical-trace envelope.
3. Timing acceptance was implementation-derived, assumed an even period and exact 50% duty, and allowed incomplete adjusted SR semantics or digital behavior to imply zero transitions, loss-free behavior, or analog behavior.
4. Ideal command and actual plant residuals were conflated, with no closed ownership map.
5. Legacy preservation inventories, adapters, schemas, applicability, and sampling were not frozen.
6. Upstream fields could enter inverter calculations through direct, transitive, default, cached, or environmental paths.
7. Snapshot, transient, and steady thermal modes shared unsuitable contracts, and seed agreement was overclaimed.
8. Realistic comparisons could precede the separate controlled-threefold and endpoint gates, share/reuse or multiply mutable/late gate artifacts, use open-ended ineligibility codes or mismatched predicates, recode invalid endpoint evidence/policy/fixed-input/candidate-set prerequisites as no-case ineligibility, misclassify progression as completion/pass/success, or overlap fixed-temperature and thermal attribution.
9. Synthetic qualification and firmware/hardware control evidence were allowed to leak across evidence boundaries.
10. Firmware source/config immutability was not proven by a closed exact before/after manifest.

## Correctness Properties

Property 1: Bug Condition - Conservative Corrected Pipeline

_For any_ input where `isBugCondition` is true, the fixed pipeline SHALL satisfy `expectedBehavior` or return correctly propagated, fresh, non-gating `PROVISIONAL`/`UNAVAILABLE` results without fabricated values, policy, evidence, or claims.

**Validates: Requirements 2.1–2.42**

Property 2: Preservation - Frozen Legacy Routing

_For any_ top-level or nested preservation key, exactly one immutable mapping SHALL route eligible cases to canonical `BASELINE_BEHAVIOR` comparison or non-fabricated `NO_BASELINE_BEHAVIOR` fix checking with complete machine-evaluable coverage.

**Validates: Requirements 2.13, 2.14, 3.1–3.12**

Property 3: Evidence and Conflict Independence

_For any_ evidence record, conflict SHALL not be an evidence class, class metadata SHALL match exactly one allowed class, and only a raw pending record may omit class; pending, rejected, and superseded records SHALL never be consumed.

**Validates: Requirements 2.1–2.5**

Property 4: Conflict Transition and Selection Integrity

_For any_ conflict history, only the four permitted transitions SHALL occur, terminal states SHALL remain terminal, exactly one eligible record SHALL be selected per tuple, and changing selection SHALL stale descendants before commit.

**Validates: Requirements 2.4, 2.5**

Property 5: MaterialResult Availability and Freshness

_For any_ material dependency graph and requested operation, `AVAILABLE` SHALL require satisfied local admissible-input/evidence and result-specific acceptance conditions plus a valid authorizing outcome from every applicable gate's required closed union; unavailable and provisional dependencies SHALL propagate monotonically, absent unbounded values SHALL be unavailable, and malformed, rejected, unresolved, or non-authorizing applicable gates SHALL make authorization-dependent results unavailable. A permitted ineligibility SHALL authorize only progression under requirements 2.25/2.38 without becoming completion, pass, or success; every downstream realistic-result availability SHALL be classified independently and SHALL NOT upgrade or relabel that artifact. Hash changes SHALL stale every descendant, and stale results SHALL not be consumed.

**Validates: Requirements 2.5, 2.34, 2.41**

Property 6: Canonical Numeric and Event Equality

_For any_ exact decision, every available canonical numeric or event representation SHALL be compared with its exact scope and count, simultaneous events SHALL follow the closed order, unavailable lists/counts SHALL retain explicit absence rather than fabricated canonical emptiness, and rounded/display values SHALL never participate.

**Validates: Requirements 2.18, 2.35, 2.42**

Property 7: Repository Digital Oracle

_For any_ p=10, p=1, or p=0 acceptance vector, `N=2285`, `H=1142`, the 1142/1143 odd-period asymmetry, `q=pH/100`, half-up `k`, every comparator, and every available event list/count SHALL match the fixed oracle exactly, including 16 adjusted individual events at p=10 and `SR_B_OFF` before `SR_B_ON` at tick 2284 for p=1/p=0; unavailable adjusted SR or complete aggregate behavior SHALL remain explicitly unavailable and SHALL never become empty, zero-transition, zero-switching, or loss-free.

**Validates: Requirements 2.6–2.9, 2.36**

Property 8: Analog and Policy Independence

_For any_ analog or settling decision, only applicable independently approved expected values, tolerances, ATS-v2, and product thresholds SHALL gate; missing artifacts SHALL make only affected decisions unavailable and non-gating without defaults.

**Validates: Requirements 2.8, 2.9, 2.11, 2.12, 2.35**

Property 9: Zero-Command Residual Conservation

_For any_ p=0 case, only commanded ideal transfer/excitation SHALL be zero; the one-tick `LV_B_ON` guard asymmetry SHALL have unique `LEG_COMMAND_TICK_ASYMMETRY` ownership, while unavailable adjusted SR semantics, gate-transition totals, pulses, current, volt-seconds, flux, energy, and loss SHALL remain unavailable until established and SHALL never be inferred as zero.

**Validates: Requirements 2.10, 2.32, 2.36, 2.37**

Property 10: Closed Residual Applicability and Ownership

_For any_ supported topology/control matrix row, each required source SHALL occur exactly once, prohibited sources SHALL not occur, initiating injection SHALL precede remaining stored-energy decay ownership, and uncertainty SHALL not count as loss.

**Validates: Requirements 2.10, 2.37**

Property 11: Settling Classification

_For any_ zero-command observation, `SETTLED` SHALL be available only after every approved W, RMS, per-period/cumulative volt-second, and end-energy comparison passes; absent policy SHALL retain `TRANSITION` and residual results.

**Validates: Requirements 2.11, 2.12, 2.35**

Property 12: Exact Inverter Boundary and Scenario Equivalence

_For any_ excluded schema path, each exact one-field mutation to at least two valid values SHALL leave all canonical inverter outputs and traces invariant, and compared scenarios SHALL have exactly equal closed boundary tuples.

**Validates: Requirements 2.17–2.19, 3.8**

Property 13: Thermal Mode Contracts

_For any_ thermal request, cold snapshots SHALL require physical temperatures but not Cth, dynamics SHALL require evidenced positive Cth and supported-domain trajectories, and steady state SHALL exclude Cth and remain exactly invariant to its mutation.

**Validates: Requirements 2.20–2.22**

Property 14: Thermal Seed and Uniqueness Semantics

_For any_ bounded steady-state solve, the exact lower/midpoint/upper seed set SHALL establish at most multi-seed agreement, while `UNIQUE` SHALL require an independently verified complete-domain one-root certificate.

**Validates: Requirements 2.23, 2.24**

Property 15: Ordered Device Comparison and Exclusive Attribution

_For any_ realistic device comparison, one finite in-domain `T_ref` with units SHALL be frozen before either mandatory gate executes; exactly one distinct immutable pre-realistic-execution artifact SHALL exist for each of `CONTROLLED_THREEFOLD` and `ENDPOINT_SENSITIVITY`, with no identity reuse and no additional gate-outcome artifact; and each artifact SHALL contain exactly one outcome from its gate-specific closed union. Controlled ineligibility SHALL use exactly one canonical code from `INELIGIBLE_ZERO_IRMS`, `INELIGIBLE_EMPTY_CONDUCTION_INTERVAL`, or `INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL` iff the corresponding requirement-2.30 predicate combination holds and every other requirement-2.29 precondition passes. Endpoint ineligibility SHALL use exactly `INELIGIBLE_NO_POSITIVE_CURRENT_CASE` only after every non-case-set endpoint, evidence, policy, fixed-input, and closed-candidate-set precondition passes and no candidate has both finite positive current and nonempty conduction. Every valid ineligibility SHALL record all and only code-corresponding unsatisfied predicates, one specific reason, evaluated-case count zero, and exactly one each of `completion_claim=false`, `pass_claim=false`, and `success_claim=false`; as a valid closed-union outcome it MAY authorize progression only and SHALL never be completion, pass, or success. Any wrong, generic, alias, unrecognized, or predicate-mismatched code; malformed, missing, duplicate, reused, mutable, aliased, or late artifact; invalid prerequisite or outcome cardinality; or malformed ineligibility SHALL leave the gate unresolved, block progression, and make every MaterialResult dependent on that workflow authorization `UNAVAILABLE`. After both artifacts provide valid outcomes authorizing progression, each realistic-result availability SHALL be classified independently from its own admissible inputs/evidence, dependencies, local acceptance conditions, and applicable workflow authorizations, without upgrading or relabeling an ineligibility artifact; fixed-temperature and thermal contributions SHALL have mutually exclusive owners and reconcile.

**Validates: Requirements 2.25, 2.26, 2.29–2.31, 2.38, 3.11**

Property 16: Qualification Evidence Isolation

_For any_ qualification graph, synthetic markers SHALL propagate and prevent real claims, while real gating SHALL require complete exact-device limits, stress, derating, conditions, and separate passing checks.

**Validates: Requirements 2.15, 2.16, 2.39**

Property 17: Orthogonal Control Evidence

_For any_ control behavior, firmware implementation and hardware measurement statuses SHALL derive only from their respective complete evidence bundles and SHALL never imply one another.

**Validates: Requirements 2.27, 2.28**

Property 18: Firmware Immutability

_For any_ bugfix run, the closed before/after firmware path sets and hashes SHALL be exactly equal for the same named commit/tree baseline; any addition, removal, rename, or hash change SHALL fail acceptance.

**Validates: Requirements 2.40**

Property 19: No-Load Completeness

_For any_ no-load report, every closed category SHALL carry independent applicability, basis, availability, context, provenance, and uncertainty, and loaded constants SHALL not be promoted to settled no-load facts.

**Validates: Requirements 2.32, 2.33**

Property 20: Publication Safety

_For any_ publication, all material results SHALL be fresh, canonical, fully traced, and correctly status-labelled; stale, rounded-input, mixed-synthetic, unsupported, or fabricated-evidence claims SHALL be rejected.

**Validates: Requirements 2.34, 2.35, 2.41, 2.42**

## Fix Implementation

### Core Semantic Contracts

### Canonical values, events, and `MaterialResult`

Every value or status used directly or transitively by a calculation, acceptance decision, qualification decision, headline, or publication is a `MaterialResult`; there is no exception based on data type, visibility, magnitude, or rounding.

```text
enum Availability { AVAILABLE, PROVISIONAL, UNAVAILABLE }
enum Freshness    { FRESH, STALE }

type CanonicalNumber = {
  numeric_type,
  dimension,
  canonical_unit,
  shape,
  element_order,
  representation:
      REDUCED_RATIONAL(numerator_integer, denominator_positive_integer)
    | FINITE_FLOAT_BITS(format, exact_bit_pattern)
}

type CanonicalEvent =
  (tick, event_class, device_id, edge, source_artifact_hash)

type MaterialResult<T> = {
  availability: Availability,
  freshness: Freshness,
  dependency_record_ids: CanonicallyOrderedSet<RecordId>,
  dependency_hashes: CanonicallyOrderedMap<RecordId, Hash>,
  computation_artifact_id,
  computation_artifact_version,
  computation_artifact_hash,
  canonical_value: T | EXPLICIT_ABSENCE(missing_fields),
  applicability,
  uncertainty_or_bound?,
  trace_identity
}
```

Canonical numbers include type, dimension, canonical unit, shape, and order. A rational is reduced; a float retains its exact finite bit pattern. NaN and infinities are invalid, and signed zero normalizes to positive zero. Canonical numeric equality compares the complete representation, never a display string.

Canonical event equality compares complete ordered tuple sequences and counts. Events at one tick sort by event class `OFF`, then `DEADTIME_EXPIRY`, then `ON`, then ascending stable device ID within the class. A noncanonical number, ambiguous event order, missing source hash, or unspecified aggregate source set makes only the affected decision `UNAVAILABLE`.

`AVAILABLE` means the MaterialResult's local required admissible inputs/evidence and result-specific acceptance conditions are satisfied, and each applicable workflow gate provides a valid outcome from its required closed union authorizing the requested operation. It does not mean that every gate outcome is a pass. A valid ineligibility outcome under requirements 2.25 and 2.38 may authorize progression to realistic comparison, but remains an ineligibility artifact with `completion_claim=false`, `pass_claim=false`, and `success_claim=false`. The downstream realistic result is classified independently from its own local inputs/evidence, dependencies, result-specific acceptance conditions, and applicable workflow authorizations; its availability never upgrades, relabels, or otherwise changes the ineligibility artifact. A malformed, rejected, unresolved, or operation-inapplicable gate authorization blocks progression and makes each MaterialResult dependent on that authorization `UNAVAILABLE`. `PROVISIONAL` requires an evaluable finite value or conservative finite bound but lacks required direct evidence or final adjudication. `UNAVAILABLE` means no evaluable admissible value exists because a required value, method, item of evidence, applicability decision, policy, or workflow authorization is absent or invalid. Explicit absence without an evaluable bound can never be provisional.

Availability and freshness form an orthogonal product lattice. Workflow authorization is validated before local availability classification and never mutates a gate outcome. `resultSpecificAcceptanceConditionsSatisfied` means that the contract for producing and classifying that MaterialResult was satisfied; it does not require a domain decision to pass, so a correctly evaluated failed comparison may itself be an `AVAILABLE` result carrying failure:

```text
FUNCTION derive(requiredResults, localEvaluation,
                applicableWorkflowGates, requestedOperation)
  authorizations := []
  FOR EACH gate IN applicableWorkflowGates
    outcome := validateExactlyOneOutcomeFromRequiredClosedUnion(gate)
    IF outcome is MALFORMED OR REJECTED OR UNRESOLVED
      RETURN MaterialResult(UNAVAILABLE, deriveFreshness(requiredResults),
                            INVALID_WORKFLOW_AUTHORIZATION(gate), ...)
    END IF

    authorization := authorizationFor(outcome, requestedOperation)
    IF authorization != AUTHORIZED
      RETURN MaterialResult(UNAVAILABLE, deriveFreshness(requiredResults),
                            OPERATION_NOT_AUTHORIZED(gate, requestedOperation), ...)
    END IF

    IF outcome is PERMITTED_INELIGIBILITY
      REQUIRE requestedOperation = PROGRESS_TO_REALISTIC_COMPARISON
      REQUIRE outcome.completion_claim = false
      REQUIRE outcome.pass_claim = false
      REQUIRE outcome.success_claim = false
      // Record authorization only; never rewrite or upgrade the outcome artifact.
    END IF
    APPEND authorization TO authorizations
  END FOR

  IF localEvaluation has no admissible finite value or finite conservative bound
     OR NOT localEvaluation.resultSpecificAcceptanceConditionsSatisfied
     OR EXISTS r IN requiredResults: r.availability = UNAVAILABLE
    availability := UNAVAILABLE
  ELSE IF localEvaluation lacks required direct/final evidence
       OR EXISTS r IN requiredResults: r.availability = PROVISIONAL
    availability := PROVISIONAL
  ELSE
    availability := AVAILABLE
  END IF

  freshness := FRESH only if every dependency ID/hash still matches
  RETURN MaterialResult(availability, freshness, authorizations, ...)
END FUNCTION
```

When the requested operation is realistic-comparison progression, a valid completed outcome or a permitted ineligibility outcome can supply the required authorization according to its closed contract. The realistic comparison then receives a separate `derive` call for each downstream MaterialResult; no downstream `AVAILABLE`, `PROVISIONAL`, or `UNAVAILABLE` classification is copied back to either gate artifact.

Any dependency-hash change marks every transitive descendant `STALE` before a changed selection becomes visible. A stale result is blocked from calculation consumption, acceptance, qualification, headline use, and publication regardless of availability. Recalculation creates a new trace identity and sets freshness to `FRESH`. Displayed, formatted, or rounded data is never stored as or converted back into an input.

`relevant power` is the absolute value of the full-precision signed aggregate being reconciled before display rounding. `relevant thermal loss` is the full-precision nonnegative sum of exactly the heat-source terms in the applicable thermal balance equations; a negative term or a term absent from those equations is inadmissible.

### Evidence class and conflict lifecycle

Conflict is not an evidence class.

```text
enum EvidenceClass {
  USER_SPECIFIED_TARGET,
  DIRECT_MANUFACTURER,
  RELATED_PART,
  DERIVED_ESTIMATE,
  MEASURED
}

enum ConflictStatus {
  NONE,
  PENDING,
  ACCEPTED_FOR_FIELD,
  REJECTED_FOR_FIELD,
  SUPERSEDED
}

type EvidenceRecord<T> = RawPending<T> | ClassifiedRecord<T>

type RawPending<T> = {
  record_kind: RAW_UNRESOLVED_PENDING,
  record_id,
  subject?, field, value?, unit?, applicability?,
  evidence_class: ABSENT,
  conflict_status: PENDING,
  every_available_raw_source_field,
  explicit_source_level_absence_markers,
  immutable_transition_log,
  trace_links
}

type ClassifiedRecord<T> = {
  record_kind: CLASSIFIED,
  record_id,
  subject, field, value, unit, applicability,
  evidence_class: EvidenceClass,
  conflict_status: ConflictStatus,
  class_metadata: MetadataFor<evidence_class>,
  immutable_transition_log,
  trace_links
}
```

A `RawPending` record is the only record that may omit `EvidenceClass`, and it is never selectable, consumable, qualifying, or publishable. Every classified record has exactly one class and exactly the matching metadata variant:

- `USER_SPECIFIED_TARGET` requires subject, field, value/unit, assertion artifact ID/version/locator/hash, and VGS, ID, Tj-or-Tc, and pulse-or-measurement condition each exactly `VALUE(value,unit)` or `ABSENT`.
- `DIRECT_MANUFACTURER` requires exact subject, manufacturer, document ID/version/hash, page and table-or-figure locator, rating class, and those four source-condition fields each exactly `STATED(value,unit)` or `NOT_STATED_BY_SOURCE`.
- `RELATED_PART` requires all direct-manufacturer metadata, exact related subject, and an explicit relationship rationale. Shared-die inference cannot promote it to direct evidence.
- `DERIVED_ESTIMATE` requires derivation artifact ID/version/hash, formula or algorithm, all dependency record IDs, applicability, and uncertainty or bound.
- `MEASURED` requires test artifact ID/version/hash, instrument IDs and calibration versions, measurement boundary, conditions, sample coverage, method, and uncertainty.

No validator fills missing metadata. Specifically, `IRL40SC209=0.60 mΩ` without direct exact-part manufacturer evidence is stored only as `USER_SPECIFIED_TARGET` with a user assertion artifact and is never labeled typical, maximum, guaranteed, directly evidenced, or measured. `0.59 mΩ` and `0.72 mΩ` from `IRL40T209` remain `RELATED_PART` records with exact T209 metadata. Conflicting `1.3 mΩ`, `1.7 mΩ`, or other source rows remain separate raw records until classified and adjudicated.

The exact transition graph is:

```text
NONE -> PENDING
PENDING -> ACCEPTED_FOR_FIELD
PENDING -> REJECTED_FOR_FIELD
ACCEPTED_FOR_FIELD -> SUPERSEDED
```

`REJECTED_FOR_FIELD` and `SUPERSEDED` are terminal. Every transition appends adjudicator, timestamp, reason, and cited artifact IDs to immutable history and creates a new record version; all other transitions fail. A new record starts `NONE` only if no conflict is known, otherwise `PENDING`. Later evidence for a terminal record creates a new record.

Exactly one record is selected for each `(subject, field, applicability)` tuple. Its status is `NONE` when undisputed or `ACCEPTED_FOR_FIELD` after adjudication; at most one non-superseded record may be accepted. Pending, rejected, and superseded records cannot be selected or consumed.

```text
FUNCTION changeSelection(tuple, candidate, citedEvidence)
  VALIDATE candidate class metadata and exact field/applicability support
  VALIDATE any status transition against the closed graph
  VALIDATE candidate is NONE or ACCEPTED_FOR_FIELD
  VALIDATE resulting tuple has exactly one selection and at most one active accepted record

  affected := all MaterialResults transitively dependent on
              tuple, old selection, candidate, or changed cited records
  MARK affected STALE before committing the selection event
  APPEND immutable selection/adjudication event; preserve all prior records
  COMMIT selection
  RECOMPUTE affected from canonical inputs with new trace identities
END FUNCTION
```

Attaching direct exact-part evidence changes only fields explicitly supported by that evidence. Unresolved evidence propagates through the `MaterialResult` lattice rather than producing a fabricated value.

### ATS-v2, product thresholds, and analog MODREF

`ATS-v2` is the sole numerical acceptance-policy artifact. It is usable only when ID, version, immutable hash, `InverterOwner` approval, expiration, and decision applicability all validate. Absence, invalidity, hash mismatch, expiration, or out-of-scope use makes only the affected numerical decision `UNAVAILABLE` and non-gating. Code cannot supply, tune, or default a replacement.

The complete available normative rules are exactly:

1. exact canonical equality for boundary outputs, statuses, trace identities, dependency sets, and zero-conduction loss;
2. exact canonical tick/comparator/event identity, count, and order for every available digital-timing value or list, while an explicitly unavailable adjusted SR or aggregate value/list/count remains non-gating and is never interpreted as empty, zero, omitted, or loss-free;
3. relative error `≤1e-9` for eligible exactly-threefold channel-conduction scaling;
4. absolute power-reconciliation error `≤max(0.01 W, 1e-6 × relevant power)`;
5. corresponding-node multi-seed difference `≤0.1 °C`, with every balance residual `≤max(0.01 W, 1e-6 × relevant thermal loss)`; and
6. absolute resistance-to-source mismatch `≤1 µΩ`.

No other numerical tolerance is available. Every decision consumes canonical full-precision data.

Product values `Ires,max`, `VSperiod,max`, `VScum,max`, and `Estored,max` are each an exact finite value/unit or an approved finite closed interval `[minimum,maximum]` with common unit. `W` is an exact finite duration or approved finite closed interval `[Wmin,Wmax]`, with `Wmin≥max(10T,1 ms)`. A separate immutable product-threshold artifact approved by `InverterOwner` defines W selection, conservative threshold-interval endpoint selection, sample population/coverage, RMS window and estimator, integration method and error bound, waveform alignment and tolerance, and the closed stored-energy source set. These product values and rules remain unavailable until approved; they are never firmware-derived or code defaults.

Each analog MODREF field is independently:

```text
EXPECTED(value, unit, tolerance_formula_or_interval, applicability,
         artifact_id, version, hash, IndependentModelReviewer_approval)
| UNAVAILABLE(missing_fields)
```

There is no third state. The implementation-independent analog artifact must cover primary/secondary polarity, DC-terminal voltage, load model/value, initial inductor/transformer current, a closed initial stored-energy source set, carrier state, and enabled power-stage states. It supplies separate records for intentional transfer, differential voltage, volt-seconds, RMS current, circulating current, flux, stored energy, and loss. Availability of one field implies nothing about another. Without approved analog expected values and tolerances, all analog electrical fields remain `UNAVAILABLE` and non-gating. The digital oracle never validates analog transfer, current, energy, or loss.

### Repository-Grounded Digital Timing Oracle

General commanded timing defines phase magnitude `p∈[0%,100%]` as a percentage of the explicitly defined half count `H`. For a timing artifact with period count `N`, `H=floor(N/2)`, and `Δt`, the ideal displacement is `q=pH/100` ticks and the ideal time displacement is `φ=qΔt`, with `0≤q≤H`. Polarity is independent: `s=+1` makes leg A lead leg B by `φ`, while `s=-1` makes leg B lead leg A. The raw leading high interval is `H` ticks and its complementary interval is `N-H` ticks. An odd `N` therefore has real asymmetric intervals; no exact `T/2` edge or exact-50%-duty premise is inferred.

```text
FUNCTION realizePhase(p, N)
  REQUIRE 0 <= p <= 100
  H := floor(N / 2)
  q := p * H / 100
  k := clamp(floor(q + 0.5), 0, H)
  RETURN (H, q, k)
END FUNCTION
```

An exact half-tick tie rounds upward. Comparator guards, edge-specific quantization, dead time, and implementation residuals are represented separately from `q` and `φ`. A general timing artifact is supported only when it explicitly defines `H`, both raw interval lengths, phase quantization, and odd-`N` behavior.

The immutable, hand-reviewed oracle is approved by `InverterOwner`, independent of the implementation under test, and bound by ID/version/hash to the named source/config baseline hashes and locators from the firmware manifest. Its exact compiled constants are:

```text
clock                  = 160000000 Hz
nominal carrier macro  = 70000 Hz
N                      = floor(160000000 / 70000) = 2285 (odd)
H                      = floor(2285 / 2) = 1142
raw interval lengths   = 1142 / 1143 ticks
Δt                     = 1/160000000 s
T                      = 2285/160000000 s exactly
actual carrier f       = 160000000/2285 = 32000000/457 Hz exactly
                         ≈ 70021.881838 Hz
nominal label          = "70 kHz" only
LV dead time           = 10 ticks
SR dead time           = 16 ticks
SR lead/trail          = 8/8 ticks
minimum window         = 18 ticks
SR enable              iff k > 34
```

Comparator identities, in order, are exactly:

```text
LV_A_ON_RESERVED, LV_A_OFF, LV_B_ON, LV_B_OFF,
SR_A_ON_RESERVED, SR_A_OFF, SR_B_ON, SR_B_OFF
```

The SR triplet is exactly `SR_A_OFF/SR_B_ON/SR_B_OFF`. Each reserved comparator value is `1`, while its corresponding raw ON edge is TEZ at tick 0. Every vector stores `p`, `s`, `q`, `φ`, `k`, `N`, `H`, both raw interval lengths, all constants, comparator identities/values, each available event list/count, explicit unavailable records, dead-time ticks, minimum-window and enable rules, source baseline hashes, artifact locators, and oracle ID/version/hash. The vectors below are `s=+1`; `s=-1` remains unavailable unless a separately hand-reviewed complete oracle exists.

```text
enum TimingListStatus<T> {
  AVAILABLE_EXACT(value: T),
  UNAVAILABLE(missing_fields: NonEmptySet)
}

type DigitalTimingVector = {
  p, s, q, phi, k, N, H,
  raw_high_interval_ticks: 1142,
  raw_complement_interval_ticks: 1143,
  comparators: AVAILABLE_EXACT<OrderedComparatorList>,
  raw_events: AVAILABLE_EXACT<CanonicalEventListAndCount>,
  adjusted_lv_events: AVAILABLE_EXACT<CanonicalEventListAndCount>,
  sr_deadtime_adjusted_suppressed_pulse: TimingListStatus<SuppressedPulseSemantics>,
  complete_adjusted_sr_events: TimingListStatus<CanonicalEventListAndCount>,
  complete_aggregate_adjusted_events: TimingListStatus<CanonicalEventListAndCount>
}
```

`UNAVAILABLE` is a first-class safety-relevant state, not an empty collection. Serialization, aggregation, comparison, and publication must preserve its reason and dependencies; no caller may coerce it to count zero, no transitions, no switching, or loss-free behavior.

### Exact p=10 vector

`q=10×1142/100=114.2`, `φ=114.2Δt`, and half-up realization gives `k=114`.

```text
comparators = (1,1142,114,1256,1,106,1150,1248)
raw HI intervals = LV_A[0,1142), LV_B[114,1256),
                   SR_A[0,106), SR_B[1150,1248)
raw events, canonical order:
  0:    LV_A_HI_ON, SR_A_HI_ON
  106:  SR_A_HI_OFF
  114:  LV_B_HI_ON
  1142: LV_A_HI_OFF
  1150: SR_B_HI_ON
  1248: SR_B_HI_OFF
  1256: LV_B_HI_OFF
raw count = 8
complete adjusted events, canonical order:
  0:    LV_A_LO_OFF, SR_A_LO_OFF
  10:   LV_A_HI_ON
  16:   SR_A_HI_ON
  106:  SR_A_HI_OFF
  114:  LV_B_LO_OFF
  122:  SR_A_LO_ON
  124:  LV_B_HI_ON
  1142: LV_A_HI_OFF
  1150: SR_B_LO_OFF
  1152: LV_A_LO_ON
  1166: SR_B_HI_ON
  1248: SR_B_HI_OFF
  1256: LV_B_HI_OFF
  1264: SR_B_LO_ON
  1266: LV_B_LO_ON
complete adjusted individual event count = 16
```

The tick-0 group contains two individual events; the remaining 14 tick groups each contain one, so the complete adjusted count is 16 rather than the number of displayed tick groups.

### Exact p=1 vector

`q=1×1142/100=11.42`, `φ=11.42Δt`, and half-up realization gives `k=11`; SR is disabled.

```text
comparators = (1,1142,11,1153,1,1,2284,2284)
raw HI intervals = LV_A[0,1142), LV_B[11,1153)
raw SR edge identities, canonical declaration =
  SR_A_ON@0, SR_A_OFF@1, SR_B_OFF@2284, SR_B_ON@2284
raw events, canonical order:
  0:    LV_A_HI_ON, SR_A_HI_ON
  1:    SR_A_HI_OFF
  11:   LV_B_HI_ON
  1142: LV_A_HI_OFF
  1153: LV_B_HI_OFF
  2284: SR_B_HI_OFF, SR_B_HI_ON
raw count = 8
adjusted LV events, canonical order:
  0:    LV_A_LO_OFF
  10:   LV_A_HI_ON
  11:   LV_B_LO_OFF
  21:   LV_B_HI_ON
  1142: LV_A_HI_OFF
  1152: LV_A_LO_ON
  1153: LV_B_HI_OFF
  1163: LV_B_LO_ON
adjusted LV event count = 8
raw SR_A pulse [0,1) is one tick and shorter than SR dead time 16
SR_DEADTIME_ADJUSTED_SUPPRESSED_PULSE =
  UNAVAILABLE(missing independent ESP-IDF peripheral-semantics artifact or
              measurement establishing whether the delayed high pulse is
              cancelled and what low-side transitions occur)
complete adjusted SR event list/count = UNAVAILABLE(same missing evidence)
complete aggregate adjusted event list/count = UNAVAILABLE(same missing evidence)
```

### Exact p=0 vector and residual ownership

`q=0`, `φ=0`, and ideal `k=0`; SR is disabled. The implementation comparator guard separately sets `LV_B_ON=1`.

```text
comparators = (1,1142,1,1142,1,1,2284,2284)
raw HI intervals = LV_A[0,1142), LV_B[1,1142)
raw SR edge identities, canonical declaration =
  SR_A_ON@0, SR_A_OFF@1, SR_B_OFF@2284, SR_B_ON@2284
raw events, canonical order:
  0:    LV_A_HI_ON, SR_A_HI_ON
  1:    SR_A_HI_OFF, LV_B_HI_ON
  1142: LV_A_HI_OFF, LV_B_HI_OFF
  2284: SR_B_HI_OFF, SR_B_HI_ON
raw count = 8
adjusted LV events, canonical order:
  0:    LV_A_LO_OFF
  1:    LV_B_LO_OFF
  10:   LV_A_HI_ON
  11:   LV_B_HI_ON
  1142: LV_A_HI_OFF, LV_B_HI_OFF
  1152: LV_A_LO_ON, LV_B_LO_ON
adjusted LV event count = 8
raw SR_A pulse [0,1) is one tick and shorter than SR dead time 16
SR_DEADTIME_ADJUSTED_SUPPRESSED_PULSE =
  UNAVAILABLE(missing independent ESP-IDF peripheral-semantics artifact or
              measurement establishing whether the delayed high pulse is
              cancelled and what low-side transitions occur)
complete adjusted SR event list/count = UNAVAILABLE(same missing evidence)
complete aggregate adjusted event list/count = UNAVAILABLE(same missing evidence)
```

Every `*_OFF` in an available adjusted list has class `OFF`; every available delayed `*_ON` has class `DEADTIME_EXPIRY`. Raw edge events use `OFF` or `ON`. Simultaneous events use the closed ordering, including `SR_B_OFF` before `SR_B_ON` at tick 2284 for p=1 and p=0; stable device ID breaks remaining ties. No implied event exists outside an available list's stated scope and count.

At p=0, `LV_B_ON=1` is actual one-tick implementation asymmetry, not ideal phase and not a consequence of the 1142/1143 interval asymmetry. For every supported repository p=0 topology/control row where this firmware baseline applies, `LEG_COMMAND_TICK_ASYMMETRY` is `REQUIRED`, and exactly one source record owns it. Oracle validation emits only available canonical digital provenance. It does not establish the unavailable adjusted SR behavior or any analog waveform, current, energy, gate-transition total, switching loss, or gate loss.

```text
FUNCTION acceptDigital(actual, oracle)
  REQUIRE valid oracle identity, approval, baseline hashes, and applicability
  REQUIRE exact N=2285, H=1142, interval lengths 1142 and 1143
  REQUIRE exact clock, actual rational carrier, T, p, s, q, phi, k
  REQUIRE exact dead-time, minimum-window, enable, comparator identity/value fields

  FOR EACH oracle timing field or list
    IF oracle field = AVAILABLE_EXACT(expected)
      REQUIRE actual field is AVAILABLE_EXACT
      REQUIRE exact canonical value or event sequence and individual count
    ELSE IF oracle field = UNAVAILABLE(reason)
      REQUIRE actual field remains UNAVAILABLE with reason and dependencies
      REJECT empty list, count zero, inferred zero transition/switching/loss,
             omitted field, or loss-free substitution
    END IF
  END FOR

  RETURN AVAILABLE only for the compared available digital scope;
         retain unavailable SR/aggregate fields as safety-relevant non-gating results
END FUNCTION
```

### Typed Residual Sources and Settled Zero Command

```text
enum ResidualSourceType {
  LEG_COMMAND_TICK_ASYMMETRY,
  DEADTIME_ASYMMETRY,
  PROPAGATION_DRIVER_MISMATCH,
  DEVICE_TRANSITION_MISMATCH,
  SR_COMMUTATION,
  STORED_ENERGY_DECAY,
  OTHER_DECLARED(nonempty_subtype)
}

enum MatrixCell { REQUIRED, NOT_APPLICABLE(reason) }
type PhysicalField<T> = VALUE(T) | NA(reason) | UNAVAILABLE(missing_fields)

type ResidualSourceRecord = {
  case_id,
  ownership_id,
  source_type: ResidualSourceType,
  provenance_artifact_id,
  provenance_artifact_version,
  provenance_artifact_hash,
  source_waveform: PhysicalField<CanonicalWaveformWithUnitsTimebaseAlignment>,
  energy_initial: PhysicalField<CanonicalEnergy>,
  energy_final: PhysicalField<CanonicalEnergy>,
  energy_change: PhysicalField<CanonicalEnergy>,
  heat_loss_contribution: PhysicalField<NonnegativeCanonicalPowerOrEnergy>,
  uncertainty_or_conservative_bound,
  availability: Availability,
  applicability_matrix_id,
  applicability_matrix_version,
  applicability_matrix_hash
}
```

Each `ownership_id` is unique within a case, each record has exactly one type, and every nonempty `OTHER_DECLARED` subtype is unique within that case. `NA(reason)` is legal only when the field is physically undefined for that type; a required but unevaluable physical field is `UNAVAILABLE`, never `NA`.

An immutable, versioned, `InverterOwner`-approved closed matrix contains one row for every Cartesian product of supported topology, p-state (`NONZERO`, `ZERO_TRANSITION`, `ZERO_SETTLED`), gate state, and SR state, and one column for every closed source type, including each approved `OTHER_DECLARED` subtype. Every cell is exactly `REQUIRED` or `NOT_APPLICABLE(reason)`. Unknown rows/columns, incomplete products, and post-approval mutation fail configuration.

```text
FUNCTION aggregateResiduals(case, matrix, records)
  row := matrix.exactRow(case.topology, case.p_state,
                         case.gate_state, case.sr_state)
  REQUIRE row contains every closed source column
  REQUIRE case-unique ownership IDs and OTHER_DECLARED subtypes

  FOR EACH source column
    IF cell = REQUIRED
      REQUIRE exactly one record of that source type
      REQUIRE physically required fields are not NA
    ELSE
      REQUIRE no record of that source type
    END IF
  END FOR

  initiating := all REQUIRED records except STORED_ENERGY_DECAY
  ASSIGN externally supplied waveform and energy injection exactly once
           to initiating owners
  remaining_start_energy := case_start_energy
                            minus energy already owned by initiating sources
  ASSIGN STORED_ENERGY_DECAY only decay of remaining pre-existing energy
  REQUIRE no waveform interval, energy, or heat term overlaps ownership

  FOR EACH aggregate field IN {waveform, energy, heat_loss}
    requiredFields := corresponding fields from every applicable REQUIRED owner
    IF any required field has no evaluable value or bound
      result := UNAVAILABLE
    ELSE
      sum only canonical physical values; never sum uncertainty as physical loss
      result := PROVISIONAL if any required input is provisional,
                otherwise AVAILABLE
    END IF
    EMIT field-specific MaterialResult and propagate it to every dependent aggregate
  END FOR
END FUNCTION
```

Missing required records, duplicate ownership/subtypes, forbidden records, matrix incompleteness, or overlap fails residual acceptance. If a finite evaluable bound survives, the affected result can be provisional; otherwise it is unavailable. Uncertainty is never physical loss.

At p=0, only commanded ideal transfer and commanded ideal differential primary excitation are forced to exact zero. Actual differential pulses, residual RMS current, differential volt-seconds, flux, stored energy, and losses come only from applicable typed residual records. Unknown residuals are never replaced by zero.

```text
FUNCTION classifyZeroCommand(case, ats, thresholds, observations)
  REJECT caller-provided settled flags
  residuals := aggregateResiduals(case, approvedMatrix, records)

  IF ATS-v2 or threshold artifact or required observation/model/measurement
     is absent, invalid, non-finite, hash-mismatched, unapproved,
     locally chosen, expired, or outside applicability
    RETURN state=TRANSITION,
           settled_decision=MaterialResult(UNAVAILABLE,FRESH,EXPLICIT_ABSENCE),
           residuals retained, gating=false, exact gap diagnostics
  END IF

  SELECT contiguous W by approved rule
  REQUIRE W >= max(10*T, 1 ms)
  Ires := approved RMS method over approved sample coverage
  VSperiod[j] := approved absolute differential volt-seconds
                 for every carrier period in W
  VScum := approved absolute cumulative differential volt-seconds over W
  Eend := end-of-W total over exactly the approved closed energy-source set

  COMPARE exact limits directly and interval limits by approved conservative rule
  IF every comparison passes
    RETURN state=SETTLED, settled_decision=AVAILABLE, residuals retained
  ELSE
    RETURN state=TRANSITION, settled_decision=AVAILABLE failed comparison,
           residuals retained, exact failed comparisons
  END IF
END FUNCTION
```

An exceeded available limit is a recorded failure, not unavailable. Missing policy makes only the affected settled decision unavailable and non-gating; the case remains `TRANSITION`, actual/provisional residuals remain visible, and settled no-load behavior cannot be published.

Every no-load report has exactly these categories:

```text
INTENTIONAL_IDEAL_DIFFERENTIAL_TRANSFER
UNINTENDED_DIFFERENTIAL_RESIDUAL
COMMON_MODE_SWITCHING
GATE_DRIVE
CONTROL_SENSING
FAN_POLICY
AUXILIARIES
SLEEP_ENABLED_LOADS
```

```text
type NoLoadCategoryRecord = {
  category: ClosedNoLoadCategory,
  applicability: APPLICABLE | NOT_APPLICABLE(reason,topology_control_matrix_cell),
  result_basis: CALCULATED_ESTIMATE | MEASURED | NONE,
  availability: Availability,
  value_and_unit: VALUE(CanonicalNumber,unit) | EXPLICIT_ABSENCE(missing_fields),
  p, s, elapsed_time,
  state: SETTLED | TRANSITION,
  observation_window: MaterialResult<Duration>,
  threshold_artifact: MaterialResult<ArtifactRef>,
  carrier_state, gate_state,
  provenance: MaterialResult<ArtifactRef>,
  uncertainty_or_bound: VALUE(CanonicalBound) | EXPLICIT_ABSENCE(missing_fields)
}
```

Each category independently carries the three classification fields. Every applicable category carries value/unit when evaluable and always carries p, s, elapsed time, state, observation-window/threshold results, carrier/gate state, provenance, and uncertainty/bound; unavailable context is represented by an unavailable `MaterialResult` or explicit missing-field absence, not omission. `NOT_APPLICABLE` is not zero and not `UNAVAILABLE`; its applicability result is available while its numerical value is explicit not-applicable absence. Applicable unevaluable categories are unavailable; provisional requires an evaluable finite value/bound.

Loaded 36 W, 42.8 W, and other fitted constants retain original load, control state, boundary, derivation, and evidence status. They cannot become unavoidable settled no-load loss without an independent term-by-term decomposition under the settled criteria.

### Frozen Preservation Manifest and Adapters

The immutable manifest is approved by `SpecBaselineOwner` and bound to a named Git commit ID and tree hash before implementation. It freezes applicability, eligibility, local bug-condition predicates, adapter choice/hash, observations, acceptance rules, and optional sampling.

```text
enum AdapterType {
  STATIC_TEXT_PARSER,
  LEGACY_FUNCTION_CAPTURE,
  LEGACY_SUBPROCESS_CAPTURE
}

type ExtractionRoute =
    SOURCE_RANGE(immutable_artifact_id, version, hash, exact_line_or_range)
  | ADAPTER_ROUTE(immutable_artifact_id, version, hash, LegacyAdapter)

type LegacyMapping = {
  namespaced_key,
  extraction_route: ExtractionRoute,   // exactly one route by construction
  frozen_applicability_predicate,
  frozen_eligibility_predicate,
  frozen_local_bug_condition_or_fix_predicate,
  mapping_kind:
      BASELINE_BEHAVIOR(canonical_observation, frozen_acceptance_rule)
    | NO_BASELINE_BEHAVIOR
}
```

A mapping with neither route, both routes, an absent source range, or incomplete route hashes is invalid.

Manifest keys are namespaced so duplicate field names do not collapse:

```text
TOP_LEVEL:3.1 ... TOP_LEVEL:3.12
EVIDENCE:<closed evidence key>
OUTPUT:<closed output key>
```

The exact closed evidence keys are:

```text
record_id, subject, related_subject, field, value, unit, EvidenceClass,
ConflictStatus, manufacturer, rating_class, artifact_id, artifact_version,
artifact_hash, locator, user_conditions, source_conditions, applicability,
relationship_rationale, formula_or_algorithm, dependency_record_ids,
instrument_ids, calibration_versions, measurement_boundary, sample_coverage,
method, uncertainty_or_bound, adjudicator, transition_timestamp,
transition_reason, trace_links, synthetic_marker
```

The exact closed output keys are:

```text
loss_categories, efficiency, temperatures, thermal_status, standby,
firmware_implementation_status, hardware_measurement_status,
device_comparison, qualification, residual_sources, boundary, availability,
freshness, applicability, result_basis, canonical_value,
uncertainty_or_bound, artifact_id, artifact_version, artifact_hash,
trace_identity, dependency_set, synthetic_marker, headline
```

The expected manifest key multiset is therefore 12 namespaced top-level keys plus every namespaced evidence key plus every namespaced output key. Machine validation requires exact set equality and exactly one mapping per namespaced key; unknown, omitted, duplicate, or unnamespaced keys fail configuration.

Each key maps exactly once either to an immutable source artifact plus exact line/range or to one adapter of type `STATIC_TEXT_PARSER`, `LEGACY_FUNCTION_CAPTURE`, or `LEGACY_SUBPROCESS_CAPTURE`. Every adapter freezes adapter-code hash, input hash, environment/container hash, command or entry point, and captured-output hash; subprocess adapters also freeze executable and dependency hashes. Each mapping is exactly `BASELINE_BEHAVIOR(canonical_observation,frozen_acceptance_rule)` or `NO_BASELINE_BEHAVIOR`. The latter contains no fabricated observation.

```text
FUNCTION executePreservation(mapping, generator)
  generated := generator.runFrozenOrderedPopulation()

  IF mapping.kind = BASELINE_BEHAVIOR
    eligible := generated cases satisfying frozen eligibility
                AND NOT frozen local bug condition
  ELSE
    eligible := generated cases satisfying frozen eligibility
                AND frozen fix-check predicate
  END IF

  sampled := frozenDeterministicSample(eligible, algorithm, seed, order, size)
             if sampling was frozen; otherwise eligible
  evaluated := sampled

  REQUIRE generated.count >= eligible.count >= sampled.count
  REQUIRE sampled.count = evaluated.count >= 1

  IF mapping.kind = BASELINE_BEHAVIOR
    COMPARE every evaluated case with immutable canonical observation
           under frozen acceptance rule
  ELSE
    REQUIRE mapping contains no legacy observation
    RUN corrected-behavior fix checks for every evaluated case
  END IF

  EMIT namespaced key, mapping kind, generated/eligible/sampled/evaluated/
       excluded counts, ordered case IDs, artifact/adapter hashes,
       and per-case machine-readable outcomes
END FUNCTION
```

Every eligible baseline case is evaluated unless the manifest froze deterministic sampling before implementation. Every no-baseline mapping has at least one evaluated fix-check case. Missing mappings, hash/applicability/adapter drift, mutable hashes, changed sampling, skipped eligible cases, zero evaluation, or post-freeze changes fail coverage.

The frozen mappings preserve the supported non-bug behavior in requirements 3.1–3.12: complete inverter-domain categories; fixed physical transformer-ratio current; eligible `Pbridge=Irms²×2×RDS(on,Tj)/m`; downstream-only system composition; explicit uncertain/missing fields; nonzero-command and transition residual physics; device qualification independent of RDS(on); exact closed scenario boundaries; calculated/modelled labels without hardware validation; complete `HOT_START_TRANSIENT`; and manifest-exclusive applicability. For requirement 3.11 they preserve the 0.60 mΩ `USER_SPECIFIED_TARGET`, pre-gate `T_ref`, exactly one distinct immutable artifact per exact gate with no reuse or extras, exact-one closed outcome, the controlled three-code iff partition, the sole endpoint code only after every non-case-set precondition passes, exact zero-count/false-claim ineligibility records, progression-only semantics, unresolved rejection behavior, and realistic execution/acceptance/publication blocking. Where no historical behavior exists, the namespaced key uses `NO_BASELINE_BEHAVIOR` rather than a fabricated preservation observation.

### Immutable Inverter Boundary

```text
type BoundaryInventory = {
  artifact_id, version, content_hash,
  owner: InverterOwner,
  approval_record,
  system_schema_id, system_schema_version, system_schema_hash,
  allowed_paths: CanonicallyOrderedSet<FieldPath>,
  excluded_paths: CanonicallyOrderedSet<FieldPath>
}
```

The immutable allowed set contains inverter DC-terminal conditions and inverter-domain electrical, control, component, thermal, and output-load fields. The excluded set contains battery cells, battery internal resistance, upstream pack interconnect, BMS, charger, C-rate, round-trip efficiency, and every other upstream field. The concrete path inventory is generated from and frozen with the actual system schema; this design does not invent unknown schema paths. Every schema path occurs exactly once in the disjoint union. Unknown, duplicate, unclassified, incomplete, owner/hash/version-mismatched, or post-freeze-mutated inventory blocks inverter-only acceptance.

The inverter solver accepts only a closed `InverterInput`; it has no direct, transitive, implicit, environment-derived, cached, callback, generic-map, or default dependency on excluded fields.

```text
FUNCTION testBoundaryIsolation(baseSystem, inventory)
  baselineSystemBytes := canonicalSerialize(baseSystem)
  inverterBytes := canonicalSerialize(baseSystem.inverter_input)
  terminalBytes := canonicalSerialize(baseSystem.dc_terminal_operating_point)
  baseline := solveInverter(baseSystem.inverter_input)

  FOR EACH excludedPath
    values := at least two distinct system-schema-valid, domain-valid values
    FOR EACH value
      mutated := mutateExactlyOneField(baseSystem, excludedPath, value)
      REQUIRE changedCanonicalPaths(baseSystem, mutated) = {excludedPath}
      REQUIRE every other system field is bit-for-bit fixed
      REQUIRE canonicalSerialize(mutated.inverter_input) = inverterBytes
      REQUIRE canonicalSerialize(mutated.dc_terminal_operating_point) = terminalBytes

      result := solveInverter(mutated.inverter_input)
      REQUIRE exact canonical equality of every full-precision scalar,
              vector, status, trace identity, and dependency set with baseline
    END FOR
  END FOR
END FUNCTION
```

Tolerance, rounded/display comparison, invalid mutation, multiple-field mutation, or changed terminal/inverter input does not count.

`composeSystem(freshInverterResult,battery?,charger?,upstream?)` is separately named and downstream-only. Adding, removing, or mutating it while preserving the terminal point leaves the inverter result, trace identity, and dependency set exactly invariant.

Scenario comparison requires exact canonical equality of the complete tuple:

```text
(energy_direction, pass_count, DC_terminal_nodes, AC_terminal_nodes,
 voltage/current sign conventions, averaging_interval, integration_method,
 load_state, control_state, carrier_state, gate_state, thermal_case,
 ambient/coolant boundaries, included_loss_categories,
 excluded_loss_categories, stored_energy_start, stored_energy_end)
```

A single-pass inverter efficiency is never compared with a two-pass round-trip efficiency.

### Thermal APIs

```text
coldSnapshot(electricalInput, completePhysicalTemperatures, domainArtifacts)
  -> MaterialResult<ColdT0Result>
initialDerivative(dynamicInput)
  -> MaterialResult<ThermalDerivative>
solveTransient(dynamicInput, elapsedTimeGreaterThanZero)
  -> MaterialResult<Trajectory>
solveSteadyState(steadyInput)
  -> MaterialResult<SteadyResult>
verifyRootCertificate(steadyInput, certificate, independentVerifier)
  -> MaterialResult<UniquenessStatus>
```

`coldSnapshot` is exactly `COLD_T0`. It requires finite physical initial temperatures for every applicable junction, case, heatsink, ambient, and coolant node, each inside the intersection of component, material-model, and solver domains. It evaluates electrical state and instantaneous losses, requires no Cth, and returns no derivative. Omitted, converged, undeclared hot, or out-of-domain temperatures make affected results unavailable.

`initialDerivative` and every t>0 transient, including `HOT_START_TRANSIENT`, use `DynamicThermalInput`: positive finite dimensionally valid cited Cth for every dynamic node; complete Rth network; boundaries; cooling mode; applied power versus time; complete physical initial temperature vector; elapsed interval; derivative/discretization/integration method; step/adaptive controls; convergence/error controls; and numerical tolerances from an immutable `InverterOwner`-approved artifact. Initial, trial-to-be-accepted, and accepted computed temperatures must stay in every applicable supported domain. Missing data or a domain exit makes the affected derivative/trajectory unavailable with node/time/value diagnostics; no fallback snapshot or steady-state result is substituted.

`SteadyThermalInput` requires complete finite Rth, boundary temperatures, cooling mode, temperature-dependent loss model, supported parameter/temperature domain, and approved method/convergence controls. It solves `dT/dt=0`. Cth is absent from the solver input and dependency trace. A legacy compatibility adapter strips Cth before canonical hashing or solving. Each unused Cth field is independently replaced with at least two distinct positive finite in-domain values while all other fields remain fixed; every canonical steady output and dependency trace must remain exactly invariant.

The deterministic seed set is exactly the lower-bound vector, componentwise midpoint vector, and upper-bound vector, deduplicated only when canonically identical. All seeds, roots, corresponding-node domain checks, residuals, and iterations are reported. Only when applicable `ATS-v2` is available, all seeds converge, node roots agree within `0.1 °C`, and every balance residual meets `max(0.01 W,1e-6×relevant thermal loss)` is `MULTI_SEED_AGREEMENT` available. Missing ATS makes that status decision unavailable; agreement never implies uniqueness.

`UNIQUE` is optional and requires a bounded root-isolation/root-count certificate covering the complete declared parameter and temperature domain, with exactly one admissible root and no unresolved, unknown, or unclassified interval/box. It identifies method and artifact ID/version/hash. An independent verifier records implementation hash, environment hash, input hash, and output hash and has a producer-distinct implementation/environment identity. Unsupported points, unresolved boxes, absent verifier/hash data, or non-one count yields `UNPROVEN`, without invalidating an otherwise valid steady solution.

### Ordered Device Comparison and Exclusive Thermal Attribution

The workflow uses two separate mandatory gates and one realistic-comparison transition:

```text
T_REF_FROZEN_BEFORE_EITHER_GATE
 -> EXACTLY_ONE_CONTROLLED_THREEFOLD_ARTIFACT_FINALIZED
 -> EXACTLY_ONE_ENDPOINT_SENSITIVITY_ARTIFACT_FINALIZED
 -> BOTH_CLOSED_OUTCOMES_VALIDATED
 -> REALISTIC_COMMON_TREF_ALLOWED
```

One finite `T_ref` with units, inside both exact devices' supported electrical-property and thermal domains, is predeclared and frozen before either gate or realistic comparison executes. A realistic result cannot precede, replace, or retroactively validate either gate. Before realistic execution, the gate-outcome registry contains exactly two artifacts total: exactly one for `CONTROLLED_THREEFOLD` and exactly one for `ENDPOINT_SENSITIVITY`. Their artifact ID/version/hash triples are distinct, immutable, non-aliased, never reused across gates, and frozen before realistic execution; no additional gate-outcome artifact exists. Each artifact identifies exactly one gate and contains exactly one outcome from that gate's closed union.

```text
type GateIdentity = CONTROLLED_THREEFOLD | ENDPOINT_SENSITIVITY

enum ControlledIneligibilityCode {
  INELIGIBLE_ZERO_IRMS,
  INELIGIBLE_EMPTY_CONDUCTION_INTERVAL,
  INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL
}

enum EndpointIneligibilityCode {
  INELIGIBLE_NO_POSITIVE_CURRENT_CASE
}

enum ControlledEligibilityPredicate {
  FINITE_POSITIVE_IRMS,
  NONEMPTY_CONDUCTION_INTERVAL
}

enum EndpointCandidateEligibilityPredicate {
  FINITE_POSITIVE_CURRENT,
  NONEMPTY_CONDUCTION_INTERVAL
}

type IneligibilityClaims = {
  completion_claim: false,  // exactly once
  pass_claim: false,        // exactly once
  success_claim: false      // exactly once
}

type ControlledIneligibility = {
  canonical_code: ControlledIneligibilityCode,
  unsatisfied_eligibility_predicates:
    ExactSet<ControlledEligibilityPredicate>,
  specific_reason: NonEmptyString,
  evaluated_case_count: CanonicalInteger<0>,
  claims: IneligibilityClaims
}

type EndpointIneligibility = {
  canonical_code: INELIGIBLE_NO_POSITIVE_CURRENT_CASE,
  unsatisfied_candidate_predicates:
    ExactSet<(candidate_id, EndpointCandidateEligibilityPredicate)>,
  specific_reason: NonEmptyString,
  evaluated_case_count: CanonicalInteger<0>,
  claims: IneligibilityClaims
}

type ControlledOutcome =
    CONTROLLED_COMPLETED_RECORDED_RESULT(requirement_2_29_result)
  | CONTROLLED_INELIGIBILITY(ControlledIneligibility)

type EndpointOutcome =
    ENDPOINT_COMPLETED_RECORDED_RESULT(requirement_2_31_result)
  | ENDPOINT_INELIGIBILITY(EndpointIneligibility)

type ControlledGateArtifact = {
  artifact_id, artifact_version, artifact_hash,
  frozen_before_realistic_execution: true,
  gate: CONTROLLED_THREEFOLD,
  outcome: ControlledOutcome
}

type EndpointGateArtifact = {
  artifact_id, artifact_version, artifact_hash,
  frozen_before_realistic_execution: true,
  gate: ENDPOINT_SENSITIVITY,
  outcome: EndpointOutcome
}
```

There is no generic ineligibility variant, generic code string, alias, or free-form predicate field. The serialized canonical field name is exactly `canonical_code`; it occurs exactly once in an ineligibility outcome and its value belongs only to that gate's enum. The three false claim fields and `evaluated_case_count=0` each occur exactly once. Duplicate keys, alternative spellings such as `passing_claim`, omitted fields, noncanonical zero, true or malformed claims, and extra completion/pass/success fields are malformed.

`CONTROLLED_COMPLETED_RECORDED_RESULT` is valid only when its canonical result satisfies requirement 2.29. `CONTROLLED_INELIGIBILITY` is valid only when every requirement-2.29 precondition other than positive `Irms` and nonempty conduction passes and exactly one of these iff rows matches:

| Exact controlled condition | `canonical_code` | Exact unsatisfied predicate set |
|---|---|---|
| finite `Irms = 0` and conduction interval nonempty | `INELIGIBLE_ZERO_IRMS` | `{FINITE_POSITIVE_IRMS}` |
| finite `Irms > 0` and conduction interval empty | `INELIGIBLE_EMPTY_CONDUCTION_INTERVAL` | `{NONEMPTY_CONDUCTION_INTERVAL}` |
| finite `Irms = 0` and conduction interval empty | `INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL` | `{FINITE_POSITIVE_IRMS, NONEMPTY_CONDUCTION_INTERVAL}` |

The rows are mutually exclusive and exhaustive only over requirement 2.30. Negative or nonfinite current, invalid resistance, unfixed temperature, changed waveform/topology/parallel count/timing/non-RDS(on) input, or any other failed requirement-2.29 precondition is not controlled ineligibility. A valid controlled ineligibility also records exact-zero baseline and replacement channel loss and delta and ratio `N/A`; it never requires or claims the one-third ratio or a nonzero total delta.

`ENDPOINT_COMPLETED_RECORDED_RESULT` is valid only when independently declared and evidenced finite low/high endpoints have canonically matching dimensions, units, and applicability with `low < high`; policy is available, valid, evidenced, and applicable; identity, every non-endpoint canonical full-precision input, and the predeclared candidate set are fixed; the candidate set is closed and immutable; every candidate satisfying both finite-positive-current and nonempty-conduction predicates is evaluated; and unrounded component/total outputs and deltas are recorded. `ENDPOINT_INELIGIBILITY` is valid only after every one of those non-case-set endpoint, evidence, policy, fixed-input, identity, and candidate-set preconditions passes and no candidate in the closed set satisfies both eligibility predicates. Its `unsatisfied_candidate_predicates` contains all and only the false `(candidate_id,predicate)` pairs for the closed set, thereby proving the no-case condition without treating eligibility inspection as case evaluation. Missing, malformed, unevidenced, nonfinite, dimensionally/unit/applicability-mismatched, or unordered endpoints; missing/invalid/unevidenced/inapplicable policy; unfixed inputs; or an open/mutable candidate set is an invalid prerequisite, never endpoint ineligibility.

```text
FUNCTION validateComparisonPrerequisites(registry, T_ref)
  REQUIRE T_ref was frozen before either gate executed
  REQUIRE T_ref is finite, unit-bearing, unchanged, and in both devices' domains

  artifacts := registry.allGateOutcomeArtifactsForThisComparison()
  REQUIRE artifacts.count = 2
  REQUIRE countForGate(artifacts, CONTROLLED_THREEFOLD) = 1
  REQUIRE countForGate(artifacts, ENDPOINT_SENSITIVITY) = 1
  controlledArtifact := soleArtifact(CONTROLLED_THREEFOLD)
  endpointArtifact := soleArtifact(ENDPOINT_SENSITIVITY)
  REQUIRE distinctNonAliasedImmutableIdentities(controlledArtifact, endpointArtifact)
  REQUIRE both were frozen before realistic execution
  REQUIRE exactlyOneOutcome(controlledArtifact)
  REQUIRE exactlyOneOutcome(endpointArtifact)

  IF controlledArtifact.outcome is CONTROLLED_COMPLETED_RECORDED_RESULT
    REQUIRE resultSatisfiesRequirement2_29(controlledArtifact.outcome)
  ELSE IF controlledArtifact.outcome is CONTROLLED_INELIGIBILITY
    REQUIRE allNonIrmsAndNonemptyConduction2_29PreconditionsPass()
    REQUIRE exactControlledIffCodeAndPredicateSet(controlledArtifact.outcome)
    REQUIRE exactZeroChannelLossesAndDeltaAndRatioNA(controlledArtifact.outcome)
    REQUIRE exactZeroEvaluatedCountAndExactlyOneFalseClaimFieldEach(controlledArtifact.outcome)
  ELSE
    REJECT
  END IF

  IF endpointArtifact.outcome is ENDPOINT_COMPLETED_RECORDED_RESULT
    REQUIRE resultSatisfiesRequirement2_31(endpointArtifact.outcome)
  ELSE IF endpointArtifact.outcome is ENDPOINT_INELIGIBILITY
    REQUIRE everyEndpointNonCaseSetPreconditionPasses()
    REQUIRE closedCandidateSetHasNoJointlyEligibleCase()
    REQUIRE endpointArtifact.outcome.canonical_code =
            INELIGIBLE_NO_POSITIVE_CURRENT_CASE
    REQUIRE allAndOnlyUnsatisfiedCandidatePredicatesAreRecorded()
    REQUIRE exactZeroEvaluatedCountAndExactlyOneFalseClaimFieldEach(endpointArtifact.outcome)
  ELSE
    REJECT
  END IF

  RETURN WORKFLOW_AUTHORIZATION(
           operation=PROGRESS_TO_REALISTIC_COMPARISON,
           controlled_outcome_ref=controlledArtifact.outcome,
           endpoint_outcome_ref=endpointArtifact.outcome)
ON ANY REJECTION
  MARK affected gate UNRESOLVED
  EMIT INVALID_WORKFLOW_AUTHORIZATION with exact gate diagnostics
  BLOCK progression
  SET every MaterialResult dependent on this workflow authorization UNAVAILABLE
  LEAVE unrelated MaterialResults unchanged
END FUNCTION
```

Validation rejects wrong-gate, generic, aliased, unrecognized, or predicate-mismatched codes; missing, extra, duplicated, or mismatched predicate records or reasons; invalid completed results; invalid prerequisites; malformed artifacts or outcomes; zero/multiple outcomes; missing, duplicate, mutable, aliased, reused, or late-created artifacts; artifact identity reuse; and any extra gate-outcome artifact. A rejected state is never reinterpreted, recoded, or summarized as ineligibility: the affected gate remains unresolved, progression is blocked, and each MaterialResult dependent on that workflow authorization is `UNAVAILABLE`; unrelated MaterialResults retain their independently derived status.

A structurally and semantically valid ineligibility outcome is a valid member of its required closed union and may satisfy only the workflow authorization for progression to realistic comparison. It is never represented, counted, summarized, traced, accepted, or published as gate completion, pass, or success, even though its artifact is immutable and valid. No realistic result can substitute for, precede, or retroactively validate either gate.

After both closed outcomes provide valid workflow authorization for progression, complete baseline and replacement temperature vectors have identical node identities and units and use the already-frozen `T_ref`. Every realistic output is then classified by a separate `derive` call using that output's own required admissible inputs/evidence, dependencies, result-specific acceptance conditions, and applicable workflow authorizations. An `AVAILABLE`, `PROVISIONAL`, or `UNAVAILABLE` realistic result never updates, upgrades, or relabels either gate outcome artifact.

The closed, mutually exclusive categories are:

```text
CHANNEL_CONDUCTION, GATE_DRIVE, EOSS_COSS, REVERSE_RECOVERY,
SWITCHING_OVERLAP, INTERCONNECT, MAGNETICS, AUXILIARIES,
OTHER_DECLARED(unique_subtype)
```

Every contribution has exactly one category owner. For each category `b`:

```text
Δfixed[b] = Lreplacement,b(T_ref_vector) - Lbaseline,b(T_ref_vector)
Δthermal[b] =
  [Lreplacement,b(Treplacement,converged) - Lreplacement,b(T_ref_vector)]
  - [Lbaseline,b(Tbaseline,converged) - Lbaseline,b(T_ref_vector)]

Δfixed_total = Σb Δfixed[b]
Δthermal_total = Σb Δthermal[b]
Δrealistic = Δfixed_total + Δthermal_total
```

The fixed bucket sum reconciles to the fixed total and the final equation reconciles to the realistic total under the ATS-v2 power rule. A temperature-induced term is owned only by `Δthermal[b]` and never by `Δfixed[b]`. The same categories and operating boundary apply throughout.

### Qualification, Control Evidence, and Firmware Immutability

A synthetic lower-voltage fixture tests only qualification-gating logic. The case and every input, evidence record, intermediate trace node, output, export, and headline carry `SYNTHETIC_TEST_ONLY`. Synthetic and real evidence never coexist in a dependency graph, aggregate, or decision. Any marker forces non-gating status and rejection from product qualification, manufacturer claims, real safety results, and measured-product conclusions. Removing a marker without rebuilding solely from real evidence fails trace validation.

A real gating case names the exact switching device and supplies direct exact-device limits for voltage, current, SOA, avalanche, package/isolation, thermal, and every declared constraint. Each limit includes value/unit, rating class, applicability predicate, pass operator or closed interval, manufacturer artifact ID/version/hash and locator, and source conditions. Stress evidence is a complete waveform over a predeclared interval with sample rate, analog bandwidth, probes/instruments and calibration/uncertainty, alignment, and peak extraction, or a cited conservative bound whose derivation, dependencies, uncertainty, and applicability include overshoot and transients. DC voltage, derating rule/margin, and a separate pass result for every limit are required. Only complete applicable passing results gate real qualification.

For 48 V operation, missing, invalid, or out-of-applicability evidence yields `UNAVAILABLE` when no admissible evaluable value exists or `PROVISIONAL` only for an evaluable bounded estimate lacking direct evidence. The result lists every gap, remains non-gating, does not fail bugfix acceptance, and supports no manufacturer or safety claim.

Control evidence has independent axes:

```text
enum ControlStatus { VERIFIED, UNVERIFIED, PROVISIONAL, UNAVAILABLE }
type ControlEvidence = {
  behavior,
  firmware_implementation_status: MaterialResult<ControlStatus>,
  hardware_measurement_status: MaterialResult<ControlStatus>
}
```

`VERIFIED` implies `AVAILABLE`. `UNVERIFIED` means applicable verification ran on evaluable evidence and at least one named VERIFIED predicate failed; every failure is recorded. `PROVISIONAL` and `UNAVAILABLE` have the global meanings. Firmware verification requires immutable source/config artifact ID/version/hash, requirement-to-code trace, build/config hash, and a deterministic passing full-requirement test under that configuration. Hardware verification independently requires test ID/version/hash, exact hardware identity, matching firmware/config hash, instruments/calibration, conditions, waveform/sample coverage, limits, and passing result for the same requirement. Missing required data prohibits verified. Phase generation or PWM-stop capability alone does not verify automatic no-load detection or control. Neither axis is copied, combined, or inferred from the other.

Firmware remains exactly immutable:

```text
type FirmwareManifest = {
  named_git_commit,
  git_tree_hash,
  entries: CanonicallyOrderedMap<path, content_hash>
}

FUNCTION verifyFirmwareUnchanged(before, after)
  REQUIRE before.named_git_commit = after.named_git_commit
  REQUIRE before.git_tree_hash = after.git_tree_hash
  REQUIRE exactCanonicalEqual(before.entries.keys, after.entries.keys)
  REQUIRE exactCanonicalEqual(before.entries, after.entries)
END FUNCTION
```

The closed file manifest is frozen before implementation and includes every named source/config artifact used by the oracle and build. Addition, removal, rename, or hash change fails bugfix acceptance. Actual hashes are captured from the repository; this design does not invent them.

A publication includes inverter/system boundary, named assumption variant, ATS-v2 ID/version/hash, device evidence/conflict state, digital oracle and analog MODREF identities, thermal case, both control statuses, result basis, availability, freshness, trace identity, dependency set, uncertainty/bound, and synthetic marker. Structural contract failures block bugfix acceptance. Missing external evidence blocks only its affected claim/decision and remains visible and non-gating. Stale, rounded-input, mixed synthetic/real, unsupported loaded-constant, or fabricated-evidence publication is rejected.

### Error Model

- `EVIDENCE_CLASS_INVALID`, `CLASS_METADATA_INCOMPLETE`, `RAW_PENDING_CONSUMPTION`
- `CONFLICT_TRANSITION_INVALID`, `SELECTION_CARDINALITY_INVALID`
- `MATERIAL_RESULT_ABSENT_BOUND`, `DEPENDENCY_UNAVAILABLE`, `INVALID_WORKFLOW_AUTHORIZATION`, `OPERATION_NOT_AUTHORIZED`, `STALE_RESULT_CONSUMPTION`
- `NONCANONICAL_NUMBER_OR_EVENT`, `ATS_UNAVAILABLE_OR_INAPPLICABLE`
- `PRODUCT_THRESHOLD_UNAVAILABLE`, `ANALOG_MODREF_UNAVAILABLE`
- `DIGITAL_ORACLE_MISMATCH`, with exact constant/comparator/available-event/count difference
- `DIGITAL_TIMING_UNAVAILABLE_COERCION`, when unavailable SR or aggregate semantics are omitted or converted to an empty list, zero count, zero gate transitions, zero switching, zero gate loss, or loss-free behavior
- `SR_DEADTIME_ADJUSTED_SUPPRESSED_PULSE_UNAVAILABLE`, carrying the missing independent ESP-IDF semantics artifact or measurement and remaining non-gating
- `RESIDUAL_MATRIX_INCOMPLETE`, `RESIDUAL_OWNER_DUPLICATE`, `RESIDUAL_OVERLAP`, `FORBIDDEN_RESIDUAL_SOURCE`
- `LEGACY_MANIFEST_INVALID`, `LEGACY_KEY_NAMESPACE_INVALID`, `LEGACY_EXTRACTION_ROUTE_INVALID`, `LEGACY_ADAPTER_DRIFT`, `PRESERVATION_COVERAGE_GAP`
- `BOUNDARY_INVENTORY_INVALID`, `EXCLUDED_DEPENDENCY`, `BOUNDARY_MUTATION_NOT_ISOLATED`, `COMPARISON_BOUNDARY_MISMATCH`
- `THERMAL_INITIAL_STATE_INVALID`, `THERMAL_DOMAIN_EXIT`, `THERMAL_DYNAMICS_UNAVAILABLE`, `STEADY_CTH_DEPENDENCY`
- `ROOT_UNIQUENESS_UNPROVEN`, which forbids `UNIQUE` but need not invalidate the steady root
- `COMPARISON_ORDER_INVALID`, `COMPARISON_TREF_INVALID_OR_LATE`, `COMPARISON_GATE_ARTIFACT_MISSING`, `COMPARISON_GATE_ARTIFACT_DUPLICATE`, `COMPARISON_GATE_ARTIFACT_MUTABLE`, `COMPARISON_GATE_ARTIFACT_ALIASED_OR_REUSED`, `COMPARISON_GATE_ARTIFACT_LATE`, `COMPARISON_GATE_ARTIFACT_EXTRA`, `COMPARISON_GATE_OUTCOME_CARDINALITY_INVALID`, `COMPARISON_GATE_WRONG_IDENTITY`, `COMPARISON_GATE_CODE_GENERIC_OR_UNRECOGNIZED`, `COMPARISON_GATE_CODE_ALIAS_OR_WRONG_GATE`, `COMPARISON_GATE_CODE_PREDICATE_MISMATCH`, `COMPARISON_GATE_PREDICATE_SET_INVALID`, `COMPARISON_GATE_REASON_INVALID`, `COMPARISON_GATE_EVALUATED_COUNT_INVALID`, `COMPARISON_GATE_FALSE_CLAIMS_INVALID`, `CONTROLLED_INELIGIBILITY_PREREQUISITE_INVALID`, `ENDPOINT_INELIGIBILITY_PREREQUISITE_INVALID`, `ENDPOINT_EVIDENCE_OR_POLICY_INVALID`, `ENDPOINT_FIXED_INPUT_OR_CANDIDATE_SET_INVALID`, `INELIGIBILITY_MISCLASSIFIED_AS_COMPLETION_PASS_OR_SUCCESS`, `BUCKET_OWNERSHIP_OVERLAP`, `COMPARISON_RECONCILIATION_FAILED`
- `SYNTHETIC_REAL_MIX`, `SYNTHETIC_PUBLICATION_REJECTED`, `QUALIFICATION_EVIDENCE_INCOMPLETE`
- `CONTROL_AXIS_INFERENCE`, `FIRMWARE_MANIFEST_CHANGED`, `LOADED_CONSTANT_NOLOAD_PROMOTION`

Errors carry affected artifact IDs/hashes, canonical paths, exact missing/invalid fields, and the local decision whose status changed. Every comparison-gate error leaves the affected mandatory gate `UNRESOLVED`, emits an invalid workflow-authorization diagnostic, blocks progression, and makes every MaterialResult dependent on that authorization `UNAVAILABLE`; it does not downgrade such a dependent result to `PROVISIONAL`, and it does not alter unrelated MaterialResults. Validators never recode an error as ineligibility. A valid ineligibility outcome is not an error: it may authorize only the permitted progression while retaining false completion/pass/success claims, and no downstream realistic-result status may upgrade or relabel it. `SR_DEADTIME_ADJUSTED_SUPPRESSED_PULSE_UNAVAILABLE` is a safety diagnostic and non-gating availability state, not an acceptance failure; coercing it triggers `DIGITAL_TIMING_UNAVAILABLE_COERCION`. External-evidence absence follows the availability lattice and does not become a global implementation failure.

### Migration Order

1. Freeze the named commit/tree, closed firmware paths and before hashes, namespaced legacy manifest, adapters, observations, predicates, and optional deterministic sampling.
2. Generate and approve the complete allowed/excluded inventory from the frozen system schema; block acceptance if it cannot be partitioned without invention.
3. Introduce canonical numbers/events, `MaterialResult`, trace DAG, availability/freshness propagation, and stale-consumption blocking.
4. Introduce evidence tagged unions, class metadata, conflict transitions, selection cardinality, immutable history, and transactional invalidation.
5. Register the fixed digital oracle with real source/config identities and the compiled `N=2285`, `H=1142`, `q=pH/100`, half-up `k`, actual `32000000/457 Hz` carrier, and 1142/1143 interval asymmetry. Store the exact p=10 available adjusted list/count and the exact p=1/p=0 available LV lists while migrating suppressed-pulse, complete adjusted SR, and complete aggregate adjusted fields to explicit safety-relevant `UNAVAILABLE`; reject legacy empty/zero/loss-free encodings. Keep analog fields unavailable pending independent approval.
6. Register ATS-v2 and product thresholds only if genuinely approved and applicable; never populate missing values from code.
7. Freeze the complete residual matrix, require p=0 asymmetry ownership, enforce source precedence, and propagate field-level aggregate status.
8. Refactor the pure inverter boundary and downstream system composition; execute exact one-field mutation and closed scenario-boundary tests.
9. Split thermal APIs, exact seed reporting, and optional independent uniqueness verification.
10. Freeze one finite, unit-bearing, in-domain `T_ref` before either gate. Allocate and finalize exactly one distinct immutable pre-realistic-execution artifact for each closed gate identity, prohibit identity reuse and additional artifacts, implement the controlled three-code iff partition and sole endpoint code with exact `canonical_code`, predicate, reason, zero-count, and false-claim schemas, reject every invalid prerequisite/artifact/code/outcome as unresolved, and only after both artifacts validate permit realistic common-`T_ref` comparison with per-category exclusive thermal attribution.
11. Isolate synthetic qualification graphs and implement complete real exact-device gating.
12. Publish orthogonal control axes, complete no-load records, loaded-constant provenance, and fresh trace metadata.
13. Execute every baseline/fix mapping and all validation, property, integration, and publication suites.
14. Capture the after firmware manifest and require exact equality before regenerating publications.

## Testing Strategy

### Validation Approach

Testing first captures counterexamples against the frozen unfixed baseline, then checks every numbered fix property, then executes preservation through the immutable manifest. All decisions use canonical full-precision values; missing external evidence is tested as a safe non-gating outcome rather than replaced.

### Exploratory Bug Condition Checking

**Goal:** Surface counterexamples on unfixed artifacts and confirm or revise each root-cause hypothesis before implementation.

**Test Plan:** Characterize current resistance records, pending-row consumption, timing behavior, caller-settled flags/default thresholds, residual ownership, legacy routes, schema dependencies, thermal mode conflation, comparison ordering, synthetic/control leakage, and firmware paths without changing the frozen baseline.

**Test Cases:**

1. Attempt target/related/conflicting resistance evidence promotion and raw pending consumption.
2. Compare p=10/1/0 timing with the fixed oracle; surface stale `N=2286`/`H=1143`/even-period/exact-50% assumptions, old vectors, p=10 count 15, reversed tick-2284 SR ordering, and any conversion of unavailable suppressed-pulse semantics to zero; also attempt analog acceptance from timing alone.
3. Exercise caller-settled/default-threshold paths and residual ownership overlap.
4. Enumerate legacy keys/adapters and actual system-schema boundary dependencies.
5. Exercise cold/dynamic/steady thermal modes, seed claims, and comparison order permutations.
6. Trace synthetic qualification, control-axis inference, loaded constants, publication freshness, and firmware path hashes.
7. Exercise all gate-registry cardinalities and artifact identity/reuse/freeze-time mutations; all controlled code/predicate combinations; endpoint missing/malformed evidence, policy, fixed-input, and candidate-set prerequisites; wrong/generic/alias codes; malformed claim/count fields; and premature realistic execution.

**Expected Counterexamples:** Unsupported evidence upgrades, digital-to-analog inference, unknown residuals replaced by zero, preservation omissions, upstream trace contamination, invalid thermal claims, out-of-order/double-counted comparison, generic or predicate-mismatched gate ineligibility, reused/extra/late gate artifacts, invalid endpoint prerequisites recoded as no-case ineligibility, synthetic/control leakage, or firmware drift. This stage also identifies which namespaced keys must use `NO_BASELINE_BEHAVIOR`.

### Fix Checking

```text
FOR ALL input WHERE isBugCondition(input)
  result := runFixedPipeline(input)
  ASSERT expectedBehavior(result)
  ASSERT no absent artifact was replaced by a code default or invented evidence
END FOR
```

Fix checks cover all evidence classes and transitions; compiled timing arithmetic (`N=2285`, `H=1142`, `q=pH/100`, half-up `k`, actual rational carrier, and 1142/1143 asymmetry); every available p=10/1/0 comparator/list/count; preservation of each unavailable suppressed-pulse/SR/aggregate field without empty, zero, omitted, or loss-free coercion; analog/policy absence; residual ownership; settling outcomes; boundary mutation; thermal modes; pre-gate finite in-domain `T_ref`; exactly two distinct immutable non-reused pre-realistic gate artifacts and no extras; exact-one gate-specific outcomes; the controlled three-code iff partition; the sole endpoint code only after every non-case-set evidence/policy/fixed-input/closed-candidate-set precondition passes; exact canonical code, all-and-only predicate set, specific reason, zero evaluated count, and exactly-once false claim fields; rejection to unresolved status for every malformed artifact, invalid prerequisite, wrong/generic/alias/predicate-mismatched code, or late/duplicate/reused artifact, with progression blocked and every authorization-dependent MaterialResult `UNAVAILABLE`; valid completed or permitted-ineligibility closed-union outcomes authorizing progression without treating ineligibility as completion/pass/success; independent `AVAILABLE`/`PROVISIONAL`/`UNAVAILABLE` classification of downstream realistic results without upgrading or relabeling the ineligibility artifact; qualification isolation; control axes; publication gates; and firmware identity.

### Preservation Checking

```text
FOR EACH namespaced mapping IN verifiedFrozenManifest
  generated := frozenGenerator(mapping)
  eligible := frozenEligibilityAndRoute(mapping, generated)
  sampled := frozenSampleIfDeclared(mapping, eligible)
  evaluated := sampled
  REQUIRE generated >= eligible >= sampled = evaluated >= 1

  IF mapping = BASELINE_BEHAVIOR
    COMPARE every evaluated case with immutable canonical observation
  ELSE
    REQUIRE no legacy observation
    RUN corrected-behavior fix checks for every evaluated case
  END IF
END FOR
```

Tests require exact mapping cardinality, immutable route hashes, frozen applicability/eligibility/local-bug predicates, frozen sampling if any, and machine-readable counts/case IDs. Omissions, duplicate namespaces, unknown keys/types, drift, skipped eligible cases, fabricated observations, or zero evaluation fail acceptance.

### Unit Tests

Unit tests cover every evidence metadata variant and absence marker; all legal/illegal transitions; raw pending rejection; selection invalidation; every availability/freshness cross-product; rational/float canonicalization; signed zero, NaN/infinity, shape/order, event ties, and aggregate definitions; exact compiled timing arithmetic (`160000000/70000→N=2285`, `H=1142`, intervals 1142/1143, `q=pH/100`, half-up `k`, `T=2285/160000000`, and carrier `32000000/457 Hz`); every requirement-2.36 comparator and available raw/adjusted list, identity, class, order, and individual count, including p=10 count 16 and `SR_B_OFF` before `SR_B_ON` at tick 2284; exact adjusted LV lists at p=1/p=0; `SR_DEADTIME_ADJUSTED_SUPPRESSED_PULSE` and complete adjusted SR/aggregate `UNAVAILABLE` propagation; rejection of empty-list, zero-count, zero-transition, zero-switching, zero-gate-loss, omitted-field, and loss-free substitutions; ATS/threshold/MODREF field deletion; exact/interval settling decisions; all residual matrix cells, NA versus unavailable, ownership and uncertainty exclusion; exact namespaced legacy inventory and adapter hashes; complete boundary partition/mutation preconditions; cold/dynamic/steady thermal contracts and seed status; pre-gate `T_ref` timing/domain validation; exact gate-registry cardinality; distinct immutable artifact identity and no alias/reuse/additional/late artifact; exact-one gate-specific outcome cardinality; requirement-valid completed results; each controlled iff code and exact predicate set; sole endpoint code only after complete valid endpoint/evidence/policy/fixed-input/closed-candidate-set prerequisites; canonical-code field spelling/cardinality; all-and-only predicate records; specific reasons; canonical zero evaluated counts; exactly-one false completion/pass/success fields; unresolved-state progression blocking and forced `UNAVAILABLE` for every workflow-authorization-dependent MaterialResult while unrelated results remain unchanged; valid completed and permitted-ineligibility closed-union authorization; independent downstream realistic-result availability classification with no ineligibility-artifact upgrade/relabel; reconciliation; synthetic propagation; real qualification fields; no-load context; orthogonal control evidence; and exact firmware manifest comparison.

### Property-Based Tests

Generators exercise evidence histories and illegal consumption, dependency DAG availability/staleness, unequal canonical values with equal displays, and one-field oracle mutations across `N`, `H`, interval lengths, `q`, `k`, actual carrier, comparator values, available event identity/order/count, and availability tags. Timing generators specifically attempt stale 2286/1143/even/exact-50% values, p=10 count 15, tick-2284 ON-before-OFF order, and every coercion of unavailable suppressed-pulse/SR/aggregate behavior to empty, zero, omitted, inferred-transition, or loss-free states; all must fail. Other generators cover missing/expired/out-of-scope policy artifacts, complete/incomplete residual matrices, waveforms around every approved threshold, each excluded schema path with at least two valid values, thermal domain exits and unsupported uniqueness claims, all comparison-order permutations; absent, late, nonfinite, unitless, out-of-domain, or changed `T_ref`; missing/duplicate/mutable/aliased/reused/late or extra gate artifacts; shared artifact IDs/versions/hashes; dual/empty/multiple outcomes; invalid completed results; every controlled current/conduction truth table crossed with every permitted code and generated generic/alias/wrong-gate code plus all predicate-set mutations; endpoint no-case code crossed with malformed/unevidenced/nonfinite/unordered/mismatched endpoints, missing/invalid/inapplicable policy, unfixed inputs, and open/mutable candidate sets; missing/extra/duplicate predicates and reasons; absent/nonzero/noncanonical evaluated counts; missing/duplicate/malformed/true completion, pass, or success fields; attempts to count or publish ineligibility as completion/pass/success; attempts to use a downstream realistic result to upgrade or relabel its ineligibility artifact; downstream realistic cases spanning locally `AVAILABLE`, `PROVISIONAL`, and `UNAVAILABLE` while gate authorization remains valid; unresolved-state bypass, premature realistic execution, or any provisional/available classification of an authorization-dependent result when its gate is malformed, rejected, or unresolved; overlapping buckets, all control status products, synthetic/real graph mixtures, qualification bundles missing one field, all no-load classifications, manifest path/hash mutations, and both legacy mapping kinds. Each generator reports against the numbered correctness properties above.

### Integration Tests

1. Ingest target, related-part, direct, derived, measured, and pending records; adjudicate one field and verify immutable history, pre-commit staleness, selection, and fresh descendant identities.
2. Run p=10/1/0 with `N=2285`, `H=1142`, actual `32000000/457 Hz` carrier, odd 1142/1143 intervals, exact `q` and half-up `k`, and compare every available comparator/raw/adjusted-LV-or-complete-adjusted list and count. Verify p=10 has 16 adjusted individual events; p=1/p=0 order `SR_B_OFF` before `SR_B_ON` at tick 2284; p=1/p=0 exact adjusted LV lists; and unavailable suppressed-pulse, complete adjusted SR, and aggregate adjusted fields remain safety-relevant, non-gating, and neither empty nor zero/loss-free. Verify p=0 one-tick asymmetry ownership and unavailable analog fields.
3. Run zero command with missing thresholds, an exceeded available threshold, and an all-pass approved artifact while retaining residuals in every path.
4. Exercise every supported residual Cartesian row and reject missing, prohibited, duplicate, or overlapping sources.
5. Execute every namespaced legacy mapping and require machine-evaluable counts, IDs, hashes, and explicit no-baseline fix checks.
6. Mutate every excluded path alone at least twice, mutate downstream compositions, and reject any mismatch in the complete scenario boundary.
7. Run cold snapshot, derivative/transient in-domain and domain-exit cases, steady Cth invariance, exact seeds, and invalid/valid independent certificate fixtures.
8. Freeze one finite unit-bearing `T_ref` inside both device domains before either gate. Run `CONTROLLED_THREEFOLD` and `ENDPOINT_SENSITIVITY` independently with exactly one distinct immutable pre-realistic artifact each, no alias/reuse or additional artifact, and exactly one gate-specific outcome. Cover valid completed results; all three controlled iff ineligibility rows with exact `canonical_code` and all-and-only predicate sets; and endpoint `INELIGIBLE_NO_POSITIVE_CURRENT_CASE` only after valid evidenced finite ordered endpoints, applicable policy, fixed inputs, and a closed immutable candidate set all pass while no candidate is jointly eligible. Require zero evaluated count and exactly one each of `completion_claim=false`, `pass_claim=false`, and `success_claim=false` for every ineligibility. Reject missing/duplicate/mutable/reused/aliased/late/extra artifacts, mixed/empty/multiple outcomes, wrong/generic/alias/predicate-mismatched codes, bad predicates/reasons/counts/claims, invalid completed results, and every invalid endpoint prerequisite; verify rejection leaves the gate unresolved, blocks progression, and makes every workflow-authorization-dependent MaterialResult `UNAVAILABLE` without changing unrelated results. Verify valid completed or permitted-ineligibility outcomes provide the required closed-union authorization for progression, while ineligibility is never counted, traced, accepted, or published as completion/pass/success. Only after both artifacts authorize progression, run realistic common-`T_ref`; independently classify realistic outputs as `AVAILABLE`, `PROVISIONAL`, or `UNAVAILABLE` from their own admissible inputs/evidence, dependencies, local acceptance conditions, and applicable authorizations; verify none of those statuses upgrades or relabels an ineligibility artifact; reject every order violation and thermal double count.
9. Run synthetic lower-voltage gating and publication rejection, then real qualification only with a complete exact-device bundle.
10. Cross firmware/hardware control evidence states and prove no inference between axes.
11. Compare before/after firmware manifests and fail every path-set or content-hash mutation.
12. Publish one complete fresh result and reject stale, rounded-input, fabricated-policy, mixed-synthetic, loaded-constant, and incomplete-evidence claims while retaining unrelated non-gating unavailable results.
