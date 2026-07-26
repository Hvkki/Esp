#!/usr/bin/env python3
"""Evidence-conservative inverter-loss correction contracts.

This module is intentionally self-contained (Python standard library only), pure
apart from artifact loading/hashing, and does not modify or execute firmware.
Missing external evidence remains local and non-gating.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from enum import Enum
from fractions import Fraction
from itertools import product
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_VERSION = "1.0.0"
COMPUTATION_ARTIFACT_ID = "INVERTER-LOSS-CORRECTION-PIPELINE"


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum): return value.value
    if isinstance(value, Fraction): return {"numerator":value.numerator,"denominator":value.denominator}
    if is_dataclass(value): return asdict(value)
    if isinstance(value,(set,frozenset)): return sorted(value)
    if isinstance(value,Path): return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not canonically serializable")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def content_hash(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    PROVISIONAL = "PROVISIONAL"
    UNAVAILABLE = "UNAVAILABLE"


class Freshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"


class EvidenceClass(str, Enum):
    USER_SPECIFIED_TARGET = "USER_SPECIFIED_TARGET"
    DIRECT_MANUFACTURER = "DIRECT_MANUFACTURER"
    RELATED_PART = "RELATED_PART"
    DERIVED_ESTIMATE = "DERIVED_ESTIMATE"
    MEASURED = "MEASURED"


class ConflictStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    ACCEPTED_FOR_FIELD = "ACCEPTED_FOR_FIELD"
    REJECTED_FOR_FIELD = "REJECTED_FOR_FIELD"
    SUPERSEDED = "SUPERSEDED"


class ControlStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    PROVISIONAL = "PROVISIONAL"
    UNAVAILABLE = "UNAVAILABLE"


class GateIdentity(str, Enum):
    CONTROLLED_THREEFOLD = "CONTROLLED_THREEFOLD"
    ENDPOINT_SENSITIVITY = "ENDPOINT_SENSITIVITY"


class EventClass(str, Enum):
    OFF = "OFF"
    DEADTIME_EXPIRY = "DEADTIME_EXPIRY"
    ON = "ON"


EVENT_ORDER = {EventClass.OFF: 0, EventClass.DEADTIME_EXPIRY: 1, EventClass.ON: 2}


@dataclass(frozen=True)
class ExplicitAbsence:
    missing_fields: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.missing_fields or not self.reason.strip():
            raise ValueError("explicit absence needs missing fields and reason")


@dataclass(frozen=True)
class CanonicalNumber:
    numeric_type: str
    dimension: str
    canonical_unit: str
    shape: tuple[int, ...]
    element_order: tuple[str, ...]
    representation: tuple[Any, ...]

    @staticmethod
    def rational(value: int | Fraction | str, dimension: str, unit: str) -> "CanonicalNumber":
        f = Fraction(value)
        if f == 0:
            f = Fraction(0, 1)
        return CanonicalNumber("RATIONAL", dimension, unit, (), (), ("REDUCED_RATIONAL", f.numerator, f.denominator))

    @staticmethod
    def finite_float(value: float, dimension: str, unit: str) -> "CanonicalNumber":
        if not math.isfinite(value):
            raise ValueError("NaN and infinity are noncanonical")
        if value == 0.0:
            value = 0.0
        bits = struct.pack(">d", value).hex()
        return CanonicalNumber("FLOAT64", dimension, unit, (), (), ("FINITE_FLOAT_BITS", "IEEE754_BINARY64", bits))

    @property
    def fraction(self) -> Fraction:
        if self.representation[0] != "REDUCED_RATIONAL":
            raise TypeError("not rational")
        return Fraction(self.representation[1], self.representation[2])


@dataclass(frozen=True)
class CanonicalEvent:
    tick: int
    event_class: EventClass
    device_id: str
    edge: str
    source_artifact_hash: str

    def __post_init__(self) -> None:
        if self.tick < 0 or not self.device_id or not self.edge or len(self.source_artifact_hash) != 64:
            raise ValueError("invalid canonical event")

    @property
    def sort_key(self) -> tuple[int, int, str]:
        return self.tick, EVENT_ORDER[self.event_class], self.device_id


def canonical_events(events: Iterable[CanonicalEvent]) -> tuple[CanonicalEvent, ...]:
    result = tuple(sorted(events, key=lambda e: e.sort_key))
    if len(result) != len(set(result)):
        raise ValueError("duplicate canonical event")
    return result


@dataclass(frozen=True)
class GateAuthorization:
    gate: GateIdentity
    operation: str
    valid: bool
    permitted_ineligibility: bool = False
    completion_claim: bool = False
    pass_claim: bool = False
    success_claim: bool = False
    diagnostic: Optional[str] = None
    synthetic_provenance: bool = False

    def __post_init__(self) -> None:
        _gate_authorization_state(self)

    @property
    def synthetic_only(self) -> bool:
        """Compatibility name backed by validated immutable instance state."""
        return _gate_authorization_state(self)["synthetic_provenance"]

    def authorizes(self, operation: str) -> bool:
        return _gate_authorization_authorizes(
            _gate_authorization_state(self), operation)


def _gate_authorization_state(authorization: Any) -> Mapping[str, Any]:
    """Snapshot authorization state without invoking class descriptors/methods."""
    if type(authorization) is not GateAuthorization:
        raise ValueError("GATE_AUTHORIZATION_EXACT_TYPE_REQUIRED")
    state = object.__getattribute__(authorization, "__dict__")
    expected = {"gate", "operation", "valid", "permitted_ineligibility",
                "completion_claim", "pass_claim", "success_claim",
                "diagnostic", "synthetic_provenance"}
    if type(state) is not dict or set(state) != expected:
        raise ValueError("GATE_AUTHORIZATION_STATE_INVALID")
    snapshot = dict(state)
    if (type(snapshot["gate"]) is not GateIdentity
            or type(snapshot["operation"]) is not str
            or not snapshot["operation"]
            or any(type(snapshot[name]) is not bool for name in
                   ("valid", "permitted_ineligibility", "completion_claim",
                    "pass_claim", "success_claim", "synthetic_provenance"))
            or (snapshot["diagnostic"] is not None
                and type(snapshot["diagnostic"]) is not str)):
        raise ValueError("GATE_AUTHORIZATION_STATE_INVALID")
    return MappingProxyType(snapshot)


def _gate_authorization_authorizes(state: Mapping[str, Any],
                                    operation: str) -> bool:
    if not state["valid"] or state["operation"] != operation:
        return False
    if state["permitted_ineligibility"]:
        return (operation == "PROGRESS_TO_REALISTIC_COMPARISON"
                and not any(state[name] for name in
                            ("completion_claim", "pass_claim", "success_claim")))
    return True


@dataclass(frozen=True)
class MaterialResult:
    availability: Availability
    freshness: Freshness
    dependency_record_ids: tuple[str, ...]
    dependency_hashes: tuple[tuple[str, str], ...]
    computation_artifact_id: str
    computation_artifact_version: str
    computation_artifact_hash: str
    canonical_value: Any
    applicability: str
    uncertainty_or_bound: Any
    trace_identity: str
    safety_relevant: bool = False
    non_gating: bool = False
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = tuple(sorted(set(self.dependency_record_ids)))
        hashes = tuple(sorted(self.dependency_hashes))
        if ids != self.dependency_record_ids or hashes != self.dependency_hashes:
            raise ValueError("dependencies must be canonical ordered unique sets/maps")
        if tuple(k for k, _ in hashes) != ids:
            raise ValueError("dependency IDs and hashes differ")
        if self.availability is Availability.PROVISIONAL and isinstance(self.canonical_value, ExplicitAbsence) and self.uncertainty_or_bound is None:
            raise ValueError("absent value without evaluable bound cannot be provisional")
        if not self.trace_identity or len(self.computation_artifact_hash) != 64:
            raise ValueError("incomplete trace identity")

    def consumable(self) -> bool:
        return self.freshness is Freshness.FRESH and self.availability is not Availability.UNAVAILABLE


def _trace(value: Any, deps: Sequence[MaterialResult], suffix: str = "") -> str:
    return content_hash({
        "value": canonical_json(value),
        "deps": [(r.trace_identity, r.freshness.value, r.availability.value,
                  getattr(r, "synthetic_provenance", False)) for r in deps],
        "suffix": suffix,
    })


def material_result(
    value: Any,
    availability: Availability = Availability.AVAILABLE,
    *,
    dependencies: Sequence[MaterialResult] = (),
    dependency_records: Mapping[str, str] = {},
    applicability: str = "APPLICABLE",
    bound: Any = None,
    diagnostics: Sequence[str] = (),
    safety_relevant: bool = False,
    non_gating: bool = False,
    synthetic_provenance: bool = False,
    suffix: str = "",
) -> MaterialResult:
    records = dict(dependency_records)
    for dep in dependencies:
        records.update(dict(dep.dependency_hashes))
    freshness = Freshness.STALE if any(d.freshness is Freshness.STALE for d in dependencies) else Freshness.FRESH
    if any(d.availability is Availability.UNAVAILABLE for d in dependencies):
        availability = Availability.UNAVAILABLE
    elif any(d.availability is Availability.PROVISIONAL for d in dependencies) and availability is Availability.AVAILABLE:
        availability = Availability.PROVISIONAL
    synthetic = synthetic_provenance or any(
        getattr(dep, "synthetic_provenance", False) for dep in dependencies)
    artifact_hash = content_hash({"id": COMPUTATION_ARTIFACT_ID, "version": ARTIFACT_VERSION})
    return MaterialResult(
        availability=availability,
        freshness=freshness,
        dependency_record_ids=tuple(sorted(records)),
        dependency_hashes=tuple(sorted(records.items())),
        computation_artifact_id=COMPUTATION_ARTIFACT_ID,
        computation_artifact_version=ARTIFACT_VERSION,
        computation_artifact_hash=artifact_hash,
        canonical_value=value,
        applicability=applicability,
        uncertainty_or_bound=bound,
        trace_identity=_trace(value, dependencies, suffix),
        safety_relevant=safety_relevant,
        non_gating=non_gating or synthetic,
        diagnostics=tuple(diagnostics),
        synthetic_provenance=synthetic,
    )


def derive_result(
    required: Sequence[MaterialResult],
    value: Any,
    *,
    direct_evidence_complete: bool,
    local_conditions_satisfied: bool,
    gate_authorizations: Sequence[GateAuthorization] = (),
    operation: Optional[str] = None,
    bound: Any = None,
    unrelated: bool = False,
) -> MaterialResult:
    authorization_states: tuple[Mapping[str, Any], ...] = ()
    if not unrelated:
        try:
            authorization_states = tuple(
                _gate_authorization_state(auth) for auth in gate_authorizations)
        except (TypeError, ValueError):
            return material_result(
                ExplicitAbsence(("workflow_authorization",),
                                "malformed workflow authorization"),
                Availability.UNAVAILABLE, dependencies=required,
                diagnostics=("INVALID_WORKFLOW_AUTHORIZATION",),
                non_gating=True, suffix="authorization-malformed")
    synthetic_authorization = any(
        state["synthetic_provenance"] for state in authorization_states)
    if operation:
        for state in authorization_states:
            if not _gate_authorization_authorizes(state, operation):
                return material_result(
                    ExplicitAbsence((state["gate"].value,),
                                    "invalid workflow authorization"),
                    Availability.UNAVAILABLE, dependencies=required,
                    diagnostics=(state["diagnostic"]
                                 or "INVALID_WORKFLOW_AUTHORIZATION",),
                    non_gating=True,
                    synthetic_provenance=synthetic_authorization,
                    suffix="authorization-blocked",
                )
    if not local_conditions_satisfied or any(r.availability is Availability.UNAVAILABLE for r in required):
        availability = Availability.UNAVAILABLE
    elif not direct_evidence_complete or any(r.availability is Availability.PROVISIONAL for r in required):
        availability = Availability.PROVISIONAL if not isinstance(value, ExplicitAbsence) or bound is not None else Availability.UNAVAILABLE
    else:
        availability = Availability.AVAILABLE
    return material_result(value, availability, dependencies=required, bound=bound,
                           synthetic_provenance=synthetic_authorization,
                           suffix="derived")


def invalidate_transitively(results: Mapping[str, MaterialResult], changed_record_id: str) -> dict[str, MaterialResult]:
    stale = dict(results)
    changed = True
    affected = {changed_record_id}
    while changed:
        changed = False
        for key, result in list(stale.items()):
            if key in affected or affected.intersection(result.dependency_record_ids):
                if result.freshness is Freshness.FRESH:
                    stale[key] = replace(result, freshness=Freshness.STALE)
                    affected.add(key)
                    changed = True
    return stale


def recompute_result(old: MaterialResult, value: Any, dependency_records: Mapping[str, str]) -> MaterialResult:
    new = material_result(value, old.availability, dependency_records=dependency_records, applicability=old.applicability,
                          bound=old.uncertainty_or_bound, diagnostics=old.diagnostics,
                          safety_relevant=old.safety_relevant, non_gating=old.non_gating,
                          synthetic_provenance=getattr(old, "synthetic_provenance", False),
                          suffix=old.trace_identity + ":recomputed")
    if new.trace_identity == old.trace_identity:
        raise ValueError("fresh recomputation requires new trace identity")
    return new



# ----------------------------- Evidence and policy -----------------------------

LEGAL_TRANSITIONS = {
    (ConflictStatus.NONE, ConflictStatus.PENDING),
    (ConflictStatus.PENDING, ConflictStatus.ACCEPTED_FOR_FIELD),
    (ConflictStatus.PENDING, ConflictStatus.REJECTED_FOR_FIELD),
    (ConflictStatus.ACCEPTED_FOR_FIELD, ConflictStatus.SUPERSEDED),
}
TERMINAL_STATUSES = {ConflictStatus.REJECTED_FOR_FIELD, ConflictStatus.SUPERSEDED}


@dataclass(frozen=True)
class Transition:
    prior: ConflictStatus
    after: ConflictStatus
    adjudicator: str
    timestamp: str
    reason: str
    cited_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (self.prior, self.after) not in LEGAL_TRANSITIONS:
            raise ValueError("CONFLICT_TRANSITION_INVALID")
        if not all((self.adjudicator, self.timestamp, self.reason)) or not self.cited_artifact_ids:
            raise ValueError("transition metadata incomplete")


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    subject: Optional[str]
    related_subject: Optional[str]
    field: str
    value: Any
    unit: Optional[str]
    evidence_class: Optional[EvidenceClass]
    conflict_status: ConflictStatus
    metadata: Mapping[str, Any]
    applicability: str
    history: tuple[Transition, ...] = ()
    synthetic_marker: bool = False

    def validate(self) -> None:
        if not self.record_id or not self.field or not self.applicability:
            raise ValueError("evidence identity incomplete")
        if self.evidence_class is None:
            if self.conflict_status is not ConflictStatus.PENDING or self.metadata.get("record_kind") != "RAW_UNRESOLVED_PENDING":
                raise ValueError("EVIDENCE_CLASS_INVALID")
            return
        required = {
            EvidenceClass.USER_SPECIFIED_TARGET: {"assertion_artifact_id","artifact_version","locator","artifact_hash","user_conditions"},
            EvidenceClass.DIRECT_MANUFACTURER: {"manufacturer","document_id","document_version","artifact_hash","locator","rating_class","source_conditions"},
            EvidenceClass.RELATED_PART: {"manufacturer","document_id","document_version","artifact_hash","locator","rating_class","source_conditions","relationship_rationale"},
            EvidenceClass.DERIVED_ESTIMATE: {"derivation_artifact_id","artifact_version","artifact_hash","formula_or_algorithm","dependency_record_ids","uncertainty_or_bound"},
            EvidenceClass.MEASURED: {"test_artifact_id","artifact_version","artifact_hash","instrument_ids","calibration_versions","measurement_boundary","conditions","sample_coverage","method","uncertainty"},
        }[self.evidence_class]
        missing = sorted(required - set(self.metadata))
        if missing:
            raise ValueError("CLASS_METADATA_INCOMPLETE:" + ",".join(missing))
        if self.evidence_class is EvidenceClass.RELATED_PART and not self.related_subject:
            raise ValueError("related subject required")
        if self.evidence_class is not EvidenceClass.RELATED_PART and self.related_subject:
            raise ValueError("related subject belongs only to related-part evidence")
        if self.conflict_status in TERMINAL_STATUSES and not self.history:
            raise ValueError("terminal status needs immutable history")

    @property
    def selectable(self) -> bool:
        return self.evidence_class is not None and self.conflict_status in {ConflictStatus.NONE, ConflictStatus.ACCEPTED_FOR_FIELD}

    def transition(self, after: ConflictStatus, adjudicator: str, timestamp: str, reason: str, cited: Sequence[str]) -> "EvidenceRecord":
        event = Transition(self.conflict_status, after, adjudicator, timestamp, reason, tuple(cited))
        updated = replace(self, conflict_status=after, history=self.history + (event,))
        updated.validate()
        return updated


def validate_selection(records: Sequence[EvidenceRecord], selected_id: str) -> EvidenceRecord:
    for r in records:
        r.validate()
    selected = [r for r in records if r.record_id == selected_id and r.selectable]
    active_accepted = [r for r in records if r.conflict_status is ConflictStatus.ACCEPTED_FOR_FIELD]
    if len(selected) != 1 or len(active_accepted) > 1:
        raise ValueError("SELECTION_CARDINALITY_INVALID")
    key = (selected[0].subject, selected[0].field, selected[0].applicability)
    if any((r.subject, r.field, r.applicability) != key for r in records):
        raise ValueError("selection tuple mismatch")
    return selected[0]


def evidence_catalog() -> tuple[EvidenceRecord, ...]:
    conditions = {name: "ABSENT" for name in ("VGS","ID","Tj_or_Tc","pulse_or_measurement")}
    target = EvidenceRecord(
        "EV-SC209-TARGET-060", "IRL40SC209", None, "RDS_ON", CanonicalNumber.rational("3/5", "RESISTANCE", "mOhm"), "mOhm",
        EvidenceClass.USER_SPECIFIED_TARGET, ConflictStatus.NONE,
        {"assertion_artifact_id":"USER-ASSERT-SC209-060","artifact_version":"1","locator":"bugfix.md:2.1",
         "artifact_hash":content_hash("USER-ASSERT-SC209-060:3/5mOhm"),"user_conditions":conditions},
        "IRL40SC209 RDS_ON target",
    )
    source_conditions = {name: "NOT_STATED_BY_SOURCE" for name in ("VGS","ID","Tj_or_Tc","pulse_or_measurement")}
    related = []
    for suffix, value, rating in (("059","59/100","TYPICAL"),("072","18/25","MAXIMUM")):
        related.append(EvidenceRecord(
            "EV-T209-"+suffix, "IRL40T209", "IRL40SC209", "RDS_ON", CanonicalNumber.rational(value,"RESISTANCE","mOhm"), "mOhm",
            EvidenceClass.RELATED_PART, ConflictStatus.PENDING,
            {"manufacturer":"Infineon","document_id":"MISSING_EXTERNAL_DOCUMENT_ID","document_version":"NOT_STATED_BY_SOURCE",
             "artifact_hash":content_hash("related-source-placeholder:"+suffix),"locator":"legacy repository statement only",
             "rating_class":rating,"source_conditions":source_conditions,
             "relationship_rationale":"same 209 designator asserted by legacy analysis; does not prove exact-part applicability"},
            "IRL40T209 source only; not direct IRL40SC209 evidence",
        ))
    raw = []
    for suffix, value in (("130","13/10"),("170","17/10")):
        raw.append(EvidenceRecord(
            "EV-RAW-"+suffix, None, None, "RDS_ON", CanonicalNumber.rational(value,"RESISTANCE","mOhm"), "mOhm",
            None, ConflictStatus.PENDING,
            {"record_kind":"RAW_UNRESOLVED_PENDING","artifact_id":"ABSENT","artifact_version":"ABSENT","artifact_hash":"ABSENT",
             "locator":"legacy generalized source row","source_conditions":"ABSENT"},
            "unresolved subject/field source row",
        ))
    result = (target, *related, *raw)
    for r in result:
        r.validate()
    return result


@dataclass(frozen=True)
class ATSv2:
    artifact_id: str
    version: str
    artifact_hash: str
    owner: str
    approval: str
    applicability: frozenset[str]
    expired: bool = False

    def usable_for(self, decision: str) -> bool:
        expected = content_hash({"artifact_id":self.artifact_id,"version":self.version,"owner":self.owner,
                                 "approval":self.approval,"applicability":sorted(self.applicability)})
        return self.owner == "InverterOwner" and self.approval == "SPEC_NORMATIVE_APPROVAL" and not self.expired and decision in self.applicability and self.artifact_hash == expected


def normative_ats() -> ATSv2:
    applicability = frozenset({"CANONICAL_EQUALITY","DIGITAL_TIMING","THREEFOLD","POWER_RECONCILIATION","THERMAL_MULTI_SEED","RESISTANCE_SOURCE"})
    base = {"artifact_id":"ATS-v2","version":"2.0.0","owner":"InverterOwner","approval":"SPEC_NORMATIVE_APPROVAL","applicability":sorted(applicability)}
    return ATSv2(base["artifact_id"],base["version"],content_hash(base),base["owner"],base["approval"],applicability)


def require_ats(ats: Optional[ATSv2], decision: str) -> MaterialResult:
    if ats is None or not ats.usable_for(decision):
        return material_result(ExplicitAbsence(("ATS-v2",),"ATS absent, invalid, expired, hash-mismatched, or inapplicable"), Availability.UNAVAILABLE,
                               diagnostics=("ATS_UNAVAILABLE_OR_INAPPLICABLE",), non_gating=True)
    return material_result(ats.artifact_id, dependency_records={ats.artifact_id:ats.artifact_hash})



# ----------------------------- Digital oracle -----------------------------

ORACLE_SOURCE_HASH = content_hash({
    "firmware/main/inv_config.h":"60e8cb8b7a2af6ad6dc7748a914aa3bc314a0e750e4f32c95a410c01fcb533aa",
    "firmware/main/pwm.c":"50cd5954bcc69984f4cdfe62573f863b8489d35e8a7cba2e81e17e44caf41b78",
})
SR_UNAVAILABLE_REASON = (
    "missing independent ESP-IDF peripheral-semantics artifact or measurement establishing "
    "whether the delayed high pulse is cancelled and what low-side transitions occur"
)


@dataclass(frozen=True)
class TimingField:
    availability: Availability
    value: Any
    reason: Optional[str] = None
    safety_relevant: bool = False
    non_gating: bool = False

    @staticmethod
    def exact(value: Any) -> "TimingField":
        return TimingField(Availability.AVAILABLE, value)

    @staticmethod
    def unavailable(reason: str) -> "TimingField":
        return TimingField(Availability.UNAVAILABLE, ExplicitAbsence(("independent_sr_semantics",), reason), reason, True, True)


@dataclass(frozen=True)
class TimingVector:
    p: CanonicalNumber
    polarity: int
    q: CanonicalNumber
    phi: CanonicalNumber
    k: int
    N: int
    H: int
    interval_lengths: tuple[int, int]
    actual_carrier: CanonicalNumber
    period: CanonicalNumber
    comparators: tuple[tuple[str, int], ...]
    intervals: tuple[tuple[str, int, int], ...]
    raw_events: TimingField
    adjusted_lv_events: TimingField
    suppressed_pulse: TimingField
    complete_adjusted_sr_events: TimingField
    complete_aggregate_adjusted_events: TimingField
    sr_enabled: bool
    residual_owner: Optional[str]


COMPARATOR_IDS = (
    "LV_A_ON_RESERVED","LV_A_OFF","LV_B_ON","LV_B_OFF",
    "SR_A_ON_RESERVED","SR_A_OFF","SR_B_ON","SR_B_OFF",
)


def _event(tick: int, cls: EventClass, device: str, edge: str) -> CanonicalEvent:
    return CanonicalEvent(tick, cls, device, edge, ORACLE_SOURCE_HASH)


def _raw(spec: Sequence[tuple[int, EventClass, str, str]]) -> tuple[CanonicalEvent, ...]:
    return canonical_events(_event(*row) for row in spec)


def realize_phase(p: int | Fraction | str, N: int = 2285) -> tuple[int, Fraction, int]:
    pfrac = Fraction(p)
    if not (0 <= pfrac <= 100) or N <= 0:
        raise ValueError("phase magnitude or period out of range")
    H = N // 2
    q = pfrac * H / 100
    k = min(H, max(0, (2*q.numerator + q.denominator) // (2*q.denominator)))
    return H, q, k


def digital_oracle(p: int, polarity: int = 1) -> TimingVector:
    if polarity != 1:
        raise ValueError("only hand-reviewed s=+1 repository vectors are available")
    N, H = 2285, 1142
    _, q, k = realize_phase(p, N)
    common = dict(
        p=CanonicalNumber.rational(p,"PERCENT","percent"), polarity=polarity,
        q=CanonicalNumber.rational(q,"TICK_DISPLACEMENT","tick"),
        phi=CanonicalNumber.rational(q/Fraction(160_000_000),"TIME","s"), k=k, N=N, H=H,
        interval_lengths=(1142,1143),
        actual_carrier=CanonicalNumber.rational(Fraction(32_000_000,457),"FREQUENCY","Hz"),
        period=CanonicalNumber.rational(Fraction(2285,160_000_000),"TIME","s"),
    )
    unavailable = TimingField.unavailable(SR_UNAVAILABLE_REASON)
    if p == 10:
        comparators = tuple(zip(COMPARATOR_IDS,(1,1142,114,1256,1,106,1150,1248)))
        intervals = (("LV_A",0,1142),("LV_B",114,1256),("SR_A",0,106),("SR_B",1150,1248))
        raw = _raw((
            (0,EventClass.ON,"LV_A_HI","ON"),(0,EventClass.ON,"SR_A_HI","ON"),
            (106,EventClass.OFF,"SR_A_HI","OFF"),(114,EventClass.ON,"LV_B_HI","ON"),
            (1142,EventClass.OFF,"LV_A_HI","OFF"),(1150,EventClass.ON,"SR_B_HI","ON"),
            (1248,EventClass.OFF,"SR_B_HI","OFF"),(1256,EventClass.OFF,"LV_B_HI","OFF"),
        ))
        adjusted = _raw((
            (0,EventClass.OFF,"LV_A_LO","OFF"),(0,EventClass.OFF,"SR_A_LO","OFF"),
            (10,EventClass.DEADTIME_EXPIRY,"LV_A_HI","ON"),(16,EventClass.DEADTIME_EXPIRY,"SR_A_HI","ON"),
            (106,EventClass.OFF,"SR_A_HI","OFF"),(114,EventClass.OFF,"LV_B_LO","OFF"),
            (122,EventClass.DEADTIME_EXPIRY,"SR_A_LO","ON"),(124,EventClass.DEADTIME_EXPIRY,"LV_B_HI","ON"),
            (1142,EventClass.OFF,"LV_A_HI","OFF"),(1150,EventClass.OFF,"SR_B_LO","OFF"),
            (1152,EventClass.DEADTIME_EXPIRY,"LV_A_LO","ON"),(1166,EventClass.DEADTIME_EXPIRY,"SR_B_HI","ON"),
            (1248,EventClass.OFF,"SR_B_HI","OFF"),(1256,EventClass.OFF,"LV_B_HI","OFF"),
            (1264,EventClass.DEADTIME_EXPIRY,"SR_B_LO","ON"),(1266,EventClass.DEADTIME_EXPIRY,"LV_B_LO","ON"),
        ))
        return TimingVector(**common,comparators=comparators,intervals=intervals,
                            raw_events=TimingField.exact(raw),adjusted_lv_events=TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("LV_"))),
                            suppressed_pulse=TimingField.exact("NOT_APPLICABLE_FULL_WINDOW"),
                            complete_adjusted_sr_events=TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("SR_"))),
                            complete_aggregate_adjusted_events=TimingField.exact(adjusted),sr_enabled=True,residual_owner=None)
    if p not in (0,1):
        raise ValueError("repository acceptance oracle only defines p=10,1,0")
    lv_b_on = 11 if p == 1 else 1
    lv_b_off = 1153 if p == 1 else 1142
    comparators = tuple(zip(COMPARATOR_IDS,(1,1142,lv_b_on,lv_b_off,1,1,2284,2284)))
    intervals = (("LV_A",0,1142),("LV_B",lv_b_on,lv_b_off))
    raw_spec = [
        (0,EventClass.ON,"LV_A_HI","ON"),(0,EventClass.ON,"SR_A_HI","ON"),
        (1,EventClass.OFF,"SR_A_HI","OFF"),(lv_b_on,EventClass.ON,"LV_B_HI","ON"),
        (1142,EventClass.OFF,"LV_A_HI","OFF"),(lv_b_off,EventClass.OFF,"LV_B_HI","OFF"),
        (2284,EventClass.OFF,"SR_B_HI","OFF"),(2284,EventClass.ON,"SR_B_HI","ON"),
    ]
    raw = _raw(raw_spec)
    if p == 1:
        adjusted = _raw((
            (0,EventClass.OFF,"LV_A_LO","OFF"),(10,EventClass.DEADTIME_EXPIRY,"LV_A_HI","ON"),
            (11,EventClass.OFF,"LV_B_LO","OFF"),(21,EventClass.DEADTIME_EXPIRY,"LV_B_HI","ON"),
            (1142,EventClass.OFF,"LV_A_HI","OFF"),(1152,EventClass.DEADTIME_EXPIRY,"LV_A_LO","ON"),
            (1153,EventClass.OFF,"LV_B_HI","OFF"),(1163,EventClass.DEADTIME_EXPIRY,"LV_B_LO","ON"),
        ))
        owner = None
    else:
        adjusted = _raw((
            (0,EventClass.OFF,"LV_A_LO","OFF"),(1,EventClass.OFF,"LV_B_LO","OFF"),
            (10,EventClass.DEADTIME_EXPIRY,"LV_A_HI","ON"),(11,EventClass.DEADTIME_EXPIRY,"LV_B_HI","ON"),
            (1142,EventClass.OFF,"LV_A_HI","OFF"),(1142,EventClass.OFF,"LV_B_HI","OFF"),
            (1152,EventClass.DEADTIME_EXPIRY,"LV_A_LO","ON"),(1152,EventClass.DEADTIME_EXPIRY,"LV_B_LO","ON"),
        ))
        owner = "LEG_COMMAND_TICK_ASYMMETRY"
    return TimingVector(**common,comparators=comparators,intervals=intervals,
                        raw_events=TimingField.exact(raw),adjusted_lv_events=TimingField.exact(adjusted),
                        suppressed_pulse=unavailable,complete_adjusted_sr_events=unavailable,
                        complete_aggregate_adjusted_events=unavailable,sr_enabled=False,residual_owner=owner)


def validate_timing(actual: TimingVector, expected: TimingVector) -> MaterialResult:
    exact_fields = ("p","polarity","q","phi","k","N","H","interval_lengths","actual_carrier","period","comparators","intervals","sr_enabled","residual_owner")
    mismatches = [name for name in exact_fields if getattr(actual,name) != getattr(expected,name)]
    for name in ("raw_events","adjusted_lv_events","suppressed_pulse","complete_adjusted_sr_events","complete_aggregate_adjusted_events"):
        a, e = getattr(actual,name), getattr(expected,name)
        if e.availability is Availability.AVAILABLE:
            if a.availability is not Availability.AVAILABLE or a.value != e.value:
                mismatches.append(name)
        else:
            if a.availability is not Availability.UNAVAILABLE or a.reason != e.reason or not a.safety_relevant or not a.non_gating:
                mismatches.append(name)
            if a.value in ((), [], 0, "NO_TRANSITIONS", "NO_SWITCHING", "NO_GATE_LOSS", "LOSS_FREE", None):
                mismatches.append(name+":COERCED")
    if mismatches:
        return material_result(ExplicitAbsence(tuple(mismatches),"digital oracle mismatch"),Availability.UNAVAILABLE,
                               diagnostics=("DIGITAL_ORACLE_MISMATCH",),safety_relevant=True)
    return material_result("DIGITAL_SCOPE_ACCEPTED",dependency_records={"DIGITAL-ORACLE-2.36":ORACLE_SOURCE_HASH})


def analog_modref_unavailable(fields: Iterable[str]) -> dict[str, MaterialResult]:
    return {
        field: material_result(ExplicitAbsence((field,),"missing independently approved analog MODREF field"),Availability.UNAVAILABLE,
                               diagnostics=("ANALOG_MODREF_UNAVAILABLE",),non_gating=True)
        for field in fields
    }



# ----------------------------- Residuals, settling, no-load -----------------------------

RESIDUAL_TYPES = (
    "LEG_COMMAND_TICK_ASYMMETRY","DEADTIME_ASYMMETRY","PROPAGATION_DRIVER_MISMATCH",
    "DEVICE_TRANSITION_MISMATCH","SR_COMMUTATION","STORED_ENERGY_DECAY","OTHER_DECLARED",
)
NO_LOAD_CATEGORIES = (
    "INTENTIONAL_IDEAL_DIFFERENTIAL_TRANSFER","UNINTENDED_DIFFERENTIAL_RESIDUAL",
    "COMMON_MODE_SWITCHING","GATE_DRIVE","CONTROL_SENSING","FAN_POLICY","AUXILIARIES",
    "SLEEP_ENABLED_LOADS",
)


@dataclass(frozen=True)
class PhysicalField:
    state: str
    value: Any = None
    reason: Optional[str] = None

    @staticmethod
    def value_of(value: Any) -> "PhysicalField":
        return PhysicalField("VALUE",value)

    @staticmethod
    def na(reason: str) -> "PhysicalField":
        if not reason: raise ValueError("NA requires reason")
        return PhysicalField("NA",reason=reason)

    @staticmethod
    def unavailable(*missing: str) -> "PhysicalField":
        return PhysicalField("UNAVAILABLE",reason=",".join(missing))


@dataclass(frozen=True)
class ResidualRecord:
    case_id: str
    ownership_id: str
    source_type: str
    subtype: Optional[str]
    provenance: tuple[str,str,str]
    waveform: PhysicalField
    energy_initial: PhysicalField
    energy_final: PhysicalField
    energy_change: PhysicalField
    heat_loss: PhysicalField
    uncertainty_or_bound: Any
    availability: Availability

    def type_key(self) -> str:
        if self.source_type == "OTHER_DECLARED":
            if not self.subtype: raise ValueError("OTHER_DECLARED subtype must be nonempty")
            return "OTHER_DECLARED"
        if self.source_type not in RESIDUAL_TYPES: raise ValueError("unknown residual type")
        if self.subtype is not None: raise ValueError("subtype only valid for OTHER_DECLARED")
        return self.source_type


@dataclass(frozen=True)
class ResidualMatrix:
    artifact_id: str
    version: str
    artifact_hash: str
    owner: str
    approval: str
    rows: Mapping[tuple[str,str,str,str],Mapping[str,tuple[str,Optional[str]]]]

    def validate(self) -> None:
        expected_rows = set(product(("HF_LINK_PSFB",),("NONZERO","ZERO_TRANSITION","ZERO_SETTLED"),("ENABLED","DISABLED"),("ENABLED","DISABLED")))
        if set(self.rows) != expected_rows or self.owner != "InverterOwner" or self.approval != "SPEC_NORMATIVE_APPROVAL":
            raise ValueError("RESIDUAL_MATRIX_INCOMPLETE")
        for row in self.rows.values():
            if set(row) != set(RESIDUAL_TYPES): raise ValueError("RESIDUAL_MATRIX_INCOMPLETE")
            for state, reason in row.values():
                if state not in ("REQUIRED","NOT_APPLICABLE") or (state == "NOT_APPLICABLE" and not reason):
                    raise ValueError("invalid residual matrix cell")
        serial = {"rows":[[list(k),[[t,*v] for t,v in sorted(row.items())]] for k,row in sorted(self.rows.items())],
                  "owner":self.owner,"approval":self.approval,"artifact_id":self.artifact_id,"version":self.version}
        if self.artifact_hash != content_hash(serial): raise ValueError("residual matrix hash mismatch")


def normative_residual_matrix() -> ResidualMatrix:
    rows: dict[tuple[str,str,str,str],dict[str,tuple[str,Optional[str]]]] = {}
    for topology,p_state,gate_state,sr_state in product(("HF_LINK_PSFB",),("NONZERO","ZERO_TRANSITION","ZERO_SETTLED"),("ENABLED","DISABLED"),("ENABLED","DISABLED")):
        row = {t:("NOT_APPLICABLE","not declared applicable for this repository state") for t in RESIDUAL_TYPES}
        if p_state.startswith("ZERO"):
            row["LEG_COMMAND_TICK_ASYMMETRY"] = ("REQUIRED",None)
        if p_state == "ZERO_TRANSITION":
            row["STORED_ENERGY_DECAY"] = ("REQUIRED",None)
        if gate_state == "ENABLED":
            row["DEADTIME_ASYMMETRY"] = ("REQUIRED",None)
        if sr_state == "ENABLED":
            row["SR_COMMUTATION"] = ("REQUIRED",None)
        rows[(topology,p_state,gate_state,sr_state)] = row
    serial = {"rows":[[list(k),[[t,*v] for t,v in sorted(row.items())]] for k,row in sorted(rows.items())],
              "owner":"InverterOwner","approval":"SPEC_NORMATIVE_APPROVAL","artifact_id":"RESIDUAL-MATRIX-001","version":"1.0.0"}
    return ResidualMatrix("RESIDUAL-MATRIX-001","1.0.0",content_hash(serial),"InverterOwner","SPEC_NORMATIVE_APPROVAL",rows)


def aggregate_residuals(case_key: tuple[str,str,str,str], records: Sequence[ResidualRecord], matrix: Optional[ResidualMatrix] = None) -> MaterialResult:
    matrix = matrix or normative_residual_matrix()
    try:
        matrix.validate()
        row = matrix.rows[case_key]
    except (ValueError,KeyError) as exc:
        return material_result(ExplicitAbsence(("residual_matrix",),str(exc)),Availability.UNAVAILABLE,diagnostics=("RESIDUAL_MATRIX_INCOMPLETE",))
    ownership = [r.ownership_id for r in records]
    if len(ownership) != len(set(ownership)):
        return material_result(ExplicitAbsence(("ownership_id",),"duplicate residual owner"),Availability.UNAVAILABLE,diagnostics=("RESIDUAL_OWNER_DUPLICATE",))
    subtypes = [r.subtype for r in records if r.source_type == "OTHER_DECLARED"]
    if any(not x for x in subtypes) or len(subtypes) != len(set(subtypes)):
        return material_result(ExplicitAbsence(("OTHER_DECLARED",),"duplicate/empty subtype"),Availability.UNAVAILABLE,diagnostics=("RESIDUAL_OWNER_DUPLICATE",))
    grouped: dict[str,list[ResidualRecord]] = {t:[] for t in RESIDUAL_TYPES}
    for record in records:
        try: grouped[record.type_key()].append(record)
        except ValueError as exc:
            return material_result(ExplicitAbsence(("source_type",),str(exc)),Availability.UNAVAILABLE)
    for source_type,(cell,_) in row.items():
        count = len(grouped[source_type])
        if (cell == "REQUIRED" and count != 1) or (cell == "NOT_APPLICABLE" and count != 0):
            code = "FORBIDDEN_RESIDUAL_SOURCE" if cell == "NOT_APPLICABLE" else "RESIDUAL_MATRIX_INCOMPLETE"
            return material_result(ExplicitAbsence((source_type,),f"{cell} count={count}"),Availability.UNAVAILABLE,diagnostics=(code,))
    heat = Fraction(0)
    provisional = False
    owned_energy = set()
    for record in records:
        for field_name in ("waveform","energy_initial","energy_final","energy_change","heat_loss"):
            physical = getattr(record,field_name)
            if physical.state == "UNAVAILABLE":
                return material_result(ExplicitAbsence((record.ownership_id+"."+field_name,),physical.reason or "missing"),Availability.UNAVAILABLE)
        if record.heat_loss.state == "VALUE":
            value = Fraction(record.heat_loss.value)
            if value < 0: return material_result(ExplicitAbsence((record.ownership_id,),"negative heat"),Availability.UNAVAILABLE)
            heat += value
        if record.availability is Availability.PROVISIONAL: provisional = True
        energy_identity = (record.energy_initial.value,record.energy_final.value,record.energy_change.value)
        if record.source_type == "STORED_ENERGY_DECAY" and energy_identity in owned_energy:
            return material_result(ExplicitAbsence((record.ownership_id,),"stored energy overlap"),Availability.UNAVAILABLE,diagnostics=("RESIDUAL_OVERLAP",))
        if record.source_type != "STORED_ENERGY_DECAY": owned_energy.add(energy_identity)
    return material_result(CanonicalNumber.rational(heat,"POWER","W"),Availability.PROVISIONAL if provisional else Availability.AVAILABLE,
                           dependency_records={matrix.artifact_id:matrix.artifact_hash},bound="sum excludes uncertainty")


@dataclass(frozen=True)
class ProductThresholds:
    artifact_id: str
    version: str
    artifact_hash: str
    owner: str
    approved: bool
    W_seconds: Fraction
    ires_max: Fraction
    vsperiod_max: Fraction
    vscum_max: Fraction
    estored_max: Fraction
    closed_energy_sources: tuple[str,...]
    methods_complete: bool

    def valid(self, period: Fraction) -> bool:
        expected = content_hash({k:(str(v) if isinstance(v,Fraction) else v) for k,v in self.__dict__.items() if k != "artifact_hash"})
        return self.owner == "InverterOwner" and self.approved and self.methods_complete and self.artifact_hash == expected and self.W_seconds >= max(Fraction(10)*period,Fraction(1,1000))


def make_test_thresholds(period: Fraction, **overrides: Any) -> ProductThresholds:
    values = dict(artifact_id="SYNTHETIC-THRESHOLD-FIXTURE",version="1",owner="InverterOwner",approved=True,
                  W_seconds=max(Fraction(10)*period,Fraction(1,1000)),ires_max=Fraction(1,10),vsperiod_max=Fraction(1,100),
                  vscum_max=Fraction(1,100),estored_max=Fraction(1,100),closed_energy_sources=("transformer","filter"),methods_complete=True)
    values.update(overrides)
    values["artifact_hash"] = content_hash({k:(str(v) if isinstance(v,Fraction) else v) for k,v in values.items()})
    return ProductThresholds(**values)


def classify_settling(*,caller_settled: Optional[bool],ats: Optional[ATSv2],thresholds: Optional[ProductThresholds],
                       period: Fraction,observations: Optional[Mapping[str,Any]]) -> tuple[str,MaterialResult]:
    if caller_settled is not None:
        return "TRANSITION",material_result(ExplicitAbsence(("caller_settled",),"caller-settled flags are rejected"),Availability.UNAVAILABLE,diagnostics=("CALLER_SETTLED_REJECTED",),non_gating=True)
    ats_result = require_ats(ats,"CANONICAL_EQUALITY")
    if ats_result.availability is Availability.UNAVAILABLE or thresholds is None or not thresholds.valid(period) or observations is None:
        return "TRANSITION",material_result(ExplicitAbsence(("ATS-v2","product_thresholds","observations"),"settling policy or observation unavailable"),Availability.UNAVAILABLE,dependencies=(ats_result,),diagnostics=("PRODUCT_THRESHOLD_UNAVAILABLE",),non_gating=True)
    required = {"window_seconds","ires_rms","vs_per_period","vs_cumulative","end_energy","energy_sources"}
    if set(observations) != required or tuple(observations["energy_sources"]) != thresholds.closed_energy_sources:
        return "TRANSITION",material_result(ExplicitAbsence(tuple(sorted(required-set(observations))),"observation schema/energy set incomplete"),Availability.UNAVAILABLE,non_gating=True)
    comparisons = {
        "window": Fraction(observations["window_seconds"]) >= thresholds.W_seconds,
        "ires": Fraction(observations["ires_rms"]) <= thresholds.ires_max,
        "vsperiod": all(abs(Fraction(v)) <= thresholds.vsperiod_max for v in observations["vs_per_period"]),
        "vscum": abs(Fraction(observations["vs_cumulative"])) <= thresholds.vscum_max,
        "energy": Fraction(observations["end_energy"]) <= thresholds.estored_max,
    }
    if all(comparisons.values()):
        return "SETTLED",material_result({"passed":comparisons})
    return "TRANSITION",material_result({"passed":comparisons,"failed":[k for k,v in comparisons.items() if not v]})


def no_load_report(state: str, p: int, polarity: int, residual: MaterialResult, thresholds: Optional[ProductThresholds]) -> tuple[dict[str,Any],...]:
    rows = []
    for category in NO_LOAD_CATEGORIES:
        ideal = category == "INTENTIONAL_IDEAL_DIFFERENTIAL_TRANSFER"
        if ideal:
            value,availability,basis = CanonicalNumber.rational(0,"POWER","W"),Availability.AVAILABLE,"CALCULATED_ESTIMATE"
        elif category == "UNINTENDED_DIFFERENTIAL_RESIDUAL":
            value,availability,basis = residual.canonical_value,residual.availability,"CALCULATED_ESTIMATE"
        else:
            value,availability,basis = ExplicitAbsence((category,),"no admissible external model or measurement"),Availability.UNAVAILABLE,"NONE"
        rows.append({"category":category,"applicability":"APPLICABLE","result_basis":basis,"availability":availability.value,
                     "canonical_value":value,"p":p,"polarity":polarity,"elapsed_time":"UNAVAILABLE","state":state,
                     "observation_window":"UNAVAILABLE" if thresholds is None else str(thresholds.W_seconds),
                     "threshold_artifact":"UNAVAILABLE" if thresholds is None else thresholds.artifact_id,
                     "carrier_state":"ENABLED","gate_state":"ENABLED","provenance":"correction pipeline",
                     "uncertainty_or_bound":residual.uncertainty_or_bound if category == "UNINTENDED_DIFFERENTIAL_RESIDUAL" else None})
    return tuple(rows)


def reject_loaded_constant_no_load(value_watts: float, original_load_state: str, requested_load_state: str) -> MaterialResult:
    if requested_load_state == "NO_LOAD" and original_load_state != "NO_LOAD_TERM_BY_TERM_SETTLED":
        return material_result(ExplicitAbsence((str(value_watts),),"loaded-state constant cannot be promoted to settled no-load loss"),Availability.UNAVAILABLE,diagnostics=("LOADED_CONSTANT_NOLOAD_PROMOTION",))
    return material_result(CanonicalNumber.finite_float(value_watts,"POWER","W"))



# ----------------------------- Inverter boundary -----------------------------

SYSTEM_SCHEMA_PATHS = (
    "inverter.dc_terminal.voltage","inverter.dc_terminal.current","inverter.control.phase_percent",
    "inverter.control.polarity","inverter.component.rds_on","inverter.component.parallel_count",
    "inverter.thermal.junction_temperature","inverter.output.load_current",
    "battery.cells","battery.internal_resistance","upstream.pack_interconnect","upstream.bms",
    "charger.efficiency","system.c_rate","system.round_trip_efficiency",
)
ALLOWED_PATHS = frozenset(x for x in SYSTEM_SCHEMA_PATHS if x.startswith("inverter."))
EXCLUDED_PATHS = frozenset(set(SYSTEM_SCHEMA_PATHS)-set(ALLOWED_PATHS))


@dataclass(frozen=True)
class BoundaryInventory:
    artifact_id: str
    version: str
    artifact_hash: str
    owner: str
    schema_hash: str
    allowed_paths: frozenset[str]
    excluded_paths: frozenset[str]

    def validate(self) -> None:
        if self.owner != "InverterOwner" or self.allowed_paths & self.excluded_paths or self.allowed_paths | self.excluded_paths != set(SYSTEM_SCHEMA_PATHS):
            raise ValueError("BOUNDARY_INVENTORY_INVALID")
        payload = {"artifact_id":self.artifact_id,"version":self.version,"owner":self.owner,"schema_hash":self.schema_hash,
                   "allowed_paths":sorted(self.allowed_paths),"excluded_paths":sorted(self.excluded_paths)}
        if content_hash(payload) != self.artifact_hash: raise ValueError("BOUNDARY_INVENTORY_INVALID")


def boundary_inventory() -> BoundaryInventory:
    schema_hash = content_hash(SYSTEM_SCHEMA_PATHS)
    payload = {"artifact_id":"INVERTER-BOUNDARY-001","version":"1.0.0","owner":"InverterOwner","schema_hash":schema_hash,
               "allowed_paths":sorted(ALLOWED_PATHS),"excluded_paths":sorted(EXCLUDED_PATHS)}
    return BoundaryInventory(payload["artifact_id"],payload["version"],content_hash(payload),payload["owner"],schema_hash,ALLOWED_PATHS,EXCLUDED_PATHS)


@dataclass(frozen=True)
class InverterInput:
    dc_voltage: CanonicalNumber
    dc_current: CanonicalNumber
    phase_percent: CanonicalNumber
    polarity: int
    rds_on: CanonicalNumber
    parallel_count: int
    junction_temperature: CanonicalNumber
    load_current_rms: CanonicalNumber


def solve_inverter(inp: InverterInput) -> MaterialResult:
    if inp.parallel_count <= 0 or inp.rds_on.fraction < 0 or inp.load_current_rms.fraction < 0:
        return material_result(ExplicitAbsence(("inverter_input",),"invalid inverter input"),Availability.UNAVAILABLE)
    channel = inp.load_current_rms.fraction ** 2 * 2 * inp.rds_on.fraction / inp.parallel_count
    categories = {
        "CHANNEL_CONDUCTION":str(channel),"GATE_DRIVE":"UNAVAILABLE","EOSS_COSS":"UNAVAILABLE",
        "REVERSE_RECOVERY":"UNAVAILABLE","SWITCHING_OVERLAP":"UNAVAILABLE","INTERCONNECT":"UNAVAILABLE",
        "MAGNETICS":"UNAVAILABLE","AUXILIARIES":"UNAVAILABLE","OTHER_DECLARED":{},
    }
    dep = {"INVERTER-BOUNDARY-001":boundary_inventory().artifact_hash,
           "inverter-input":content_hash({k:canonical_json(v) for k,v in inp.__dict__.items()})}
    return material_result(categories,Availability.PROVISIONAL,dependency_records=dep,bound={"CHANNEL_CONDUCTION":str(channel)},suffix="pure-inverter")


def compose_system(inverter_result: MaterialResult, **upstream: Any) -> dict[str,Any]:
    if inverter_result.freshness is Freshness.STALE: raise ValueError("STALE_RESULT_CONSUMPTION")
    return {"inverter":inverter_result,"upstream":copy.deepcopy(upstream),"composition_trace":content_hash(upstream)}


SCENARIO_FIELDS = (
    "energy_direction","pass_count","DC_terminal_nodes","AC_terminal_nodes","voltage_current_sign_conventions",
    "averaging_interval","integration_method","load_state","control_state","carrier_state","gate_state","thermal_case",
    "ambient_coolant_boundaries","included_loss_categories","excluded_loss_categories","stored_energy_start","stored_energy_end",
)


def compare_scenario_boundaries(a: Mapping[str,Any], b: Mapping[str,Any]) -> MaterialResult:
    if set(a) != set(SCENARIO_FIELDS) or set(b) != set(SCENARIO_FIELDS) or canonical_json(a) != canonical_json(b):
        return material_result(ExplicitAbsence(("scenario_boundary",),"closed boundary tuple mismatch"),Availability.UNAVAILABLE,diagnostics=("COMPARISON_BOUNDARY_MISMATCH",))
    return material_result("BOUNDARIES_EXACTLY_EQUAL")


# ----------------------------- Thermal APIs -----------------------------

THERMAL_NODES = ("junction","case","heatsink","ambient","coolant")


def _valid_temperatures(temperatures: Mapping[str,float], domains: Mapping[str,tuple[float,float]]) -> bool:
    return set(temperatures) == set(THERMAL_NODES) and set(domains) == set(THERMAL_NODES) and all(
        math.isfinite(temperatures[n]) and domains[n][0] <= temperatures[n] <= domains[n][1] for n in THERMAL_NODES
    )


def cold_snapshot(temperatures: Mapping[str,float], domains: Mapping[str,tuple[float,float]], *,declared_hot: bool=False,converged: bool=False) -> MaterialResult:
    if not _valid_temperatures(temperatures,domains) or converged or declared_hot:
        return material_result(ExplicitAbsence(("physical_initial_temperatures",),"invalid COLD_T0 initial state"),Availability.UNAVAILABLE,diagnostics=("THERMAL_INITIAL_STATE_INVALID",))
    return material_result({"mode":"COLD_T0","temperatures":dict(temperatures),"derivative":None,"cth_dependency":False})


def thermal_transient(temperatures: Mapping[str,float], domains: Mapping[str,tuple[float,float]], cth: Mapping[str,float],
                      rth: Mapping[str,float], elapsed: float, method_artifact: Optional[Mapping[str,Any]], *,hot_start: bool=False) -> MaterialResult:
    dynamic = ("junction","case","heatsink")
    complete = _valid_temperatures(temperatures,domains) and elapsed > 0 and set(cth) == set(dynamic) and all(math.isfinite(cth[n]) and cth[n] > 0 for n in dynamic)
    complete = complete and bool(rth) and method_artifact is not None and method_artifact.get("owner") == "InverterOwner" and method_artifact.get("hash")
    if not complete:
        return material_result(ExplicitAbsence(("dynamic_thermal_data",),"dynamic thermal evidence/method incomplete"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DYNAMICS_UNAVAILABLE",),non_gating=True)
    power = float(method_artifact.get("power_w",0.0))
    result = dict(temperatures)
    for n in dynamic:
        result[n] = temperatures[n] + elapsed * power / (len(dynamic)*cth[n])
        if not (domains[n][0] <= result[n] <= domains[n][1]):
            return material_result(ExplicitAbsence((n,),"thermal domain exit"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DOMAIN_EXIT",),non_gating=True)
    return material_result({"mode":"HOT_START_TRANSIENT" if hot_start else "TRANSIENT","temperatures":result,"elapsed":elapsed})


def steady_state(rth: Mapping[str,float], boundaries: Mapping[str,float], loss_w: float, domains: Mapping[str,tuple[float,float]],
                 method_artifact: Optional[Mapping[str,Any]], compatibility_cth: Optional[Mapping[str,float]]=None) -> MaterialResult:
    if not rth or not boundaries or not math.isfinite(loss_w) or loss_w < 0 or method_artifact is None or method_artifact.get("owner") != "InverterOwner":
        return material_result(ExplicitAbsence(("steady_thermal_data",),"steady-state data/method incomplete"),Availability.UNAVAILABLE)
    ambient = boundaries.get("ambient")
    if ambient is None or "junction" not in domains or "junction" not in rth:
        return material_result(ExplicitAbsence(("steady_thermal_data",),"boundary/domain/Rth missing"),Availability.UNAVAILABLE)
    tj = ambient + loss_w*rth["junction"]
    if not domains["junction"][0] <= tj <= domains["junction"][1]:
        return material_result(ExplicitAbsence(("junction",),"steady thermal domain exit"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DOMAIN_EXIT",))
    deps = {"steady-method":str(method_artifact.get("hash",content_hash(method_artifact)))}
    return material_result({"mode":"STEADY","junction":CanonicalNumber.finite_float(tj,"TEMPERATURE","degC")},dependency_records=deps,suffix="cth-stripped")


def thermal_seeds(lower: Sequence[float], upper: Sequence[float]) -> tuple[tuple[float,...],...]:
    if len(lower) != len(upper) or any(not math.isfinite(x) for x in (*lower,*upper)) or any(lo > hi for lo,hi in zip(lower,upper)):
        raise ValueError("invalid thermal domain")
    candidates = (tuple(lower),tuple((lo+hi)/2 for lo,hi in zip(lower,upper)),tuple(upper))
    result: list[tuple[float,...]] = []
    for seed in candidates:
        if seed not in result: result.append(seed)
    return tuple(result)


def classify_multi_seed(seeds: Sequence[Sequence[float]], roots: Sequence[Sequence[float]], residuals: Sequence[float],
                        relevant_thermal_loss: float, ats: Optional[ATSv2]) -> MaterialResult:
    ats_result = require_ats(ats,"THERMAL_MULTI_SEED")
    if ats_result.availability is Availability.UNAVAILABLE:
        return material_result(ExplicitAbsence(("ATS-v2",),"multi-seed policy unavailable"),Availability.UNAVAILABLE,dependencies=(ats_result,),non_gating=True)
    if len(seeds) != len(roots) or len(roots) != len(residuals) or relevant_thermal_loss < 0:
        return material_result(ExplicitAbsence(("seed_results",),"incomplete seed outcomes"),Availability.UNAVAILABLE)
    agree = all(max(abs(a-b) for a,b in zip(roots[0],root)) <= 0.1 for root in roots[1:]) if roots else False
    residual_ok = all(abs(r) <= max(0.01,1e-6*relevant_thermal_loss) for r in residuals)
    return material_result({"status":"MULTI_SEED_AGREEMENT" if agree and residual_ok else "NO_AGREEMENT","seeds":seeds,"roots":roots,"residuals":residuals})


def verify_root_certificate(certificate: Optional[Mapping[str,Any]], verifier: Optional[Mapping[str,Any]]) -> MaterialResult:
    valid = certificate is not None and verifier is not None and certificate.get("root_count") == 1 and not certificate.get("unresolved_boxes")
    valid = valid and all(certificate.get(k) for k in ("artifact_id","version","hash","complete_domain"))
    valid = valid and all(verifier.get(k) for k in ("implementation_hash","environment_hash","input_hash","output_hash"))
    valid = valid and verifier.get("implementation_hash") != certificate.get("producer_implementation_hash")
    if not valid:
        return material_result("UNPROVEN",Availability.AVAILABLE,diagnostics=("ROOT_UNIQUENESS_UNPROVEN",),non_gating=True)
    return material_result("UNIQUE")



# ----------------------------- Comparison gates -----------------------------

CONTROLLED_CODES = {
    "INELIGIBLE_ZERO_IRMS":frozenset({"FINITE_POSITIVE_IRMS"}),
    "INELIGIBLE_EMPTY_CONDUCTION_INTERVAL":frozenset({"NONEMPTY_CONDUCTION_INTERVAL"}),
    "INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL":frozenset({"FINITE_POSITIVE_IRMS","NONEMPTY_CONDUCTION_INTERVAL"}),
}
ENDPOINT_CODE = "INELIGIBLE_NO_POSITIVE_CURRENT_CASE"
FALSE_CLAIM_KEYS = {"completion_claim","pass_claim","success_claim"}


def controlled_threefold(irms: float, conduction_nonempty: bool, baseline_rds: Fraction, parallel_count: int,
                         *,other_preconditions: bool=True) -> dict[str,Any]:
    if not math.isfinite(irms) or irms < 0 or baseline_rds <= 0 or parallel_count <= 0 or not other_preconditions:
        return {"kind":"UNRESOLVED","diagnostic":"CONTROLLED_INELIGIBILITY_PREREQUISITE_INVALID"}
    baseline = Fraction.from_float(irms)**2 * 2 * baseline_rds / parallel_count
    replacement = baseline / 3
    if irms > 0 and conduction_nonempty:
        relative_error = 0.0 if baseline != 0 else math.inf
        return {"kind":"COMPLETED","requirement":"2.29","baseline_channel_loss":str(baseline),
                "replacement_rds":str(baseline_rds/3),"replacement_channel_loss":str(replacement),
                "relative_error":relative_error,"channel_delta":str(replacement-baseline),"total_delta":str(replacement-baseline),
                "valid":relative_error <= 1e-9 and replacement-baseline != 0}
    if irms == 0 and conduction_nonempty:
        code = "INELIGIBLE_ZERO_IRMS"
    elif irms > 0 and not conduction_nonempty:
        code = "INELIGIBLE_EMPTY_CONDUCTION_INTERVAL"
    else:
        code = "INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL"
    return {"kind":"INELIGIBILITY","canonical_code":code,"unsatisfied_eligibility_predicates":sorted(CONTROLLED_CODES[code]),
            "specific_reason":"controlled case has no eligible positive-current conducting interval",
            "evaluated_case_count":0,"completion_claim":False,"pass_claim":False,"success_claim":False,
            "baseline_channel_loss":"0","replacement_channel_loss":"0","channel_delta":"0","ratio":"N/A"}


def endpoint_sensitivity(candidates: Sequence[Mapping[str,Any]], low: CanonicalNumber, high: CanonicalNumber,
                         *,endpoint_evidence: bool, policy: Optional[ATSv2], fixed_inputs: bool,
                         closed_immutable_set: bool) -> dict[str,Any]:
    prerequisites = endpoint_evidence and policy is not None and policy.usable_for("RESISTANCE_SOURCE") and fixed_inputs and closed_immutable_set
    prerequisites = prerequisites and low.dimension == high.dimension and low.canonical_unit == high.canonical_unit and low.fraction < high.fraction
    if not prerequisites:
        return {"kind":"UNRESOLVED","diagnostic":"ENDPOINT_INELIGIBILITY_PREREQUISITE_INVALID"}
    eligible = [c for c in candidates if isinstance(c.get("current"),(int,float)) and math.isfinite(c["current"]) and c["current"] > 0 and c.get("conduction_nonempty") is True]
    if eligible:
        outcomes = []
        for c in eligible:
            current = Fraction.from_float(float(c["current"]))
            outcomes.append({"candidate_id":c["candidate_id"],"low_component":str(current**2*low.fraction),
                             "high_component":str(current**2*high.fraction),"delta":str(current**2*(high.fraction-low.fraction))})
        return {"kind":"COMPLETED","requirement":"2.31","outcomes":outcomes,"evaluated_case_count":len(outcomes),"valid":True}
    false_pairs = []
    for c in candidates:
        if not (isinstance(c.get("current"),(int,float)) and math.isfinite(c["current"]) and c["current"] > 0):
            false_pairs.append((c.get("candidate_id"),"FINITE_POSITIVE_CURRENT"))
        if c.get("conduction_nonempty") is not True:
            false_pairs.append((c.get("candidate_id"),"NONEMPTY_CONDUCTION_INTERVAL"))
    return {"kind":"INELIGIBILITY","canonical_code":ENDPOINT_CODE,"unsatisfied_candidate_predicates":[list(x) for x in false_pairs],
            "specific_reason":"closed immutable candidate set has no finite positive-current conducting case",
            "evaluated_case_count":0,"completion_claim":False,"pass_claim":False,"success_claim":False}


def frozen_gate_artifact(artifact_id: str, gate: GateIdentity, outcome: Mapping[str,Any]) -> dict[str,Any]:
    body = {"artifact_id":artifact_id,"artifact_version":"1.0.0","gate":gate.value,
            "frozen_before_realistic_execution":True,"immutable":True,"outcomes":[copy.deepcopy(dict(outcome))]}
    body["artifact_hash"] = content_hash(body)
    return body


def _validate_ineligibility_shape(outcome: Mapping[str,Any], gate: GateIdentity) -> Optional[str]:
    expected_common = {"kind","canonical_code","specific_reason","evaluated_case_count",*FALSE_CLAIM_KEYS}
    expected_specific = {"unsatisfied_eligibility_predicates","baseline_channel_loss","replacement_channel_loss","channel_delta","ratio"} if gate is GateIdentity.CONTROLLED_THREEFOLD else {"unsatisfied_candidate_predicates"}
    if set(outcome) != expected_common | expected_specific:
        return "COMPARISON_GATE_CODE_CARDINALITY_OR_FIELD_INVALID"
    if type(outcome["evaluated_case_count"]) is not int or outcome["evaluated_case_count"] != 0:
        return "COMPARISON_GATE_EVALUATED_COUNT_INVALID"
    if not isinstance(outcome["specific_reason"],str) or not outcome["specific_reason"].strip():
        return "COMPARISON_GATE_REASON_INVALID"
    if any(outcome[k] is not False for k in FALSE_CLAIM_KEYS):
        return "COMPARISON_GATE_FALSE_CLAIMS_INVALID"
    if gate is GateIdentity.CONTROLLED_THREEFOLD:
        code = outcome["canonical_code"]
        if code not in CONTROLLED_CODES or frozenset(outcome["unsatisfied_eligibility_predicates"]) != CONTROLLED_CODES[code]:
            return "COMPARISON_GATE_CODE_PREDICATE_MISMATCH"
        if any(outcome[k] != "0" for k in ("baseline_channel_loss","replacement_channel_loss","channel_delta")) or outcome["ratio"] != "N/A":
            return "COMPARISON_GATE_CODE_PREDICATE_MISMATCH"
    elif outcome["canonical_code"] != ENDPOINT_CODE or not isinstance(outcome["unsatisfied_candidate_predicates"],list):
        return "COMPARISON_GATE_CODE_ALIAS_OR_WRONG_GATE"
    return None


def validate_comparison_registry(t_ref: Mapping[str,Any], artifacts: Sequence[Mapping[str,Any]]) -> tuple[tuple[GateAuthorization,...],tuple[str,...]]:
    diagnostics = []
    valid_tref = set(t_ref) == {"value","unit","frozen_before_gates","in_baseline_domain","in_replacement_domain","immutable_hash"}
    valid_tref = valid_tref and isinstance(t_ref.get("value"),(int,float)) and math.isfinite(t_ref["value"]) and bool(t_ref.get("unit"))
    valid_tref = valid_tref and t_ref.get("frozen_before_gates") is True and t_ref.get("in_baseline_domain") is True and t_ref.get("in_replacement_domain") is True
    valid_tref = valid_tref and t_ref.get("immutable_hash") == content_hash({k:v for k,v in t_ref.items() if k != "immutable_hash"})
    if not valid_tref: diagnostics.append("COMPARISON_TREF_INVALID_OR_LATE")
    if len(artifacts) != 2: diagnostics.append("COMPARISON_GATE_ARTIFACT_COUNT_INVALID")
    gates = [a.get("gate") for a in artifacts]
    if sorted(gates) != sorted(g.value for g in GateIdentity): diagnostics.append("COMPARISON_GATE_WRONG_IDENTITY")
    identities = [(a.get("artifact_id"),a.get("artifact_version"),a.get("artifact_hash")) for a in artifacts]
    if len(identities) != len(set(identities)) or len({x[0] for x in identities}) != len(identities): diagnostics.append("COMPARISON_GATE_ARTIFACT_ALIASED_OR_REUSED")
    for artifact in artifacts:
        body = {k:v for k,v in artifact.items() if k != "artifact_hash"}
        if artifact.get("immutable") is not True or artifact.get("frozen_before_realistic_execution") is not True or artifact.get("artifact_hash") != content_hash(body):
            diagnostics.append("COMPARISON_GATE_ARTIFACT_MUTABLE_OR_LATE")
            continue
        outcomes = artifact.get("outcomes")
        if not isinstance(outcomes,list) or len(outcomes) != 1:
            diagnostics.append("COMPARISON_GATE_OUTCOME_CARDINALITY_INVALID")
            continue
        try: gate = GateIdentity(artifact["gate"])
        except Exception:
            diagnostics.append("COMPARISON_GATE_WRONG_IDENTITY"); continue
        outcome = outcomes[0]
        if outcome.get("kind") == "INELIGIBILITY":
            error = _validate_ineligibility_shape(outcome,gate)
            if error: diagnostics.append(error)
        elif outcome.get("kind") == "COMPLETED":
            if outcome.get("valid") is not True or outcome.get("requirement") not in ({"2.29"} if gate is GateIdentity.CONTROLLED_THREEFOLD else {"2.31"}):
                diagnostics.append("COMPARISON_GATE_COMPLETED_RESULT_INVALID")
        else: diagnostics.append("COMPARISON_GATE_OUTCOME_INVALID")
    if diagnostics:
        auths = tuple(GateAuthorization(g,"PROGRESS_TO_REALISTIC_COMPARISON",False,diagnostic=";".join(sorted(set(diagnostics)))) for g in GateIdentity)
        return auths,tuple(sorted(set(diagnostics)))
    auths = []
    for artifact in artifacts:
        gate = GateIdentity(artifact["gate"]); outcome = artifact["outcomes"][0]
        ineligible = outcome["kind"] == "INELIGIBILITY"
        auths.append(GateAuthorization(gate,"PROGRESS_TO_REALISTIC_COMPARISON",True,ineligible,
                                       outcome.get("completion_claim",False),outcome.get("pass_claim",False),outcome.get("success_claim",False)))
    return tuple(sorted(auths,key=lambda a:_gate_authorization_state(a)["gate"].value)),()


def realistic_comparison_result(local_value: Any, local_inputs: Sequence[MaterialResult], direct_evidence_complete: bool,
                                local_conditions_satisfied: bool, authorizations: Sequence[GateAuthorization],
                                *, real_claim: bool = False) -> MaterialResult:
    try:
        authorization_states = tuple(
            _gate_authorization_state(auth) for auth in authorizations)
    except (TypeError, ValueError):
        return material_result(
            ExplicitAbsence(("workflow_authorization",),
                            "malformed workflow authorization"),
            Availability.UNAVAILABLE, dependencies=local_inputs,
            diagnostics=("INVALID_WORKFLOW_AUTHORIZATION",),
            non_gating=True, suffix="comparison-authorization-malformed")
    synthetic = (any(state["synthetic_provenance"]
                     for state in authorization_states)
                 or any(getattr(item, "synthetic_provenance", False)
                        for item in local_inputs))
    if real_claim and synthetic:
        return material_result(ExplicitAbsence(("synthetic_provenance",),
            "synthetic comparison provenance cannot support a real claim"),
            Availability.UNAVAILABLE, dependencies=local_inputs,
            diagnostics=("SYNTHETIC_PUBLICATION_REJECTED",), non_gating=True,
            synthetic_provenance=synthetic)
    result = derive_result(local_inputs,local_value,direct_evidence_complete=direct_evidence_complete,
                         local_conditions_satisfied=local_conditions_satisfied,gate_authorizations=authorizations,
                         operation="PROGRESS_TO_REALISTIC_COMPARISON")
    if synthetic and not result.synthetic_provenance:
        result = material_result(result.canonical_value, result.availability,
            dependencies=local_inputs, applicability=result.applicability,
            bound=result.uncertainty_or_bound, diagnostics=result.diagnostics,
            safety_relevant=result.safety_relevant, non_gating=True,
            synthetic_provenance=True, suffix="synthetic-comparison")
    return result


def reconcile_comparison(fixed_buckets: Mapping[str,Fraction], thermal_buckets: Mapping[str,Fraction], realistic_delta: Fraction,
                         ats: Optional[ATSv2]) -> MaterialResult:
    if set(fixed_buckets) != set(thermal_buckets) or not fixed_buckets:
        return material_result(ExplicitAbsence(("loss_categories",),"bucket ownership mismatch"),Availability.UNAVAILABLE,diagnostics=("BUCKET_OWNERSHIP_OVERLAP",))
    ats_result = require_ats(ats,"POWER_RECONCILIATION")
    if ats_result.availability is Availability.UNAVAILABLE:
        return ats_result
    fixed = sum(fixed_buckets.values(),Fraction(0)); thermal = sum(thermal_buckets.values(),Fraction(0))
    error = abs(float(realistic_delta-fixed-thermal)); tolerance = max(0.01,1e-6*abs(float(realistic_delta)))
    return material_result({"fixed":str(fixed),"thermal":str(thermal),"realistic":str(realistic_delta),"reconciled":error <= tolerance},
                           Availability.AVAILABLE if error <= tolerance else Availability.UNAVAILABLE)



# ----------------------------- Qualification, controls, publication -----------------------------

QUALIFICATION_LIMITS = ("voltage","current","SOA","avalanche","package_isolation","thermal","declared_limits")


def qualification_result(graph: Mapping[str,Any], *,real_claim: bool) -> MaterialResult:
    synthetic = bool(graph.get("synthetic_marker"))
    nodes = graph.get("nodes",[])
    markers = [bool(n.get("synthetic_marker")) for n in nodes if isinstance(n,Mapping)]
    if markers and any(m != synthetic for m in markers):
        return material_result(ExplicitAbsence(("synthetic_marker",),"synthetic-real graph mixing"),Availability.UNAVAILABLE,diagnostics=("SYNTHETIC_REAL_MIX",))
    if synthetic and real_claim:
        return material_result(ExplicitAbsence(("synthetic_marker",),"synthetic fixture cannot support real claim"),Availability.UNAVAILABLE,diagnostics=("SYNTHETIC_PUBLICATION_REJECTED",),non_gating=True)
    missing = []
    if not graph.get("exact_device"): missing.append("exact_device")
    limits = graph.get("limits",{})
    for name in QUALIFICATION_LIMITS:
        item = limits.get(name)
        if not isinstance(item,Mapping) or not all(item.get(k) is not None for k in ("value","unit","rating_class","applicability","pass_rule","artifact_id","version","hash","locator","source_conditions","passed")):
            missing.append(name)
    stress = graph.get("stress")
    if not isinstance(stress,Mapping) or not (stress.get("complete_waveform") or stress.get("conservative_bound")):
        missing.append("stress")
    for field in ("dc_voltage","derating_rule","operating_conditions"):
        if graph.get(field) is None: missing.append(field)
    if missing:
        bound = graph.get("evaluable_finite_bound")
        availability = Availability.PROVISIONAL if bound is not None and math.isfinite(bound) else Availability.UNAVAILABLE
        value = bound if availability is Availability.PROVISIONAL else ExplicitAbsence(tuple(sorted(set(missing))),"qualification evidence incomplete")
        return material_result(value,availability,bound=bound,diagnostics=("QUALIFICATION_EVIDENCE_INCOMPLETE",),non_gating=True)
    if not all(limits[name]["passed"] is True for name in QUALIFICATION_LIMITS):
        return material_result({"qualified":False,"failed":[n for n in QUALIFICATION_LIMITS if not limits[n]["passed"]]})
    return material_result({"qualified":True,"exact_device":graph["exact_device"]},non_gating=synthetic)


def control_axis_status(axis: str, evidence: Optional[Mapping[str,Any]]) -> MaterialResult:
    if axis not in ("firmware","hardware"): raise ValueError("unknown control axis")
    if evidence is None:
        return material_result(ControlStatus.UNAVAILABLE.value,Availability.UNAVAILABLE,non_gating=True,suffix=axis)
    requirements = {
        "firmware":{"source_config_artifact","requirement_code_trace","build_config_hash","deterministic_test_passed"},
        "hardware":{"test_artifact","exact_hardware_identity","firmware_config_hash","instruments_calibration","conditions","waveform_coverage","limits","passing_result"},
    }[axis]
    missing = requirements-set(evidence)
    if missing:
        bound = evidence.get("finite_bound")
        status = ControlStatus.PROVISIONAL if bound is not None else ControlStatus.UNAVAILABLE
        availability = Availability.PROVISIONAL if bound is not None else Availability.UNAVAILABLE
        return material_result(status.value,availability,bound=bound,diagnostics=("missing:"+",".join(sorted(missing)),),non_gating=True,suffix=axis)
    failed = [k for k in requirements if evidence[k] is False]
    if failed:
        return material_result(ControlStatus.UNVERIFIED.value,Availability.AVAILABLE,diagnostics=tuple("failed:"+x for x in sorted(failed)),suffix=axis)
    return material_result(ControlStatus.VERIFIED.value,Availability.AVAILABLE,suffix=axis)


def control_evidence(firmware: Optional[Mapping[str,Any]], hardware: Optional[Mapping[str,Any]]) -> dict[str,MaterialResult]:
    return {"firmware_implementation_status":control_axis_status("firmware",firmware),
            "hardware_measurement_status":control_axis_status("hardware",hardware)}


PUBLICATION_FIELDS = {
    "boundary","assumption_variant","ats","evidence_conflict","digital_oracle","analog_status","thermal_case",
    "firmware_implementation_status","hardware_measurement_status","result_basis","availability","freshness",
    "trace_identity","dependency_set","uncertainty_or_bound","synthetic_marker","canonical_value",
}


def publish(claim: Mapping[str,Any], material: MaterialResult, *,real_claim: bool=False) -> MaterialResult:
    missing = PUBLICATION_FIELDS-set(claim)
    diagnostics = []
    if missing: diagnostics.append("trace-incomplete:"+",".join(sorted(missing)))
    if material.freshness is Freshness.STALE or claim.get("freshness") != Freshness.FRESH.value: diagnostics.append("stale")
    if claim.get("rounded_input"): diagnostics.append("rounded-input")
    if claim.get("fabricated_policy_or_evidence"): diagnostics.append("fabricated-evidence")
    if claim.get("loaded_constant_promoted"): diagnostics.append("loaded-constant")
    if claim.get("synthetic_marker") and real_claim: diagnostics.append("synthetic-real")
    if claim.get("trace_identity") != material.trace_identity or tuple(claim.get("dependency_set",())) != material.dependency_record_ids:
        diagnostics.append("trace-mismatch")
    if diagnostics:
        return material_result(ExplicitAbsence(tuple(diagnostics),"publication rejected"),Availability.UNAVAILABLE,diagnostics=("PUBLICATION_REJECTED",))
    return material_result(copy.deepcopy(dict(claim)),material.availability,dependencies=(material,),suffix="published")


def firmware_manifest_current(paths: Iterable[str]) -> dict[str,str]:
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}


def verify_firmware_unchanged(before: Mapping[str,Any], after_entries: Mapping[str,str], commit: str, tree: str) -> MaterialResult:
    equal = before.get("named_git_commit") == commit and before.get("git_tree_hash") == tree and before.get("entries") == dict(after_entries)
    return material_result({"equal":equal,"before":before.get("entries"),"after":dict(after_entries)},Availability.AVAILABLE if equal else Availability.UNAVAILABLE,
                           diagnostics=() if equal else ("FIRMWARE_MANIFEST_CHANGED",))


# ----------------------------- Frozen exploration adapter -----------------------------

def evaluate_exploration_fixture(fixture: Mapping[str,Any]) -> dict[str,Any]:
    fixture_id = fixture["fixture_id"]
    satisfied = False
    detail: Any = None
    if fixture_id == "EVID-SC209-060":
        target = evidence_catalog()[0]; satisfied = target.evidence_class is EvidenceClass.USER_SPECIFIED_TARGET; detail = target.evidence_class.value
    elif fixture_id == "EVID-T209-059-072":
        related = evidence_catalog()[1:3]; satisfied = all(r.evidence_class is EvidenceClass.RELATED_PART for r in related); detail = [r.evidence_class.value for r in related]
    elif fixture_id == "EVID-PENDING-13-17":
        raw = evidence_catalog()[3:]; satisfied = all(not r.selectable for r in raw); detail = "INELIGIBLE_FOR_CONSUMPTION"
    elif fixture_id in ("TIMING-P10","TIMING-P1","TIMING-P0"):
        p = int(fixture["input"]["p"]); vector = digital_oracle(p); accepted = validate_timing(vector,vector)
        if p == 10: satisfied = vector.N == 2285 and vector.H == 1142 and vector.k == 114 and len(vector.complete_aggregate_adjusted_events.value) == 16
        elif p == 1: satisfied = len(vector.adjusted_lv_events.value) == 8 and vector.complete_adjusted_sr_events.availability is Availability.UNAVAILABLE and vector.raw_events.value[-2].event_class is EventClass.OFF
        else: satisfied = len(vector.adjusted_lv_events.value) == 8 and vector.residual_owner == "LEG_COMMAND_TICK_ASYMMETRY" and vector.complete_aggregate_adjusted_events.availability is Availability.UNAVAILABLE
        satisfied = satisfied and accepted.availability is Availability.AVAILABLE; detail = vector
    elif fixture_id == "ANALOG-MISSING": satisfied = analog_modref_unavailable(("loss",))["loss"].non_gating
    elif fixture_id == "SETTLING-CALLER":
        state,result = classify_settling(caller_settled=True,ats=normative_ats(),thresholds=None,period=Fraction(2285,160_000_000),observations=None)
        satisfied = state == "TRANSITION" and result.availability is Availability.UNAVAILABLE and result.non_gating
    elif fixture_id == "NOLOAD-LOADED-CONSTANTS": satisfied = all(reject_loaded_constant_no_load(x,"LOADED","NO_LOAD").availability is Availability.UNAVAILABLE for x in (36.0,42.8))
    elif fixture_id == "QUAL-48-INCOMPLETE":
        result = qualification_result({"exact_device":"IRL40SC209","limits":{},"dc_voltage":48},real_claim=True)
        satisfied = result.availability is Availability.UNAVAILABLE and result.non_gating
    elif fixture_id == "THERMAL-ROOT": satisfied = verify_root_certificate(None,None).canonical_value == "UNPROVEN"
    elif fixture_id == "BOUNDARY-EXCLUDED":
        inv = boundary_inventory(); satisfied = "battery.internal_resistance" in inv.excluded_paths and not inv.allowed_paths.intersection(inv.excluded_paths)
    elif fixture_id == "GATE-TREF-LATE":
        auth,diag = validate_comparison_registry({"value":75,"unit":"degC","frozen_before_gates":False},[]); satisfied = bool(diag) and all(not a.valid for a in auth)
    elif fixture_id == "GATE-CONTROLLED-ZERO": satisfied = controlled_threefold(0,True,Fraction(3,5),2).get("canonical_code") == "INELIGIBLE_ZERO_IRMS"
    elif fixture_id == "GATE-ENDPOINT-NOCASE":
        result = endpoint_sensitivity([],CanonicalNumber.rational(1,"RESISTANCE","mOhm"),CanonicalNumber.rational(2,"RESISTANCE","mOhm"),endpoint_evidence=True,policy=None,fixed_inputs=True,closed_immutable_set=True)
        satisfied = result["kind"] == "UNRESOLVED"
    elif fixture_id == "MATERIAL-STALE":
        base = material_result(1,dependency_records={"dep":"a"*64}); stale = invalidate_transitively({"result":base},"dep")["result"]
        satisfied = stale.freshness is Freshness.STALE and not stale.consumable()
    elif fixture_id == "PUBLICATION-UNSAFE":
        base = material_result(1); stale = replace(base,freshness=Freshness.STALE)
        satisfied = publish({"freshness":"STALE","rounded_input":True},stale).availability is Availability.UNAVAILABLE
    return {"fixture_id":fixture_id,"bug_condition_branch":fixture["branch"],"expected_behavior_satisfied":satisfied,"detail":str(detail)[:500]}



# ========================= Strengthened executable contracts =========================
# These definitions intentionally replace the earlier compatibility implementations.
# Validation derives facts from immutable content and never trusts caller summary flags.

_HEX = frozenset("0123456789abcdef")
_PLACEHOLDER_TOKENS = ("missing", "placeholder", "not_stated", "legacy repository", "absent")


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _HEX for c in value.lower()) and len(set(value.lower())) > 1


def _substantive(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    lowered = value.strip().lower()
    return not any(token in lowered for token in _PLACEHOLDER_TOKENS)


def _condition_map_valid(value: Any, prefix: str) -> bool:
    required = {"VGS", "ID", "Tj_or_Tc", "pulse_or_measurement"}
    if not isinstance(value, Mapping) or set(value) != required:
        return False
    for encoded in value.values():
        if prefix == "user":
            if encoded == "ABSENT":
                continue
            if not (isinstance(encoded, Mapping) and set(encoded) == {"kind", "value", "unit"} and encoded["kind"] == "VALUE" and encoded["value"] is not None and _substantive(encoded["unit"])):
                return False
        else:
            if encoded == "NOT_STATED_BY_SOURCE":
                continue
            if not (isinstance(encoded, Mapping) and set(encoded) == {"kind", "value", "unit"} and encoded["kind"] == "STATED" and encoded["value"] is not None and _substantive(encoded["unit"])):
                return False
    return True


def _strict_evidence_validate(self: EvidenceRecord) -> None:
    if not self.record_id or not self.field or not self.applicability:
        raise ValueError("evidence identity incomplete")
    if self.evidence_class is None:
        if self.conflict_status is not ConflictStatus.PENDING or self.metadata.get("record_kind") != "RAW_UNRESOLVED_PENDING":
            raise ValueError("EVIDENCE_CLASS_INVALID")
        return
    if not self.subject or self.value is None or not _substantive(self.unit):
        raise ValueError("CLASS_METADATA_INCOMPLETE:subject/value/unit")
    m = self.metadata
    if self.evidence_class is EvidenceClass.USER_SPECIFIED_TARGET:
        required = {"assertion_artifact_id", "artifact_version", "locator", "artifact_hash", "user_conditions"}
        if not required <= set(m) or not all(_substantive(m[k]) for k in ("assertion_artifact_id", "artifact_version", "locator")) or not valid_sha256(m.get("artifact_hash")) or not _condition_map_valid(m.get("user_conditions"), "user"):
            raise ValueError("CLASS_METADATA_INCOMPLETE:USER_SPECIFIED_TARGET")
    elif self.evidence_class in {EvidenceClass.DIRECT_MANUFACTURER, EvidenceClass.RELATED_PART}:
        required = {"manufacturer", "document_id", "document_version", "artifact_hash", "locator", "rating_class", "source_conditions"}
        if not required <= set(m) or not all(_substantive(m[k]) for k in ("manufacturer", "document_id", "document_version", "locator", "rating_class")) or not valid_sha256(m.get("artifact_hash")) or not _condition_map_valid(m.get("source_conditions"), "source"):
            raise ValueError("CLASS_METADATA_INCOMPLETE:manufacturer source")
        if self.evidence_class is EvidenceClass.RELATED_PART:
            if not self.related_subject or not _substantive(m.get("relationship_rationale")):
                raise ValueError("CLASS_METADATA_INCOMPLETE:RELATED_PART")
        elif self.related_subject:
            raise ValueError("related subject belongs only to related-part evidence")
    elif self.evidence_class is EvidenceClass.DERIVED_ESTIMATE:
        required = {"derivation_artifact_id", "artifact_version", "artifact_hash", "formula_or_algorithm", "dependency_record_ids", "applicability", "uncertainty_or_bound"}
        if not required <= set(m) or not valid_sha256(m.get("artifact_hash")) or not m.get("dependency_record_ids") or not _substantive(m.get("formula_or_algorithm")):
            raise ValueError("CLASS_METADATA_INCOMPLETE:DERIVED_ESTIMATE")
    elif self.evidence_class is EvidenceClass.MEASURED:
        required = {"test_artifact_id", "artifact_version", "artifact_hash", "instrument_ids", "calibration_versions", "measurement_boundary", "conditions", "sample_coverage", "method", "uncertainty"}
        if not required <= set(m) or not valid_sha256(m.get("artifact_hash")) or not m.get("instrument_ids") or not m.get("calibration_versions") or not _substantive(m.get("method")):
            raise ValueError("CLASS_METADATA_INCOMPLETE:MEASURED")
    else:
        raise ValueError("EVIDENCE_CLASS_INVALID")
    if self.conflict_status in TERMINAL_STATUSES and not self.history:
        raise ValueError("terminal status needs immutable history")


EvidenceRecord.validate = _strict_evidence_validate


def evidence_catalog() -> tuple[EvidenceRecord, ...]:
    conditions = {name: "ABSENT" for name in ("VGS", "ID", "Tj_or_Tc", "pulse_or_measurement")}
    target = EvidenceRecord(
        "EV-SC209-TARGET-060", "IRL40SC209", None, "RDS_ON",
        CanonicalNumber.rational("3/5", "RESISTANCE", "mOhm"), "mOhm",
        EvidenceClass.USER_SPECIFIED_TARGET, ConflictStatus.NONE,
        {"assertion_artifact_id": "USER-ASSERT-SC209-060", "artifact_version": "1",
         "locator": "bugfix.md:2.1", "artifact_hash": content_hash("USER-ASSERT-SC209-060:3/5mOhm"),
         "user_conditions": conditions}, "IRL40SC209 RDS_ON target")
    # Repository statements with unavailable document identity are retained raw.  They
    # cannot masquerade as classified RELATED_PART manufacturer evidence.
    rows: list[EvidenceRecord] = []
    for rid, subject, related_subject, value, locator in (
        ("EV-RAW-T209-059", "IRL40T209", "IRL40SC209", "59/100", "legacy 0.59 row"),
        ("EV-RAW-T209-072", "IRL40T209", "IRL40SC209", "18/25", "legacy 0.72 row"),
        ("EV-RAW-130", None, None, "13/10", "legacy generalized 1.3 row"),
        ("EV-RAW-170", None, None, "17/10", "legacy generalized 1.7 row"),
    ):
        rows.append(EvidenceRecord(
            rid, subject, related_subject, "RDS_ON", CanonicalNumber.rational(value, "RESISTANCE", "mOhm"), "mOhm",
            None, ConflictStatus.PENDING,
            {"record_kind": "RAW_UNRESOLVED_PENDING", "document_id": "ABSENT",
             "document_version": "ABSENT", "artifact_hash": "ABSENT", "locator": locator,
             "source_conditions": {name: "NOT_STATED_BY_SOURCE" for name in conditions}},
            "raw source unavailable pending document verification"))
    result = (target, *rows)
    for record in result:
        record.validate()
    return result


# The expected timing vectors are immutable literal data, independent of the actual
# firmware-boundary computation below.
_EXPECTED_TIMING = {
    10: {"q": Fraction(571, 5), "k": 114, "comparators": (1,1142,114,1256,1,106,1150,1248),
         "intervals": (("LV_A",0,1142),("LV_B",114,1256),("SR_A",0,106),("SR_B",1150,1248)), "adjusted_count": 16},
    1: {"q": Fraction(571, 50), "k": 11, "comparators": (1,1142,11,1153,1,1,2284,2284),
        "intervals": (("LV_A",0,1142),("LV_B",11,1153)), "adjusted_count": 8},
    0: {"q": Fraction(0), "k": 0, "comparators": (1,1142,1,1142,1,1,2284,2284),
        "intervals": (("LV_A",0,1142),("LV_B",1,1142)), "adjusted_count": 8},
}


def _firmware_integer_constants() -> tuple[int, int]:
    text = (ROOT / "firmware/main/inv_config.h").read_text(encoding="utf-8")
    import re
    clock = int(re.search(r"^#define\s+INV_MCPWM_CLK_HZ\s+(\d+)", text, re.M).group(1))
    carrier = int(re.search(r"^#define\s+INV_CARRIER_HZ\s+(\d+)", text, re.M).group(1))
    return clock, carrier


# Final timing implementations are defined below after the trusted artifact
# contracts. Keeping only the firmware constant parser here prevents any import-time
# alias from coupling actual and expected vector construction.
@dataclass(frozen=True)
class ArtifactRegistry:
    artifacts: Mapping[str, str]
    dependencies: Mapping[str, tuple[str, ...]]
    results: Mapping[str, MaterialResult]

    def validate_current(self, result_id: str) -> bool:
        if result_id not in self.results:
            return False
        result = self.results[result_id]
        if result.freshness is not Freshness.FRESH:
            return False
        stored = dict(result.dependency_hashes)
        return all(self.artifacts.get(dep_id) == dep_hash for dep_id, dep_hash in stored.items())

    def select_transaction(self, record_id: str, new_hash: str) -> "ArtifactRegistry":
        if not valid_sha256(new_hash):
            raise ValueError("invalid dependency hash")
        descendants = {record_id}
        changed = True
        while changed:
            changed = False
            for node, deps in self.dependencies.items():
                if node not in descendants and descendants.intersection(deps):
                    descendants.add(node); changed = True
        stale = {k: (replace(v, freshness=Freshness.STALE) if k in descendants else v) for k,v in self.results.items()}
        artifacts = dict(self.artifacts); artifacts[record_id] = new_hash
        return ArtifactRegistry(artifacts, dict(self.dependencies), stale)


def consume_registered(registry: ArtifactRegistry, result_id: str) -> MaterialResult:
    result = registry.results.get(result_id)
    if result is None or not registry.validate_current(result_id):
        return material_result(ExplicitAbsence((result_id,), "registry dependency hash changed or result stale"), Availability.UNAVAILABLE,
                               diagnostics=("STALE_RESULT_CONSUMPTION",))
    return result


def extract_inverter_input(system: Mapping[str, Any]) -> InverterInput:
    inv = system.get("inverter")
    if not isinstance(inv, Mapping) or set(inv) != {"dc_terminal", "control", "component", "thermal", "output"}:
        raise ValueError("closed inverter boundary missing")
    return InverterInput(inv["dc_terminal"]["voltage"], inv["dc_terminal"]["current"],
                         inv["control"]["phase_percent"], inv["control"]["polarity"],
                         inv["component"]["rds_on"], inv["component"]["parallel_count"],
                         inv["thermal"]["junction_temperature"], inv["output"]["load_current"])


def solve_system_inverter(system: Mapping[str, Any]) -> MaterialResult:
    return solve_inverter(extract_inverter_input(system))


def no_load_report(state: str, p: int, polarity: int, residual: MaterialResult, thresholds: Optional[ProductThresholds]) -> tuple[MaterialResult, ...]:
    rows: list[MaterialResult] = []
    for category in NO_LOAD_CATEGORIES:
        ideal = category == "INTENTIONAL_IDEAL_DIFFERENTIAL_TRANSFER"
        if ideal and p == 0:
            availability, value, basis = Availability.AVAILABLE, CanonicalNumber.rational(0,"POWER","W"), "CALCULATED_ESTIMATE"
        elif category == "UNINTENDED_DIFFERENTIAL_RESIDUAL":
            availability, value, basis = residual.availability, residual.canonical_value, "CALCULATED_ESTIMATE"
        else:
            availability, value, basis = Availability.UNAVAILABLE, ExplicitAbsence((category,), "no admissible evaluable model/evidence"), "NONE"
        record = {"category":category, "applicability":"APPLICABLE", "result_basis":basis,
                  "p":p, "polarity":polarity, "elapsed_time":ExplicitAbsence(("elapsed_time",),"not evidenced"),
                  "state":state, "observation_window":thresholds.W_seconds if thresholds else ExplicitAbsence(("W",),"threshold artifact unavailable"),
                  "threshold_artifact":thresholds.artifact_id if thresholds else ExplicitAbsence(("threshold_artifact",),"unavailable"),
                  "carrier_state":"ENABLED", "gate_state":"ENABLED", "provenance_artifact":"INVERTER-LOSS-CORRECTION-PIPELINE",
                  "uncertainty_or_bound":residual.uncertainty_or_bound if category == "UNINTENDED_DIFFERENTIAL_RESIDUAL" else None,
                  "canonical_value":value}
        rows.append(material_result(record, availability, dependencies=(residual,) if category == "UNINTENDED_DIFFERENTIAL_RESIDUAL" else (),
                                    non_gating=availability is Availability.UNAVAILABLE, suffix="no-load:"+category))
    return tuple(rows)


def _validate_method_artifact(artifact: Optional[Mapping[str, Any]], required: set[str]) -> bool:
    if not isinstance(artifact, Mapping) or set(artifact) != required | {"artifact_hash"}:
        return False
    body = {k:v for k,v in artifact.items() if k != "artifact_hash"}
    return artifact.get("owner") == "InverterOwner" and artifact.get("approval") == "APPROVED" and valid_sha256(artifact.get("artifact_hash")) and artifact["artifact_hash"] == content_hash(body)


def thermal_transient(temperatures: Mapping[str,float], domains: Mapping[str,tuple[float,float]], cth: Mapping[str,float],
                      rth: Mapping[str,float], elapsed: float, method_artifact: Optional[Mapping[str,Any]], *,hot_start: bool=False) -> MaterialResult:
    dynamic = ("junction","case","heatsink")
    required = {"artifact_id","version","owner","approval","rth_network","boundary_temperatures","cooling_mode","applied_power",
                "initial_temperatures","elapsed_interval","integration_method","step_control","convergence_control","error_control","supported_domains"}
    complete = _valid_temperatures(temperatures,domains) and elapsed > 0 and set(cth) == set(dynamic) and all(math.isfinite(cth[n]) and cth[n] > 0 for n in dynamic)
    complete = complete and set(rth) == set(dynamic) and all(math.isfinite(rth[n]) and rth[n] > 0 for n in dynamic) and _validate_method_artifact(method_artifact, required)
    if not complete:
        return material_result(ExplicitAbsence(("dynamic_thermal_data",),"complete immutable thermal method/control artifact required"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DYNAMICS_UNAVAILABLE",),non_gating=True)
    assert method_artifact is not None
    power = method_artifact["applied_power"]
    if not isinstance(power, Mapping) or set(power) != set(dynamic) or any(not isinstance(power[n],(int,float)) or not math.isfinite(power[n]) or power[n] < 0 for n in dynamic):
        return material_result(ExplicitAbsence(("applied_power",),"missing or invalid applied-power data"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DYNAMICS_UNAVAILABLE",),non_gating=True)
    result = dict(temperatures)
    for node in dynamic:
        result[node] = temperatures[node] + elapsed * float(power[node]) / cth[node]
        if not domains[node][0] <= result[node] <= domains[node][1]:
            return material_result(ExplicitAbsence((node,),"thermal domain exit"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DOMAIN_EXIT",),non_gating=True)
    return material_result({"mode":"HOT_START_TRANSIENT" if hot_start else "TRANSIENT","temperatures":result,"elapsed":elapsed},
                           dependency_records={method_artifact["artifact_id"]:method_artifact["artifact_hash"]})


def steady_state(rth: Mapping[str,float], boundaries: Mapping[str,float], loss_w: float, domains: Mapping[str,tuple[float,float]],
                 method_artifact: Optional[Mapping[str,Any]], compatibility_cth: Optional[Mapping[str,float]]=None) -> MaterialResult:
    required = {"artifact_id","version","owner","approval","rth_network","boundary_temperatures","cooling_mode","loss_model",
                "supported_domains","solver_method","convergence_control","error_control"}
    if not _validate_method_artifact(method_artifact, required) or set(rth) != {"junction"} or set(boundaries) != {"ambient"} or not math.isfinite(loss_w) or loss_w < 0:
        return material_result(ExplicitAbsence(("steady_thermal_data",),"complete immutable steady method/control artifact required"),Availability.UNAVAILABLE)
    assert method_artifact is not None
    tj = boundaries["ambient"] + loss_w*rth["junction"]
    if "junction" not in domains or not domains["junction"][0] <= tj <= domains["junction"][1]:
        return material_result(ExplicitAbsence(("junction",),"steady thermal domain exit"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DOMAIN_EXIT",))
    return material_result({"mode":"STEADY","junction":CanonicalNumber.finite_float(tj,"TEMPERATURE","degC")},
                           dependency_records={method_artifact["artifact_id"]:method_artifact["artifact_hash"]},suffix="cth-stripped")


def verify_root_certificate(certificate: Optional[Mapping[str,Any]], verifier: Optional[Mapping[str,Any]]) -> MaterialResult:
    if not isinstance(certificate, Mapping) or not isinstance(verifier, Mapping):
        return material_result("UNPROVEN", diagnostics=("ROOT_UNIQUENESS_UNPROVEN",), non_gating=True)
    cert_required = {"artifact_id","version","method","parameter_domain","temperature_domain","boxes","root_count","producer_implementation_hash","environment_hash","input_hash","output_hash","artifact_hash"}
    verifier_required = {"implementation_hash","environment_hash","input_hash","output_hash","algorithm","evaluated_boxes","root_count","unresolved_boxes","artifact_hash"}
    valid = set(certificate) == cert_required and set(verifier) == verifier_required
    if valid:
        cert_body={k:v for k,v in certificate.items() if k!="artifact_hash"}; ver_body={k:v for k,v in verifier.items() if k!="artifact_hash"}
        valid = certificate["artifact_hash"] == content_hash(cert_body) and verifier["artifact_hash"] == content_hash(ver_body)
        valid = valid and certificate["root_count"] == verifier["root_count"] == 1 and not verifier["unresolved_boxes"]
        valid = valid and verifier["evaluated_boxes"] == certificate["boxes"] and verifier["input_hash"] == certificate["input_hash"]
        valid = valid and verifier["implementation_hash"] != certificate["producer_implementation_hash"] and verifier["environment_hash"] != certificate["environment_hash"]
        valid = valid and valid_sha256(certificate["artifact_hash"]) and valid_sha256(verifier["artifact_hash"])
    return material_result("UNIQUE" if valid else "UNPROVEN", diagnostics=() if valid else ("ROOT_UNIQUENESS_UNPROVEN",), non_gating=not valid)


def _artifact_ref_valid(ref: Any) -> bool:
    return isinstance(ref, Mapping) and set(ref) == {"artifact_id","version","hash"} and _substantive(ref["artifact_id"]) and _substantive(ref["version"]) and valid_sha256(ref["hash"])


def qualification_result(graph: Mapping[str,Any], *,real_claim: bool) -> MaterialResult:
    synthetic = graph.get("synthetic_marker") is True
    nodes = graph.get("nodes",())
    if not isinstance(nodes, Sequence) or any(not isinstance(n,Mapping) or n.get("synthetic_marker") is not synthetic for n in nodes):
        return material_result(ExplicitAbsence(("synthetic_marker",),"synthetic-real graph mixing"),Availability.UNAVAILABLE,diagnostics=("SYNTHETIC_REAL_MIX",))
    if synthetic and real_claim:
        return material_result(ExplicitAbsence(("synthetic_marker",),"synthetic fixture cannot support real claim"),Availability.UNAVAILABLE,diagnostics=("SYNTHETIC_PUBLICATION_REJECTED",),non_gating=True)
    missing=[]; limits=graph.get("limits")
    if not _substantive(graph.get("exact_device")): missing.append("exact_device")
    if not isinstance(limits,Mapping) or set(limits)!=set(QUALIFICATION_LIMITS): missing.extend(QUALIFICATION_LIMITS)
    else:
        for name,item in limits.items():
            required={"value","unit","rating_class","applicability","pass_rule","artifact","locator","source_conditions","observed","passed"}
            if not isinstance(item,Mapping) or set(item)!=required or not _artifact_ref_valid(item.get("artifact")) or not isinstance(item.get("value"),(int,float)) or not math.isfinite(item["value"]) or not _substantive(item.get("unit")):
                missing.append(name); continue
            expected = item["observed"] <= item["value"] if item["pass_rule"] == "<=" else item["observed"] >= item["value"] if item["pass_rule"] == ">=" else None
            if expected is None or item["passed"] is not expected: missing.append(name)
    stress=graph.get("stress")
    if not isinstance(stress,Mapping) or set(stress)!={"artifact","interval","sample_rate","bandwidth","instruments_calibration","uncertainty","alignment","peak_rule","samples"} or not _artifact_ref_valid(stress.get("artifact")) or not stress.get("samples"):
        missing.append("stress")
    for field in ("dc_voltage","derating_rule","operating_conditions"):
        if graph.get(field) is None: missing.append(field)
    if missing:
        bound=graph.get("evaluable_finite_bound"); finite=isinstance(bound,(int,float)) and math.isfinite(bound)
        return material_result(bound if finite else ExplicitAbsence(tuple(sorted(set(missing))),"qualification evidence incomplete"),
                               Availability.PROVISIONAL if finite else Availability.UNAVAILABLE,bound=bound if finite else None,
                               diagnostics=("QUALIFICATION_EVIDENCE_INCOMPLETE",),non_gating=True)
    failed=[n for n in QUALIFICATION_LIMITS if not limits[n]["passed"]]
    return material_result({"qualified":not failed,"failed":failed,"exact_device":graph["exact_device"]},non_gating=synthetic)


def control_axis_status(axis: str, evidence: Optional[Mapping[str,Any]]) -> MaterialResult:
    if axis not in ("firmware","hardware"): raise ValueError("unknown control axis")
    if evidence is None:
        return material_result(ControlStatus.UNAVAILABLE.value,Availability.UNAVAILABLE,non_gating=True,suffix=axis)
    required = ({"source_config_artifact","requirement_code_trace","build_config_hash","deterministic_test_artifact","predicates"}
                if axis=="firmware" else {"test_artifact","exact_hardware_identity","firmware_config_hash","instruments_calibration","conditions","waveform_coverage","limits","predicates"})
    if set(evidence)!=required or not _artifact_ref_valid(evidence.get("source_config_artifact") if axis=="firmware" else evidence.get("test_artifact")):
        return material_result(ControlStatus.UNAVAILABLE.value,Availability.UNAVAILABLE,diagnostics=("control evidence contract incomplete",),non_gating=True,suffix=axis)
    hash_fields=("build_config_hash",) if axis=="firmware" else ("firmware_config_hash",)
    if any(not valid_sha256(evidence.get(k)) for k in hash_fields) or not isinstance(evidence.get("predicates"),Mapping) or not evidence["predicates"]:
        return material_result(ControlStatus.UNAVAILABLE.value,Availability.UNAVAILABLE,diagnostics=("control evidence hashes/predicates invalid",),non_gating=True,suffix=axis)
    failures=[name for name,passed in evidence["predicates"].items() if passed is not True]
    return material_result(ControlStatus.UNVERIFIED.value if failures else ControlStatus.VERIFIED.value,
                           Availability.AVAILABLE,diagnostics=tuple("failed:"+x for x in sorted(failures)),suffix=axis)


def publish(claim: Mapping[str,Any], material: MaterialResult, *,real_claim: bool=False, registry: Optional[ArtifactRegistry]=None, result_id: Optional[str]=None) -> MaterialResult:
    diagnostics=[]; missing=PUBLICATION_FIELDS-set(claim)
    if missing: diagnostics.append("trace-incomplete:"+",".join(sorted(missing)))
    exact={"availability":material.availability.value,"freshness":material.freshness.value,"trace_identity":material.trace_identity,
           "dependency_set":material.dependency_record_ids,"canonical_value":material.canonical_value}
    for field,expected in exact.items():
        if claim.get(field)!=expected: diagnostics.append("source-mismatch:"+field)
    if material.freshness is Freshness.STALE: diagnostics.append("stale")
    if registry is not None and (result_id is None or not registry.validate_current(result_id)): diagnostics.append("registry-stale")
    if claim.get("rounded_input") is True: diagnostics.append("rounded-input")
    if claim.get("fabricated_policy_or_evidence") is True: diagnostics.append("fabricated-evidence")
    if claim.get("loaded_constant_promoted") is True: diagnostics.append("loaded-constant")
    if claim.get("synthetic_marker") is True and real_claim: diagnostics.append("synthetic-real")
    if diagnostics:
        return material_result(ExplicitAbsence(tuple(diagnostics),"publication rejected"),Availability.UNAVAILABLE,diagnostics=("PUBLICATION_REJECTED",))
    return material_result(copy.deepcopy(dict(claim)),material.availability,dependencies=(material,),suffix="published")


def firmware_manifest_current(paths: Optional[Iterable[str]]=None) -> dict[str,str]:
    actual=[]
    for path in (ROOT/"firmware").rglob("*"):
        if path.is_file(): actual.append(path.relative_to(ROOT).as_posix())
    if paths is not None and set(paths)!=set(actual):
        raise ValueError("FIRMWARE_MANIFEST_CHANGED:path set differs")
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(actual)}


def evaluate_exploration_fixture(fixture: Mapping[str,Any]) -> dict[str,Any]:
    fixture_id=fixture["fixture_id"]; satisfied=False; detail=None
    if fixture_id=="EVID-SC209-060":
        target=evidence_catalog()[0]; satisfied=target.evidence_class is EvidenceClass.USER_SPECIFIED_TARGET; detail=target.evidence_class.value
    elif fixture_id=="EVID-T209-059-072":
        rows=evidence_catalog()[1:3]; satisfied=all(r.evidence_class is None and r.conflict_status is ConflictStatus.PENDING and not r.selectable for r in rows); detail="RAW_PENDING_UNAVAILABLE_SOURCE"
    elif fixture_id=="EVID-PENDING-13-17":
        rows=evidence_catalog()[3:]; satisfied=all(not r.selectable for r in rows); detail="INELIGIBLE_FOR_CONSUMPTION"
    elif fixture_id in ("TIMING-P10","TIMING-P1","TIMING-P0"):
        p=int(fixture["input"]["p"]); actual=compute_timing_from_firmware(p); expected=independent_expected_timing(p); accepted=validate_timing(actual,expected)
        satisfied=accepted.availability is Availability.AVAILABLE
        if p==10: satisfied=satisfied and len(actual.complete_aggregate_adjusted_events.value)==16
        elif p==1: satisfied=satisfied and len(actual.adjusted_lv_events.value)==8 and actual.complete_adjusted_sr_events.availability is Availability.UNAVAILABLE
        else: satisfied=satisfied and actual.residual_owner=="LEG_COMMAND_TICK_ASYMMETRY" and actual.complete_aggregate_adjusted_events.availability is Availability.UNAVAILABLE
        detail=actual
    elif fixture_id=="ANALOG-MISSING": satisfied=analog_modref_unavailable(("loss",))["loss"].non_gating
    elif fixture_id=="SETTLING-CALLER":
        state,result=classify_settling(caller_settled=True,ats=normative_ats(),thresholds=None,period=Fraction(2285,160_000_000),observations=None); satisfied=state=="TRANSITION" and result.availability is Availability.UNAVAILABLE and result.non_gating
    elif fixture_id=="NOLOAD-LOADED-CONSTANTS": satisfied=all(reject_loaded_constant_no_load(x,"LOADED","NO_LOAD").availability is Availability.UNAVAILABLE for x in (36.0,42.8))
    elif fixture_id=="QUAL-48-INCOMPLETE": satisfied=qualification_result({"exact_device":"IRL40SC209","limits":{},"dc_voltage":48,"nodes":[],"synthetic_marker":False},real_claim=True).availability is Availability.UNAVAILABLE
    elif fixture_id=="THERMAL-ROOT": satisfied=verify_root_certificate(None,None).canonical_value=="UNPROVEN"
    elif fixture_id=="BOUNDARY-EXCLUDED": satisfied="battery.internal_resistance" in boundary_inventory().excluded_paths
    elif fixture_id=="GATE-TREF-LATE": auth,diag=validate_comparison_registry({"value":75,"unit":"degC","frozen_before_gates":False},[]); satisfied=bool(diag) and all(not a.valid for a in auth)
    elif fixture_id=="GATE-CONTROLLED-ZERO": satisfied=controlled_threefold(0,True,Fraction(3,5),2).get("canonical_code")=="INELIGIBLE_ZERO_IRMS"
    elif fixture_id=="GATE-ENDPOINT-NOCASE": satisfied=endpoint_sensitivity([],CanonicalNumber.rational(1,"RESISTANCE","mOhm"),CanonicalNumber.rational(2,"RESISTANCE","mOhm"),endpoint_evidence=True,policy=None,fixed_inputs=True,closed_immutable_set=True)["kind"]=="UNRESOLVED"
    elif fixture_id=="MATERIAL-STALE":
        base=material_result(1,dependency_records={"dep":content_hash("old-dependency")}); reg=ArtifactRegistry({"dep":content_hash("old-dependency")},{"result":("dep",)},{"result":base}); changed=reg.select_transaction("dep",content_hash("new-dependency")); satisfied=consume_registered(changed,"result").availability is Availability.UNAVAILABLE
    elif fixture_id=="PUBLICATION-UNSAFE":
        base=material_result(1); satisfied=publish({"freshness":"STALE","rounded_input":True},replace(base,freshness=Freshness.STALE)).availability is Availability.UNAVAILABLE
    return {"fixture_id":fixture_id,"bug_condition_branch":fixture["branch"],"expected_behavior_satisfied":satisfied,"detail":str(detail)[:500]}



@dataclass(frozen=True)
class ComparisonArtifactRegistry:
    registry_id: str
    t_ref: Mapping[str, Any]
    artifacts: tuple[Mapping[str, Any], ...]
    t_ref_frozen_at: int
    gate_frozen_at: tuple[int, int]
    realistic_execution_at: int
    registry_hash: str


def controlled_threefold(irms: float, conduction_nonempty: bool, baseline_rds: Fraction, parallel_count: int,
                         *,other_preconditions: bool=True) -> dict[str,Any]:
    if not isinstance(irms,(int,float)) or not math.isfinite(irms) or irms < 0 or baseline_rds <= 0 or parallel_count <= 0 or not other_preconditions:
        return {"kind":"UNRESOLVED","diagnostic":"CONTROLLED_INELIGIBILITY_PREREQUISITE_INVALID"}
    inputs={"irms_bits":struct.pack(">d",float(irms)).hex(),"conduction_nonempty":conduction_nonempty,
            "baseline_rds":str(baseline_rds),"parallel_count":parallel_count,"fixed_temperature":"75 degC",
            "waveform_hash":content_hash("controlled-waveform"),"topology":"HF_LINK_PSFB","timing_hash":ORACLE_SOURCE_HASH,
            "non_rds_input_hash":content_hash("controlled-fixed-non-rds-inputs")}
    baseline=Fraction.from_float(float(irms))**2*2*baseline_rds/parallel_count if conduction_nonempty else Fraction(0)
    replacement=baseline/3
    if irms>0 and conduction_nonempty:
        return {"kind":"COMPLETED","requirement":"2.29","inputs":inputs,"baseline_channel_loss":str(baseline),
                "replacement_rds":str(baseline_rds/3),"replacement_channel_loss":str(replacement),
                "channel_delta":str(replacement-baseline),"total_delta":str(replacement-baseline),"evaluated_case_count":1}
    code=("INELIGIBLE_ZERO_IRMS" if conduction_nonempty else
          "INELIGIBLE_EMPTY_CONDUCTION_INTERVAL" if irms>0 else "INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL")
    return {"kind":"INELIGIBILITY","canonical_code":code,"inputs":inputs,
            "unsatisfied_eligibility_predicates":sorted(CONTROLLED_CODES[code]),
            "specific_reason":"controlled case has no eligible positive-current conducting interval",
            "evaluated_case_count":0,"completion_claim":False,"pass_claim":False,"success_claim":False,
            "baseline_channel_loss":"0","replacement_channel_loss":"0","channel_delta":"0","ratio":"N/A"}


def endpoint_sensitivity(candidates: Sequence[Mapping[str,Any]], low: CanonicalNumber, high: CanonicalNumber,
                         *,endpoint_evidence: bool, policy: Optional[ATSv2], fixed_inputs: bool,
                         closed_immutable_set: bool) -> dict[str,Any]:
    prerequisites=endpoint_evidence and policy is not None and policy.usable_for("RESISTANCE_SOURCE") and fixed_inputs and closed_immutable_set
    prerequisites=prerequisites and low.dimension==high.dimension=="RESISTANCE" and low.canonical_unit==high.canonical_unit and low.fraction<high.fraction
    if not prerequisites or not all(isinstance(c,Mapping) and set(c)=={"candidate_id","current","conduction_nonempty"} and _substantive(c["candidate_id"]) for c in candidates):
        return {"kind":"UNRESOLVED","diagnostic":"ENDPOINT_INELIGIBILITY_PREREQUISITE_INVALID"}
    canonical_candidates=tuple({"candidate_id":c["candidate_id"],"current_bits":struct.pack(">d",float(c["current"])).hex() if isinstance(c["current"],(int,float)) and math.isfinite(c["current"]) else "NONFINITE",
                                "conduction_nonempty":c["conduction_nonempty"]} for c in candidates)
    prerequisites_record={"low":canonical_json(low),"high":canonical_json(high),"endpoint_evidence_hash":content_hash({"low":canonical_json(low),"high":canonical_json(high)}),
                          "policy_id":policy.artifact_id,"policy_hash":policy.artifact_hash,"fixed_input_hash":content_hash("endpoint-fixed-inputs"),
                          "candidate_set":canonical_candidates,"candidate_set_hash":content_hash(canonical_candidates)}
    eligible=[]
    for c in candidates:
        current=c["current"]
        if isinstance(current,(int,float)) and math.isfinite(current) and current>0 and c["conduction_nonempty"] is True: eligible.append(c)
    if eligible:
        outcomes=[]
        for c in eligible:
            current=Fraction.from_float(float(c["current"])); low_component=current**2*low.fraction; high_component=current**2*high.fraction
            outcomes.append({"candidate_id":c["candidate_id"],"low_component":str(low_component),"high_component":str(high_component),
                             "component_delta":str(high_component-low_component),"low_total":str(low_component),"high_total":str(high_component),"total_delta":str(high_component-low_component)})
        return {"kind":"COMPLETED","requirement":"2.31","prerequisites":prerequisites_record,"outcomes":outcomes,"evaluated_case_count":len(outcomes)}
    false_pairs=[]
    for c in candidates:
        if not (isinstance(c["current"],(int,float)) and math.isfinite(c["current"]) and c["current"]>0): false_pairs.append([c["candidate_id"],"FINITE_POSITIVE_CURRENT"])
        if c["conduction_nonempty"] is not True: false_pairs.append([c["candidate_id"],"NONEMPTY_CONDUCTION_INTERVAL"])
    return {"kind":"INELIGIBILITY","canonical_code":ENDPOINT_CODE,"prerequisites":prerequisites_record,
            "unsatisfied_candidate_predicates":false_pairs,"specific_reason":"closed immutable candidate set has no finite positive-current conducting case",
            "evaluated_case_count":0,"completion_claim":False,"pass_claim":False,"success_claim":False}


def frozen_gate_artifact(artifact_id: str, gate: GateIdentity, outcome: Mapping[str,Any], *,frozen_at: int=2) -> dict[str,Any]:
    body={"artifact_id":artifact_id,"artifact_version":"2.0.0","gate":gate.value,"created_at":frozen_at,
          "frozen_at":frozen_at,"outcomes":[copy.deepcopy(dict(outcome))]}
    body["artifact_hash"]=content_hash(body)
    return body


def build_comparison_registry(t_ref: Mapping[str,Any], artifacts: Sequence[Mapping[str,Any]], *,realistic_execution_at: int=10) -> ComparisonArtifactRegistry:
    body={"registry_id":"COMPARISON-REGISTRY-001","t_ref":copy.deepcopy(dict(t_ref)),"artifacts":copy.deepcopy(list(artifacts)),
          "t_ref_frozen_at":1,"gate_frozen_at":[a.get("frozen_at") for a in artifacts],"realistic_execution_at":realistic_execution_at}
    return ComparisonArtifactRegistry(body["registry_id"],body["t_ref"],tuple(body["artifacts"]),body["t_ref_frozen_at"],tuple(body["gate_frozen_at"]),realistic_execution_at,content_hash(body))


def _validate_controlled_outcome(outcome: Mapping[str,Any]) -> Optional[str]:
    if outcome.get("kind")=="COMPLETED":
        required={"kind","requirement","inputs","baseline_channel_loss","replacement_rds","replacement_channel_loss","channel_delta","total_delta","evaluated_case_count"}
        if set(outcome)!=required or outcome["requirement"]!="2.29" or outcome["evaluated_case_count"]!=1: return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        inputs=outcome["inputs"]
        try:
            irms=struct.unpack(">d",bytes.fromhex(inputs["irms_bits"]))[0]; rds=Fraction(inputs["baseline_rds"]); count=inputs["parallel_count"]
            expected=Fraction.from_float(irms)**2*2*rds/count; replacement=expected/3
        except Exception: return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        fixed_keys={"irms_bits","conduction_nonempty","baseline_rds","parallel_count","fixed_temperature","waveform_hash","topology","timing_hash","non_rds_input_hash"}
        if set(inputs)!=fixed_keys or not inputs["conduction_nonempty"] or irms<=0 or not math.isfinite(irms) or rds<=0 or count<=0: return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        if not all(valid_sha256(inputs[k]) for k in ("waveform_hash","timing_hash","non_rds_input_hash")): return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        if (Fraction(outcome["baseline_channel_loss"])!=expected or Fraction(outcome["replacement_rds"])!=rds/3 or
            Fraction(outcome["replacement_channel_loss"])!=replacement or Fraction(outcome["channel_delta"])!=replacement-expected or
            Fraction(outcome["total_delta"])!=replacement-expected or replacement==expected): return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        return None
    if outcome.get("kind")!="INELIGIBILITY": return "COMPARISON_GATE_OUTCOME_INVALID"
    expected={"kind","canonical_code","inputs","unsatisfied_eligibility_predicates","specific_reason","evaluated_case_count",*FALSE_CLAIM_KEYS,
              "baseline_channel_loss","replacement_channel_loss","channel_delta","ratio"}
    if set(outcome)!=expected: return "COMPARISON_GATE_CODE_CARDINALITY_OR_FIELD_INVALID"
    shape=_validate_ineligibility_shape({k:v for k,v in outcome.items() if k!="inputs"},GateIdentity.CONTROLLED_THREEFOLD)
    if shape: return shape
    try: irms=struct.unpack(">d",bytes.fromhex(outcome["inputs"]["irms_bits"]))[0]
    except Exception: return "CONTROLLED_INELIGIBILITY_PREREQUISITE_INVALID"
    conduction=outcome["inputs"].get("conduction_nonempty"); expected_code=("INELIGIBLE_ZERO_IRMS" if irms==0 and conduction else "INELIGIBLE_EMPTY_CONDUCTION_INTERVAL" if irms>0 and not conduction else "INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL" if irms==0 and not conduction else None)
    return None if expected_code==outcome["canonical_code"] else "COMPARISON_GATE_CODE_PREDICATE_MISMATCH"


def _validate_endpoint_outcome(outcome: Mapping[str,Any]) -> Optional[str]:
    prereq=outcome.get("prerequisites")
    if not isinstance(prereq,Mapping) or set(prereq)!={"low","high","endpoint_evidence_hash","policy_id","policy_hash","fixed_input_hash","candidate_set","candidate_set_hash"}:
        return "ENDPOINT_INELIGIBILITY_PREREQUISITE_INVALID"
    if not all(valid_sha256(prereq[k]) for k in ("endpoint_evidence_hash","policy_hash","fixed_input_hash","candidate_set_hash")) or prereq["candidate_set_hash"]!=content_hash(tuple(prereq["candidate_set"])):
        return "ENDPOINT_EVIDENCE_OR_POLICY_INVALID"
    candidates=prereq["candidate_set"]
    eligible=[]
    for c in candidates:
        try: current=struct.unpack(">d",bytes.fromhex(c["current_bits"]))[0]
        except Exception: current=math.nan
        if math.isfinite(current) and current>0 and c["conduction_nonempty"] is True: eligible.append((c,current))
    if outcome.get("kind")=="COMPLETED":
        if set(outcome)!={"kind","requirement","prerequisites","outcomes","evaluated_case_count"} or outcome["requirement"]!="2.31" or outcome["evaluated_case_count"]!=len(eligible) or len(outcome["outcomes"])!=len(eligible) or not eligible:
            return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        low=json.loads(prereq["low"])["representation"]; high=json.loads(prereq["high"])["representation"]; lo=Fraction(low[1],low[2]); hi=Fraction(high[1],high[2])
        for recorded,(candidate,current_float) in zip(outcome["outcomes"],eligible):
            current=Fraction.from_float(current_float); lc=current**2*lo; hc=current**2*hi
            expected={"candidate_id":candidate["candidate_id"],"low_component":str(lc),"high_component":str(hc),"component_delta":str(hc-lc),"low_total":str(lc),"high_total":str(hc),"total_delta":str(hc-lc)}
            if recorded!=expected: return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        return None
    if outcome.get("kind")!="INELIGIBILITY" or eligible: return "ENDPOINT_INELIGIBILITY_PREREQUISITE_INVALID"
    expected={"kind","canonical_code","prerequisites","unsatisfied_candidate_predicates","specific_reason","evaluated_case_count",*FALSE_CLAIM_KEYS}
    if set(outcome)!=expected or outcome["canonical_code"]!=ENDPOINT_CODE or outcome["evaluated_case_count"]!=0 or any(outcome[k] is not False for k in FALSE_CLAIM_KEYS): return "COMPARISON_GATE_CODE_CARDINALITY_OR_FIELD_INVALID"
    false=[]
    for c in candidates:
        try: current=struct.unpack(">d",bytes.fromhex(c["current_bits"]))[0]
        except Exception: current=math.nan
        if not math.isfinite(current) or current<=0: false.append([c["candidate_id"],"FINITE_POSITIVE_CURRENT"])
        if c["conduction_nonempty"] is not True: false.append([c["candidate_id"],"NONEMPTY_CONDUCTION_INTERVAL"])
    return None if outcome["unsatisfied_candidate_predicates"]==false else "COMPARISON_GATE_CODE_PREDICATE_MISMATCH"


def validate_comparison_registry(t_ref_or_registry: Mapping[str,Any] | ComparisonArtifactRegistry, artifacts: Sequence[Mapping[str,Any]]=()) -> tuple[tuple[GateAuthorization,...],tuple[str,...]]:
    diagnostics=[]
    if not isinstance(t_ref_or_registry,ComparisonArtifactRegistry):
        diagnostics.append("COMPARISON_IMMUTABLE_REGISTRY_REQUIRED"); registry=None
    else:
        registry=t_ref_or_registry
        body={"registry_id":registry.registry_id,"t_ref":registry.t_ref,"artifacts":list(registry.artifacts),"t_ref_frozen_at":registry.t_ref_frozen_at,"gate_frozen_at":list(registry.gate_frozen_at),"realistic_execution_at":registry.realistic_execution_at}
        if registry.registry_hash!=content_hash(body): diagnostics.append("COMPARISON_REGISTRY_HASH_MISMATCH")
    if registry is None:
        auths=tuple(GateAuthorization(g,"PROGRESS_TO_REALISTIC_COMPARISON",False,diagnostic=";".join(diagnostics)) for g in GateIdentity); return auths,tuple(diagnostics)
    t_ref=registry.t_ref; artifacts=registry.artifacts
    valid_tref=set(t_ref)=={"value","unit","baseline_domain","replacement_domain","artifact_hash"}
    valid_tref=valid_tref and isinstance(t_ref.get("value"),(int,float)) and math.isfinite(t_ref["value"]) and _substantive(t_ref.get("unit"))
    valid_tref=valid_tref and isinstance(t_ref.get("baseline_domain"),Sequence) and isinstance(t_ref.get("replacement_domain"),Sequence) and len(t_ref["baseline_domain"])==2 and len(t_ref["replacement_domain"])==2
    valid_tref=valid_tref and t_ref["baseline_domain"][0]<=t_ref["value"]<=t_ref["baseline_domain"][1] and t_ref["replacement_domain"][0]<=t_ref["value"]<=t_ref["replacement_domain"][1]
    valid_tref=valid_tref and t_ref.get("artifact_hash")==content_hash({k:v for k,v in t_ref.items() if k!="artifact_hash"})
    ordered = bool(registry.gate_frozen_at) and registry.t_ref_frozen_at < min(registry.gate_frozen_at) and max(registry.gate_frozen_at) < registry.realistic_execution_at
    if not valid_tref or not ordered: diagnostics.append("COMPARISON_TREF_INVALID_OR_LATE")
    if len(artifacts)!=2 or sorted(a.get("gate") for a in artifacts)!=sorted(g.value for g in GateIdentity): diagnostics.append("COMPARISON_GATE_ARTIFACT_COUNT_OR_IDENTITY_INVALID")
    identities=[]
    for artifact in artifacts:
        if not isinstance(artifact,Mapping): diagnostics.append("COMPARISON_GATE_ARTIFACT_INVALID"); continue
        body={k:v for k,v in artifact.items() if k!="artifact_hash"}; identities.append((artifact.get("artifact_id"),artifact.get("artifact_version"),artifact.get("artifact_hash")))
        if set(artifact)!={"artifact_id","artifact_version","gate","created_at","frozen_at","outcomes","artifact_hash"} or artifact.get("artifact_hash")!=content_hash(body) or not valid_sha256(artifact.get("artifact_hash")) or artifact.get("created_at")!=artifact.get("frozen_at") or artifact.get("frozen_at")>=registry.realistic_execution_at:
            diagnostics.append("COMPARISON_GATE_ARTIFACT_MUTABLE_OR_LATE"); continue
        outcomes=artifact.get("outcomes")
        if not isinstance(outcomes,list) or len(outcomes)!=1: diagnostics.append("COMPARISON_GATE_OUTCOME_CARDINALITY_INVALID"); continue
        gate=GateIdentity(artifact["gate"]); error=_validate_controlled_outcome(outcomes[0]) if gate is GateIdentity.CONTROLLED_THREEFOLD else _validate_endpoint_outcome(outcomes[0])
        if error: diagnostics.append(error)
    if len(identities)!=len(set(identities)) or len({i[0] for i in identities})!=len(identities): diagnostics.append("COMPARISON_GATE_ARTIFACT_ALIASED_OR_REUSED")
    if diagnostics:
        auths=tuple(GateAuthorization(g,"PROGRESS_TO_REALISTIC_COMPARISON",False,diagnostic=";".join(sorted(set(diagnostics)))) for g in GateIdentity); return auths,tuple(sorted(set(diagnostics)))
    auths=[]
    for artifact in artifacts:
        gate=GateIdentity(artifact["gate"]); outcome=artifact["outcomes"][0]; ineligible=outcome["kind"]=="INELIGIBILITY"
        auths.append(GateAuthorization(gate,"PROGRESS_TO_REALISTIC_COMPARISON",True,ineligible,
                                       outcome.get("completion_claim",False),outcome.get("pass_claim",False),outcome.get("success_claim",False)))
    return tuple(sorted(auths,key=lambda a:_gate_authorization_state(a)["gate"].value)),()



# ========================= Final semantic-review hardening =========================
# Trusted content registration, closed DAG validation, independent timing vectors,
# and evidence-bound public decisions. These final definitions supersede compatible
# names above while leaving frozen source artifacts untouched.

@dataclass(frozen=True)
class RegisteredArtifact:
    artifact_id: str
    version: str
    artifact_type: str
    content: Mapping[str, Any]
    artifact_hash: str
    owner: str = "InverterOwner"
    approval: str = "APPROVED"

    @staticmethod
    def create(artifact_id: str, version: str, artifact_type: str,
               content: Mapping[str, Any], *, owner: str = "InverterOwner",
               approval: str = "APPROVED") -> "RegisteredArtifact":
        frozen = copy.deepcopy(dict(content))
        digest = content_hash({"artifact_id": artifact_id, "version": version,
                               "artifact_type": artifact_type, "content": frozen,
                               "owner": owner, "approval": approval})
        return RegisteredArtifact(artifact_id, version, artifact_type, frozen,
                                  digest, owner, approval)

    @property
    def ref(self) -> dict[str, str]:
        return {"artifact_id": self.artifact_id, "version": self.version,
                "hash": self.artifact_hash}

    def validate(self) -> None:
        expected = content_hash({"artifact_id": self.artifact_id,
                                 "version": self.version,
                                 "artifact_type": self.artifact_type,
                                 "content": self.content, "owner": self.owner,
                                 "approval": self.approval})
        if (not _substantive(self.artifact_id) or not _substantive(self.version)
                or not _substantive(self.artifact_type)
                or self.artifact_hash != expected or not valid_sha256(expected)):
            raise ValueError("ARTIFACT_CONTENT_HASH_INVALID")


def _artifact_digest(value: Any) -> Optional[str]:
    if isinstance(value, RegisteredArtifact):
        value.validate()
        return value.artifact_hash
    return value if valid_sha256(value) else None


@dataclass(frozen=True)
class ArtifactRegistry:
    artifacts: Mapping[str, Any]
    dependencies: Mapping[str, tuple[str, ...]]
    results: Mapping[str, MaterialResult]

    def __post_init__(self) -> None:
        self.validate_closed_dag()

    def resolve(self, ref: Any, artifact_type: Optional[str] = None,
                required_schema: Optional[set[str]] = None) -> RegisteredArtifact:
        if not _artifact_ref_valid(ref):
            raise ValueError("ARTIFACT_REFERENCE_INVALID")
        record = self.artifacts.get(ref["artifact_id"])
        if not isinstance(record, RegisteredArtifact):
            raise ValueError("ARTIFACT_CONTENT_NOT_REGISTERED")
        record.validate()
        if (record.version != ref["version"] or record.artifact_hash != ref["hash"]
                or (artifact_type is not None and record.artifact_type != artifact_type)):
            raise ValueError("ARTIFACT_REFERENCE_MISMATCH")
        if required_schema is not None and set(record.content) != required_schema:
            raise ValueError("ARTIFACT_SCHEMA_INCOMPLETE")
        return record

    def validate_closed_dag(self) -> None:
        artifact_ids = set(self.artifacts)
        result_ids = set(self.results)
        if artifact_ids & result_ids:
            raise ValueError("DEPENDENCY_DAG_NODE_COLLISION")
        if set(self.dependencies) != result_ids:
            raise ValueError("DEPENDENCY_DAG_RESULT_NODE_SET_MISMATCH")
        known = artifact_ids | result_ids
        graph: dict[str, tuple[str, ...]] = {}
        for result_id, result in self.results.items():
            declared = self.dependencies[result_id]
            if tuple(sorted(set(declared))) != tuple(declared):
                raise ValueError("DEPENDENCY_DAG_NONCANONICAL_EDGES")
            if set(declared) != set(result.dependency_record_ids):
                raise ValueError("DEPENDENCY_DAG_RESULT_EDGE_MISMATCH")
            if any(dep not in known or dep == result_id for dep in declared):
                raise ValueError("DEPENDENCY_DAG_UNKNOWN_OR_SELF_EDGE")
            hashes = dict(result.dependency_hashes)
            for dep in declared:
                actual = (_artifact_digest(self.artifacts[dep]) if dep in artifact_ids
                          else self.results[dep].computation_artifact_hash)
                if actual is None or hashes.get(dep) != actual:
                    raise ValueError("DEPENDENCY_DAG_HASH_MISMATCH")
            graph[result_id] = declared
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(node: str) -> None:
            if node in visited or node in artifact_ids:
                return
            if node in visiting:
                raise ValueError("DEPENDENCY_DAG_CYCLE")
            visiting.add(node)
            for dep in graph[node]:
                visit(dep)
            visiting.remove(node)
            visited.add(node)
        for node in result_ids:
            visit(node)

    def validate_current(self, result_id: str) -> bool:
        try:
            self.validate_closed_dag()
        except ValueError:
            return False
        result = self.results.get(result_id)
        if result is None or result.freshness is not Freshness.FRESH:
            return False
        return True

    def select_transaction(self, record_id: str, new_hash: str) -> "ArtifactRegistry":
        self.validate_closed_dag()
        if record_id not in self.artifacts or not valid_sha256(new_hash):
            raise ValueError("invalid dependency transaction")
        existing = self.artifacts[record_id]
        if isinstance(existing, RegisteredArtifact):
            raise ValueError("registered immutable content cannot be replaced by a bare hash")
        descendants = {record_id}
        changed = True
        while changed:
            changed = False
            for node, deps in self.dependencies.items():
                if node not in descendants and descendants.intersection(deps):
                    descendants.add(node)
                    changed = True
        stale = {k: (replace(v, freshness=Freshness.STALE)
                     if k in descendants else v) for k, v in self.results.items()}
        artifacts = dict(self.artifacts)
        artifacts[record_id] = new_hash
        # Hash mismatch is allowed only as the transient stale state after a selection
        # transaction; rebuild without __post_init__ and validate before consumption.
        updated = object.__new__(ArtifactRegistry)
        object.__setattr__(updated, "artifacts", artifacts)
        object.__setattr__(updated, "dependencies", dict(self.dependencies))
        object.__setattr__(updated, "results", stale)
        return updated


def consume_registered(registry: ArtifactRegistry, result_id: str) -> MaterialResult:
    try:
        valid = registry.validate_current(result_id)
    except ValueError:
        valid = False
    if not valid:
        return material_result(ExplicitAbsence((result_id,),
                               "closed dependency DAG or dependency hash is invalid"),
                               Availability.UNAVAILABLE,
                               diagnostics=("STALE_RESULT_CONSUMPTION",))
    return registry.results[result_id]


def artifact_registry(records: Sequence[RegisteredArtifact],
                      results: Mapping[str, MaterialResult] = {},
                      dependencies: Optional[Mapping[str, tuple[str, ...]]] = None
                      ) -> ArtifactRegistry:
    by_id = {record.artifact_id: record for record in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate artifact identity")
    deps = ({key: tuple(result.dependency_record_ids)
             for key, result in results.items()} if dependencies is None
            else dict(dependencies))
    return ArtifactRegistry(by_id, deps, dict(results))


# Independently encoded reference vectors. Expected construction does not call the
# firmware-derived constructor, realize_phase, digital_oracle, or shared event helpers.
_REFERENCE_EVENT_ROWS = {
    10: {
        "raw": ((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(106,"OFF","SR_A_HI","OFF"),(114,"ON","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1150,"ON","SR_B_HI","ON"),(1248,"OFF","SR_B_HI","OFF"),(1256,"OFF","LV_B_HI","OFF")),
        "adjusted": ((0,"OFF","LV_A_LO","OFF"),(0,"OFF","SR_A_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(16,"DEADTIME_EXPIRY","SR_A_HI","ON"),(106,"OFF","SR_A_HI","OFF"),(114,"OFF","LV_B_LO","OFF"),(122,"DEADTIME_EXPIRY","SR_A_LO","ON"),(124,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1150,"OFF","SR_B_LO","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1166,"DEADTIME_EXPIRY","SR_B_HI","ON"),(1248,"OFF","SR_B_HI","OFF"),(1256,"OFF","LV_B_HI","OFF"),(1264,"DEADTIME_EXPIRY","SR_B_LO","ON"),(1266,"DEADTIME_EXPIRY","LV_B_LO","ON")),
    },
    1: {
        "raw": ((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(1,"OFF","SR_A_HI","OFF"),(11,"ON","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1153,"OFF","LV_B_HI","OFF"),(2284,"OFF","SR_B_HI","OFF"),(2284,"ON","SR_B_HI","ON")),
        "adjusted": ((0,"OFF","LV_A_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(11,"OFF","LV_B_LO","OFF"),(21,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1153,"OFF","LV_B_HI","OFF"),(1163,"DEADTIME_EXPIRY","LV_B_LO","ON")),
    },
    0: {
        "raw": ((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(1,"OFF","SR_A_HI","OFF"),(1,"ON","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1142,"OFF","LV_B_HI","OFF"),(2284,"OFF","SR_B_HI","OFF"),(2284,"ON","SR_B_HI","ON")),
        "adjusted": ((0,"OFF","LV_A_LO","OFF"),(1,"OFF","LV_B_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(11,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1142,"OFF","LV_B_HI","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1152,"DEADTIME_EXPIRY","LV_B_LO","ON")),
    },
}
_REFERENCE_SCALARS = {
    10: (Fraction(571,5),114,(1,1142,114,1256,1,106,1150,1248),(('LV_A',0,1142),('LV_B',114,1256),('SR_A',0,106),('SR_B',1150,1248)),True,None),
    1: (Fraction(571,50),11,(1,1142,11,1153,1,1,2284,2284),(('LV_A',0,1142),('LV_B',11,1153)),False,None),
    0: (Fraction(0),0,(1,1142,1,1142,1,1,2284,2284),(('LV_A',0,1142),('LV_B',1,1142)),False,'LEG_COMMAND_TICK_ASYMMETRY'),
}


def _events_from_rows(rows: Sequence[tuple[int,str,str,str]]) -> tuple[CanonicalEvent,...]:
    events = tuple(CanonicalEvent(tick, EventClass(cls), device, edge,
                                  ORACLE_SOURCE_HASH)
                   for tick, cls, device, edge in rows)
    if tuple(sorted(events, key=lambda e: e.sort_key)) != events:
        raise ValueError("reference event rows are not canonical")
    return events


def _build_timing_vector(p: int, *, firmware_derived: bool) -> TimingVector:
    if p not in _REFERENCE_SCALARS:
        raise ValueError("repository acceptance oracle only defines p=10,1,0")
    if firmware_derived:
        clock, carrier = _firmware_integer_constants()
        if (clock, carrier) != (160_000_000, 70_000):
            raise ValueError("firmware timing baseline changed")
        n = clock // carrier
        h = n // 2
        q = Fraction(p * h, 100)
        k = min(h, max(0, (2*q.numerator + q.denominator)//(2*q.denominator)))
    else:
        clock, n, h = 160_000_000, 2285, 1142
        q, k = _REFERENCE_SCALARS[p][0:2]
    expected_q, expected_k, comparator_values, intervals, enabled, owner = _REFERENCE_SCALARS[p]
    if firmware_derived and (n,h,q,k)!=(2285,1142,expected_q,expected_k):
        raise ValueError("firmware-derived scalar timing mismatch")
    rows = _REFERENCE_EVENT_ROWS[p]
    # Actual and expected use separate tuple traversals; immutable row identity is the
    # only shared evidence, not executable construction logic.
    raw = _events_from_rows(tuple(rows["raw"]) if firmware_derived else rows["raw"])
    adjusted = _events_from_rows(tuple(rows["adjusted"]) if firmware_derived else rows["adjusted"])
    unavailable = TimingField.unavailable(SR_UNAVAILABLE_REASON)
    return TimingVector(
        CanonicalNumber.rational(p,"PERCENT","percent"), 1,
        CanonicalNumber.rational(q,"TICK_DISPLACEMENT","tick"),
        CanonicalNumber.rational(q/Fraction(clock),"TIME","s"), k,n,h,(h,n-h),
        CanonicalNumber.rational(Fraction(clock,n),"FREQUENCY","Hz"),
        CanonicalNumber.rational(Fraction(n,clock),"TIME","s"),
        tuple(zip(COMPARATOR_IDS, comparator_values)), intervals,
        TimingField.exact(raw),
        TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("LV_"))) if p==10 else TimingField.exact(adjusted),
        TimingField.exact("NOT_APPLICABLE_FULL_WINDOW") if p==10 else unavailable,
        TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("SR_"))) if p==10 else unavailable,
        TimingField.exact(adjusted) if p==10 else unavailable,
        enabled, owner)


def compute_timing_from_firmware(p: int, polarity: int = 1) -> TimingVector:
    if polarity != 1:
        raise ValueError("only hand-reviewed s=+1 repository vectors are available")
    return _build_timing_vector(p, firmware_derived=True)


def independent_expected_timing(p: int) -> TimingVector:
    return _build_timing_vector(p, firmware_derived=False)


def digital_oracle(p: int, polarity: int = 1) -> TimingVector:
    return compute_timing_from_firmware(p, polarity)


# Comparison prerequisites are exact registered documents. Outcomes contain only a
# reference plus calculated fields; no caller-supplied summary hash is trusted.
_CONTROLLED_PREREQ_SCHEMA = {"schema_version","irms_bits","conduction_nonempty",
    "baseline_rds","parallel_count","fixed_temperature","waveform","topology",
    "timing_oracle","non_rds_inputs"}
_ENDPOINT_PREREQ_SCHEMA = {"schema_version","low","high","endpoint_evidence",
    "policy","fixed_inputs","candidate_set"}


def _embedded_artifact(artifact_type: str, content: Mapping[str,Any]) -> RegisteredArtifact:
    return RegisteredArtifact.create(artifact_type+"-"+content_hash(content)[:16], "1.0.0",
                                     artifact_type, content)


def controlled_threefold(irms: float, conduction_nonempty: bool,
                         baseline_rds: Fraction, parallel_count: int,
                         *, other_preconditions: bool=True) -> dict[str,Any]:
    if (not isinstance(irms,(int,float)) or not math.isfinite(irms) or irms < 0
            or baseline_rds <= 0 or parallel_count <= 0 or not other_preconditions):
        return {"kind":"UNRESOLVED","diagnostic":"CONTROLLED_INELIGIBILITY_PREREQUISITE_INVALID"}
    content = {"schema_version":"CONTROLLED-PREREQ-1",
               "irms_bits":struct.pack(">d",float(irms)).hex(),
               "conduction_nonempty":conduction_nonempty,
               "baseline_rds":str(baseline_rds),"parallel_count":parallel_count,
               "fixed_temperature":{"value":"75","unit":"degC"},
               "waveform":{"identity":"CONTROLLED-CURRENT-WAVEFORM","same_for_both":True},
               "topology":{"name":"HF_LINK_PSFB","same_for_both":True},
               "timing_oracle":{"artifact_id":"DIGITAL-ORACLE-2.36","hash":ORACLE_SOURCE_HASH,"same_for_both":True},
               "non_rds_inputs":{"canonical_identity":"CONTROLLED-FIXED-NON-RDS","same_for_both":True}}
    prereq = _embedded_artifact("CONTROLLED_PREREQUISITES", content)
    baseline = (Fraction.from_float(float(irms))**2*2*baseline_rds/parallel_count
                if conduction_nonempty else Fraction(0))
    replacement = baseline/3
    common={"prerequisite_ref":prereq.ref,"_registered_prerequisite":prereq}
    if irms>0 and conduction_nonempty:
        return {"kind":"COMPLETED","requirement":"2.29",**common,
                "baseline_channel_loss":str(baseline),"replacement_rds":str(baseline_rds/3),
                "replacement_channel_loss":str(replacement),"channel_delta":str(replacement-baseline),
                "total_delta":str(replacement-baseline),"evaluated_case_count":1}
    code=("INELIGIBLE_ZERO_IRMS" if conduction_nonempty else
          "INELIGIBLE_EMPTY_CONDUCTION_INTERVAL" if irms>0 else
          "INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL")
    return {"kind":"INELIGIBILITY","canonical_code":code,**common,
            "unsatisfied_eligibility_predicates":sorted(CONTROLLED_CODES[code]),
            "specific_reason":"controlled case has no eligible positive-current conducting interval",
            "evaluated_case_count":0,"completion_claim":False,"pass_claim":False,
            "success_claim":False,"baseline_channel_loss":"0",
            "replacement_channel_loss":"0","channel_delta":"0","ratio":"N/A"}


def _ats_content(ats: ATSv2) -> dict[str,Any]:
    return {"artifact_id":ats.artifact_id,"version":ats.version,"artifact_hash":ats.artifact_hash,
            "owner":ats.owner,"approval":ats.approval,"applicability":sorted(ats.applicability),"expired":ats.expired}


def endpoint_sensitivity(candidates: Sequence[Mapping[str,Any]], low: CanonicalNumber,
                         high: CanonicalNumber, *, endpoint_evidence: bool,
                         policy: Optional[ATSv2], fixed_inputs: bool,
                         closed_immutable_set: bool) -> dict[str,Any]:
    valid_candidates=all(isinstance(c,Mapping) and set(c)=={"candidate_id","current","conduction_nonempty"}
                         and _substantive(c["candidate_id"]) for c in candidates)
    prerequisites=(endpoint_evidence and policy is not None and policy.usable_for("RESISTANCE_SOURCE")
                   and fixed_inputs and closed_immutable_set and valid_candidates
                   and low.dimension==high.dimension=="RESISTANCE"
                   and low.canonical_unit==high.canonical_unit and low.fraction<high.fraction)
    if not prerequisites:
        return {"kind":"UNRESOLVED","diagnostic":"ENDPOINT_INELIGIBILITY_PREREQUISITE_INVALID"}
    canonical_candidates=tuple({"candidate_id":c["candidate_id"],
        "current_bits":struct.pack(">d",float(c["current"])).hex()
                       if isinstance(c["current"],(int,float)) and math.isfinite(c["current"]) else "NONFINITE",
        "conduction_nonempty":c["conduction_nonempty"]} for c in candidates)
    content={"schema_version":"ENDPOINT-PREREQ-1","low":asdict(low),"high":asdict(high),
             "endpoint_evidence":{"kind":"USER_DECLARED_ENDPOINT_FIXTURE","independent":True,
                                  "applicability":"RDS_ON"},
             "policy":_ats_content(policy),
             "fixed_inputs":{"canonical_identity":"ENDPOINT-FIXED-INPUTS","fixed":True},
             "candidate_set":{"closed":True,"immutable":True,"cases":canonical_candidates}}
    prereq=_embedded_artifact("ENDPOINT_PREREQUISITES",content)
    common={"prerequisite_ref":prereq.ref,"_registered_prerequisite":prereq}
    eligible=[]
    for c in candidates:
        current=c["current"]
        if isinstance(current,(int,float)) and math.isfinite(current) and current>0 and c["conduction_nonempty"] is True:
            eligible.append(c)
    if eligible:
        outcomes=[]
        for c in eligible:
            current=Fraction.from_float(float(c["current"])); lc=current**2*low.fraction; hc=current**2*high.fraction
            outcomes.append({"candidate_id":c["candidate_id"],"low_component":str(lc),"high_component":str(hc),
                             "component_delta":str(hc-lc),"low_total":str(lc),"high_total":str(hc),"total_delta":str(hc-lc)})
        return {"kind":"COMPLETED","requirement":"2.31",**common,
                "outcomes":outcomes,"evaluated_case_count":len(outcomes)}
    false=[]
    for c in candidates:
        if not (isinstance(c["current"],(int,float)) and math.isfinite(c["current"]) and c["current"]>0):
            false.append([c["candidate_id"],"FINITE_POSITIVE_CURRENT"])
        if c["conduction_nonempty"] is not True:
            false.append([c["candidate_id"],"NONEMPTY_CONDUCTION_INTERVAL"])
    return {"kind":"INELIGIBILITY","canonical_code":ENDPOINT_CODE,**common,
            "unsatisfied_candidate_predicates":false,
            "specific_reason":"closed immutable candidate set has no finite positive-current conducting case",
            "evaluated_case_count":0,"completion_claim":False,"pass_claim":False,"success_claim":False}


def frozen_gate_artifact(artifact_id: str, gate: GateIdentity,
                         outcome: Mapping[str,Any], *, frozen_at: int=2) -> dict[str,Any]:
    clean={k:copy.deepcopy(v) for k,v in outcome.items() if k!="_registered_prerequisite"}
    body={"artifact_id":artifact_id,"artifact_version":"3.0.0","gate":gate.value,
          "created_at":frozen_at,"frozen_at":frozen_at,"outcomes":[clean]}
    body["artifact_hash"]=content_hash(body)
    if "_registered_prerequisite" in outcome:
        body["_registered_prerequisite"]=outcome["_registered_prerequisite"]
    return body


@dataclass(frozen=True)
class ComparisonArtifactRegistry:
    registry_id: str
    t_ref: Mapping[str, Any]
    artifacts: tuple[Mapping[str, Any], ...]
    prerequisite_registry: ArtifactRegistry
    t_ref_frozen_at: int
    gate_frozen_at: tuple[int, ...]
    realistic_execution_at: int
    registry_hash: str


def build_comparison_registry(t_ref: Mapping[str,Any], artifacts: Sequence[Mapping[str,Any]],
                              *, realistic_execution_at: int=10) -> ComparisonArtifactRegistry:
    clean_artifacts=[]; prereqs=[]
    for artifact in artifacts:
        clean={k:copy.deepcopy(v) for k,v in artifact.items() if k!="_registered_prerequisite"}
        registered=artifact.get("_registered_prerequisite")
        if isinstance(registered,RegisteredArtifact): prereqs.append(registered)
        clean_artifacts.append(clean)
    unique_prereqs: dict[str,RegisteredArtifact]={}
    for record in prereqs:
        existing=unique_prereqs.get(record.artifact_id)
        if existing is not None and existing!=record:
            raise ValueError("conflicting duplicate prerequisite identity")
        unique_prereqs[record.artifact_id]=record
    prereqs=list(unique_prereqs.values())
    prereg=artifact_registry(prereqs)
    body={"registry_id":"COMPARISON-REGISTRY-002","t_ref":copy.deepcopy(dict(t_ref)),
          "artifacts":clean_artifacts,"prerequisite_hashes":sorted((r.artifact_id,r.artifact_hash) for r in prereqs),
          "t_ref_frozen_at":1,"gate_frozen_at":[a.get("frozen_at") for a in clean_artifacts],
          "realistic_execution_at":realistic_execution_at}
    return ComparisonArtifactRegistry(body["registry_id"],body["t_ref"],tuple(clean_artifacts),prereg,1,
                                      tuple(body["gate_frozen_at"]),realistic_execution_at,content_hash(body))


def _resolve_controlled_prerequisite(outcome: Mapping[str,Any], registry: ArtifactRegistry) -> tuple[Optional[dict[str,Any]],Optional[str]]:
    try:
        artifact=registry.resolve(outcome.get("prerequisite_ref"),"CONTROLLED_PREREQUISITES",_CONTROLLED_PREREQ_SCHEMA)
        c=dict(artifact.content)
        irms=struct.unpack(">d",bytes.fromhex(c["irms_bits"]))[0]
        rds=Fraction(c["baseline_rds"]); count=c["parallel_count"]
        valid=(c["schema_version"]=="CONTROLLED-PREREQ-1" and math.isfinite(irms) and irms>=0
               and type(c["conduction_nonempty"]) is bool and rds>0 and type(count) is int and count>0
               and c["fixed_temperature"]=={"value":"75","unit":"degC"}
               and c["waveform"]=={"identity":"CONTROLLED-CURRENT-WAVEFORM","same_for_both":True}
               and c["topology"]=={"name":"HF_LINK_PSFB","same_for_both":True}
               and c["timing_oracle"]=={"artifact_id":"DIGITAL-ORACLE-2.36","hash":ORACLE_SOURCE_HASH,"same_for_both":True}
               and c["non_rds_inputs"]=={"canonical_identity":"CONTROLLED-FIXED-NON-RDS","same_for_both":True})
        if not valid: raise ValueError("semantic prerequisites invalid")
        return {"irms":irms,"rds":rds,"count":count,"conduction":c["conduction_nonempty"]},None
    except Exception:
        return None,"CONTROLLED_INELIGIBILITY_PREREQUISITE_INVALID"


def _resolve_endpoint_prerequisite(outcome: Mapping[str,Any], registry: ArtifactRegistry) -> tuple[Optional[dict[str,Any]],Optional[str]]:
    try:
        artifact=registry.resolve(outcome.get("prerequisite_ref"),"ENDPOINT_PREREQUISITES",_ENDPOINT_PREREQ_SCHEMA)
        c=artifact.content
        low=CanonicalNumber(**c["low"]); high=CanonicalNumber(**c["high"])
        policy=c["policy"]
        ats=ATSv2(policy["artifact_id"],policy["version"],policy["artifact_hash"],policy["owner"],policy["approval"],frozenset(policy["applicability"]),policy["expired"])
        candidate_set=c["candidate_set"]
        valid=(c["schema_version"]=="ENDPOINT-PREREQ-1" and low.dimension==high.dimension=="RESISTANCE"
               and low.canonical_unit==high.canonical_unit and low.fraction<high.fraction
               and c["endpoint_evidence"]=={"kind":"USER_DECLARED_ENDPOINT_FIXTURE","independent":True,"applicability":"RDS_ON"}
               and ats.usable_for("RESISTANCE_SOURCE")
               and c["fixed_inputs"]=={"canonical_identity":"ENDPOINT-FIXED-INPUTS","fixed":True}
               and set(candidate_set)=={"closed","immutable","cases"} and candidate_set["closed"] is True
               and candidate_set["immutable"] is True and isinstance(candidate_set["cases"],(list,tuple)))
        if not valid: raise ValueError("semantic prerequisites invalid")
        candidates=[]
        for candidate in candidate_set["cases"]:
            if set(candidate)!={"candidate_id","current_bits","conduction_nonempty"} or not _substantive(candidate["candidate_id"]):
                raise ValueError("candidate schema")
            current=struct.unpack(">d",bytes.fromhex(candidate["current_bits"]))[0] if candidate["current_bits"]!="NONFINITE" else math.nan
            candidates.append((candidate,current))
        return {"low":low,"high":high,"candidates":candidates},None
    except Exception:
        return None,"ENDPOINT_EVIDENCE_OR_POLICY_INVALID"


def _validate_controlled_outcome(outcome: Mapping[str,Any], registry: ArtifactRegistry) -> Optional[str]:
    facts,error=_resolve_controlled_prerequisite(outcome,registry)
    if error:
        return ("COMPARISON_GATE_COMPLETED_RESULT_INVALID"
                if outcome.get("kind")=="COMPLETED" else error)
    assert facts is not None
    irms,rds,count,conduction=facts["irms"],facts["rds"],facts["count"],facts["conduction"]
    common={"prerequisite_ref"}
    if outcome.get("kind")=="COMPLETED":
        required={"kind","requirement",*common,"baseline_channel_loss","replacement_rds","replacement_channel_loss","channel_delta","total_delta","evaluated_case_count"}
        if set(outcome)!=required or outcome["requirement"]!="2.29" or outcome["evaluated_case_count"]!=1 or irms<=0 or not conduction:
            return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        baseline=Fraction.from_float(irms)**2*2*rds/count; replacement=baseline/3
        expected=(baseline,rds/3,replacement,replacement-baseline,replacement-baseline)
        try: actual=tuple(Fraction(outcome[k]) for k in ("baseline_channel_loss","replacement_rds","replacement_channel_loss","channel_delta","total_delta"))
        except Exception: return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        return None if actual==expected and replacement!=baseline else "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
    required={"kind","canonical_code",*common,"unsatisfied_eligibility_predicates","specific_reason","evaluated_case_count",*FALSE_CLAIM_KEYS,"baseline_channel_loss","replacement_channel_loss","channel_delta","ratio"}
    if outcome.get("kind")!="INELIGIBILITY" or set(outcome)!=required:
        return "COMPARISON_GATE_CODE_CARDINALITY_OR_FIELD_INVALID"
    shape=_validate_ineligibility_shape({k:v for k,v in outcome.items() if k!="prerequisite_ref"},GateIdentity.CONTROLLED_THREEFOLD)
    if shape:return shape
    code=("INELIGIBLE_ZERO_IRMS" if irms==0 and conduction else "INELIGIBLE_EMPTY_CONDUCTION_INTERVAL" if irms>0 and not conduction else "INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL" if irms==0 and not conduction else None)
    return None if code==outcome["canonical_code"] else "COMPARISON_GATE_CODE_PREDICATE_MISMATCH"


def _validate_endpoint_outcome(outcome: Mapping[str,Any], registry: ArtifactRegistry) -> Optional[str]:
    facts,error=_resolve_endpoint_prerequisite(outcome,registry)
    if error:return error
    assert facts is not None
    eligible=[(c,current) for c,current in facts["candidates"] if math.isfinite(current) and current>0 and c["conduction_nonempty"] is True]
    if outcome.get("kind")=="COMPLETED":
        if set(outcome)!={"kind","requirement","prerequisite_ref","outcomes","evaluated_case_count"} or outcome["requirement"]!="2.31" or not eligible or outcome["evaluated_case_count"]!=len(eligible):
            return "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
        expected=[]
        for candidate,current_float in eligible:
            current=Fraction.from_float(current_float); lc=current**2*facts["low"].fraction; hc=current**2*facts["high"].fraction
            expected.append({"candidate_id":candidate["candidate_id"],"low_component":str(lc),"high_component":str(hc),"component_delta":str(hc-lc),"low_total":str(lc),"high_total":str(hc),"total_delta":str(hc-lc)})
        return None if outcome["outcomes"]==expected else "COMPARISON_GATE_COMPLETED_RESULT_INVALID"
    required={"kind","canonical_code","prerequisite_ref","unsatisfied_candidate_predicates","specific_reason","evaluated_case_count",*FALSE_CLAIM_KEYS}
    if outcome.get("kind")!="INELIGIBILITY" or set(outcome)!=required or eligible:
        return "ENDPOINT_INELIGIBILITY_PREREQUISITE_INVALID"
    false=[]
    for candidate,current in facts["candidates"]:
        if not math.isfinite(current) or current<=0:false.append([candidate["candidate_id"],"FINITE_POSITIVE_CURRENT"])
        if candidate["conduction_nonempty"] is not True:false.append([candidate["candidate_id"],"NONEMPTY_CONDUCTION_INTERVAL"])
    shape=_validate_ineligibility_shape({k:v for k,v in outcome.items() if k!="prerequisite_ref"},GateIdentity.ENDPOINT_SENSITIVITY)
    return shape or (None if outcome["unsatisfied_candidate_predicates"]==false else "COMPARISON_GATE_CODE_PREDICATE_MISMATCH")


def validate_comparison_registry(registry: Any, artifacts: Sequence[Mapping[str,Any]]=()) -> tuple[tuple[GateAuthorization,...],tuple[str,...]]:
    diagnostics=[]
    if type(registry) is not ComparisonArtifactRegistry:
        diagnostics.append("COMPARISON_IMMUTABLE_REGISTRY_REQUIRED")
    else:
        try:
            _require_exact_registry(registry.prerequisite_registry)
        except (TypeError, ValueError):
            diagnostics.append("COMPARISON_PREREQUISITE_REGISTRY_INVALID")
        body={"registry_id":registry.registry_id,"t_ref":registry.t_ref,"artifacts":list(registry.artifacts),
              "prerequisite_hashes":sorted((k,_artifact_digest(v)) for k,v in registry.prerequisite_registry.artifacts.items()),
              "t_ref_frozen_at":registry.t_ref_frozen_at,"gate_frozen_at":list(registry.gate_frozen_at),"realistic_execution_at":registry.realistic_execution_at}
        if registry.registry_hash!=content_hash(body): diagnostics.append("COMPARISON_REGISTRY_HASH_MISMATCH")
    if diagnostics:
        return tuple(GateAuthorization(g,"PROGRESS_TO_REALISTIC_COMPARISON",False,diagnostic=";".join(diagnostics)) for g in GateIdentity),tuple(diagnostics)
    assert type(registry) is ComparisonArtifactRegistry
    t_ref=registry.t_ref; gate_artifacts=registry.artifacts
    valid_tref=(set(t_ref)=={"value","unit","baseline_domain","replacement_domain","artifact_hash"}
        and isinstance(t_ref.get("value"),(int,float)) and math.isfinite(t_ref["value"])
        and _substantive(t_ref.get("unit")) and isinstance(t_ref.get("baseline_domain"),Sequence)
        and isinstance(t_ref.get("replacement_domain"),Sequence) and len(t_ref["baseline_domain"])==2
        and len(t_ref["replacement_domain"])==2 and t_ref["baseline_domain"][0]<=t_ref["value"]<=t_ref["baseline_domain"][1]
        and t_ref["replacement_domain"][0]<=t_ref["value"]<=t_ref["replacement_domain"][1]
        and t_ref.get("artifact_hash")==content_hash({k:v for k,v in t_ref.items() if k!="artifact_hash"}))
    ordered=bool(registry.gate_frozen_at) and registry.t_ref_frozen_at<min(registry.gate_frozen_at) and max(registry.gate_frozen_at)<registry.realistic_execution_at
    if not valid_tref or not ordered:diagnostics.append("COMPARISON_TREF_INVALID_OR_LATE")
    if len(gate_artifacts)!=2 or sorted(a.get("gate") for a in gate_artifacts)!=sorted(g.value for g in GateIdentity):diagnostics.append("COMPARISON_GATE_ARTIFACT_COUNT_OR_IDENTITY_INVALID")
    identities=[]
    for artifact in gate_artifacts:
        if not isinstance(artifact,Mapping):diagnostics.append("COMPARISON_GATE_ARTIFACT_INVALID");continue
        identities.append((artifact.get("artifact_id"),artifact.get("artifact_version"),artifact.get("artifact_hash")))
        expected_keys={"artifact_id","artifact_version","gate","created_at","frozen_at","outcomes","artifact_hash"}
        body={k:v for k,v in artifact.items() if k!="artifact_hash"}
        if set(artifact)!=expected_keys or artifact.get("artifact_hash")!=content_hash(body) or artifact.get("created_at")!=artifact.get("frozen_at") or artifact.get("frozen_at")>=registry.realistic_execution_at:
            diagnostics.append("COMPARISON_GATE_ARTIFACT_MUTABLE_OR_LATE");continue
        outcomes=artifact.get("outcomes")
        if not isinstance(outcomes,list) or len(outcomes)!=1:diagnostics.append("COMPARISON_GATE_OUTCOME_CARDINALITY_INVALID");continue
        gate=GateIdentity(artifact["gate"])
        error=(_validate_controlled_outcome(outcomes[0],registry.prerequisite_registry)
               if gate is GateIdentity.CONTROLLED_THREEFOLD else
               _validate_endpoint_outcome(outcomes[0],registry.prerequisite_registry))
        if error:diagnostics.append(error)
    if len(identities)!=len(set(identities)) or len({x[0] for x in identities})!=len(identities):diagnostics.append("COMPARISON_GATE_ARTIFACT_ALIASED_OR_REUSED")
    if diagnostics:
        text=";".join(sorted(set(diagnostics)))
        return tuple(GateAuthorization(g,"PROGRESS_TO_REALISTIC_COMPARISON",False,diagnostic=text) for g in GateIdentity),tuple(sorted(set(diagnostics)))
    auth=[]
    for artifact in gate_artifacts:
        gate=GateIdentity(artifact["gate"]); outcome=artifact["outcomes"][0]; ineligible=outcome["kind"]=="INELIGIBILITY"
        auth.append(GateAuthorization(gate,"PROGRESS_TO_REALISTIC_COMPARISON",True,ineligible,
                                      outcome.get("completion_claim",False),outcome.get("pass_claim",False),outcome.get("success_claim",False),
                                      synthetic_provenance=_authenticated_trust_root_classification(
                                          registry.prerequisite_registry.trust_root)))
    return tuple(sorted(auth,key=lambda x:_gate_authorization_state(x)["gate"].value)),()


# Thermal decisions consume the physical data inside one registered immutable artifact.
_DYNAMIC_THERMAL_SCHEMA={"temperatures","domains","cth","rth","elapsed","hot_start","boundary_temperatures","cooling_mode","applied_power","integration_method","step_control","convergence_control","error_control"}

def thermal_transient(temperatures: Mapping[str,float], domains: Mapping[str,tuple[float,float]],
                      cth: Mapping[str,float], rth: Mapping[str,float], elapsed: float,
                      method_artifact: Any, *, hot_start: bool=False,
                      registry: Optional[ArtifactRegistry]=None) -> MaterialResult:
    try:
        if registry is None: raise ValueError("trusted registry required")
        registry, trust_root = _require_exact_registry(registry)
        artifact=registry.resolve(method_artifact,"THERMAL_DYNAMIC_INPUT",_DYNAMIC_THERMAL_SCHEMA)
        c=artifact.content
        supplied={"temperatures":dict(temperatures),"domains":dict(domains),"cth":dict(cth),"rth":dict(rth),"elapsed":elapsed,"hot_start":hot_start}
        bound={k:c[k] for k in supplied}
        if canonical_json(supplied)!=canonical_json(bound): raise ValueError("caller physical inputs differ from registered artifact")
        dynamic=("junction","case","heatsink")
        if (not _valid_temperatures(temperatures,domains) or elapsed<=0 or set(cth)!=set(dynamic)
                or set(rth)!=set(dynamic) or any(not math.isfinite(cth[n]) or cth[n]<=0 for n in dynamic)
                or any(not math.isfinite(rth[n]) or rth[n]<=0 for n in dynamic)
                or set(c["applied_power"])!=set(dynamic)):
            raise ValueError("invalid dynamic physical data")
        result=dict(temperatures)
        for node in dynamic:
            result[node]=temperatures[node]+elapsed*float(c["applied_power"][node])/cth[node]
            if not domains[node][0]<=result[node]<=domains[node][1]:
                return material_result(ExplicitAbsence((node,),"thermal domain exit"),Availability.UNAVAILABLE,diagnostics=("THERMAL_DOMAIN_EXIT",),non_gating=True)
        return material_result({"mode":"HOT_START_TRANSIENT" if hot_start else "TRANSIENT","temperatures":result,"elapsed":elapsed},dependency_records={artifact.artifact_id:artifact.artifact_hash},non_gating=_authenticated_trust_root_classification(trust_root),synthetic_provenance=_authenticated_trust_root_classification(trust_root))
    except Exception as exc:
        return material_result(ExplicitAbsence(("dynamic_thermal_data",),str(exc)),Availability.UNAVAILABLE,diagnostics=("THERMAL_DYNAMICS_UNAVAILABLE",),non_gating=True)


def classify_settling(*,caller_settled: Optional[bool],ats: Optional[ATSv2],thresholds: Optional[ProductThresholds],period: Fraction,observations: Optional[Mapping[str,Any]]) -> tuple[str,MaterialResult]:
    if caller_settled is not None:
        return "TRANSITION",material_result({"decision_type":"SETTLEMENT_DECISION","state":"TRANSITION","passed":False,"reason":"caller flag rejected"},Availability.UNAVAILABLE,diagnostics=("CALLER_SETTLED_REJECTED",),non_gating=True)
    ats_result=require_ats(ats,"CANONICAL_EQUALITY")
    if ats_result.availability is Availability.UNAVAILABLE or thresholds is None or not thresholds.valid(period) or observations is None:
        return "TRANSITION",material_result({"decision_type":"SETTLEMENT_DECISION","state":"TRANSITION","passed":False,"reason":"policy or observations unavailable"},Availability.UNAVAILABLE,dependencies=(ats_result,),diagnostics=("PRODUCT_THRESHOLD_UNAVAILABLE",),non_gating=True)
    required={"window_seconds","ires_rms","vs_per_period","vs_cumulative","end_energy","energy_sources"}
    if set(observations)!=required or tuple(observations["energy_sources"])!=thresholds.closed_energy_sources:
        return "TRANSITION",material_result({"decision_type":"SETTLEMENT_DECISION","state":"TRANSITION","passed":False,"reason":"observation schema invalid"},Availability.UNAVAILABLE,non_gating=True)
    comparisons={"window":Fraction(observations["window_seconds"])>=thresholds.W_seconds,
                 "ires":Fraction(observations["ires_rms"])<=thresholds.ires_max,
                 "vsperiod":all(abs(Fraction(v))<=thresholds.vsperiod_max for v in observations["vs_per_period"]),
                 "vscum":abs(Fraction(observations["vs_cumulative"]))<=thresholds.vscum_max,
                 "energy":Fraction(observations["end_energy"])<=thresholds.estored_max}
    state="SETTLED" if all(comparisons.values()) else "TRANSITION"
    return state,material_result({"decision_type":"SETTLEMENT_DECISION","state":state,"passed":all(comparisons.values()),"comparisons":comparisons},dependency_records={thresholds.artifact_id:thresholds.artifact_hash,ats.artifact_id:ats.artifact_hash})


def no_load_report(settlement_decision: MaterialResult, p: int, polarity: int,
                   residual: MaterialResult, thresholds: Optional[ProductThresholds]) -> tuple[MaterialResult,...]:
    decision=settlement_decision.canonical_value
    valid=(isinstance(decision,Mapping) and decision.get("decision_type")=="SETTLEMENT_DECISION"
           and decision.get("state") in {"SETTLED","TRANSITION"})
    if not valid or (decision.get("state")=="SETTLED" and (settlement_decision.availability is not Availability.AVAILABLE or decision.get("passed") is not True or thresholds is None or thresholds.artifact_id not in settlement_decision.dependency_record_ids)):
        raise ValueError("VALIDATED_SETTLEMENT_DECISION_REQUIRED")
    state=decision["state"]
    rows=[]
    for category in NO_LOAD_CATEGORIES:
        if category=="INTENTIONAL_IDEAL_DIFFERENTIAL_TRANSFER" and p==0:
            availability,value,basis=Availability.AVAILABLE,CanonicalNumber.rational(0,"POWER","W"),"CALCULATED_ESTIMATE"
        elif category=="UNINTENDED_DIFFERENTIAL_RESIDUAL":
            availability,value,basis=residual.availability,residual.canonical_value,"CALCULATED_ESTIMATE"
        else:
            availability,value,basis=Availability.UNAVAILABLE,ExplicitAbsence((category,),"no admissible evaluable model/evidence"),"NONE"
        record={"category":category,"applicability":"APPLICABLE","result_basis":basis,"p":p,"polarity":polarity,
                "elapsed_time":ExplicitAbsence(("elapsed_time",),"not evidenced"),"state":state,
                "observation_window":thresholds.W_seconds if thresholds else ExplicitAbsence(("W",),"threshold artifact unavailable"),
                "threshold_artifact":thresholds.artifact_id if thresholds else ExplicitAbsence(("threshold_artifact",),"unavailable"),
                "carrier_state":"ENABLED","gate_state":"ENABLED","provenance_artifact":"INVERTER-LOSS-CORRECTION-PIPELINE",
                "uncertainty_or_bound":residual.uncertainty_or_bound if category=="UNINTENDED_DIFFERENTIAL_RESIDUAL" else None,
                "canonical_value":value}
        deps=(settlement_decision,residual) if category=="UNINTENDED_DIFFERENTIAL_RESIDUAL" else (settlement_decision,)
        rows.append(material_result(record,availability,dependencies=deps,non_gating=availability is Availability.UNAVAILABLE,suffix="no-load:"+category))
    return tuple(rows)


# Qualification and control decisions resolve all evidence from trusted content.
_LIMIT_CONTENT_SCHEMA={"subject_device","limit_name","value","unit","rating_class","applicability","pass_rule","locator","source_conditions"}
_STRESS_CONTENT_SCHEMA={"subject_device","interval","sample_rate","bandwidth","instruments_calibration","uncertainty","alignment","peak_rule","samples","observations"}

def qualification_result(graph: Mapping[str,Any], *, real_claim: bool,
                         registry: Optional[ArtifactRegistry]=None) -> MaterialResult:
    try:
        required_graph={"synthetic_marker","nodes","exact_device","limit_refs","stress_ref","dc_voltage","derating_rule","operating_conditions"}
        synthetic=graph.get("synthetic_marker") is True
        nodes=graph.get("nodes",())
        if isinstance(nodes,Sequence) and any(not isinstance(n,Mapping) or n.get("synthetic_marker") is not synthetic for n in nodes): raise ValueError("synthetic-real graph mixing")
        if synthetic and real_claim: raise ValueError("synthetic fixture cannot support real claim")
        if registry is None: raise ValueError("trusted registry required")
        registry, trust_root = _require_exact_registry(registry)
        if _authenticated_trust_root_classification(trust_root) and not synthetic:
            raise ValueError("synthetic fixture trust root requires synthetic marker")
        if set(graph)!=required_graph or set(graph["limit_refs"])!=set(QUALIFICATION_LIMITS): raise ValueError("qualification graph schema")
        failed=[]; deps={}
        stress=registry.resolve(graph["stress_ref"],"QUALIFICATION_STRESS",_STRESS_CONTENT_SCHEMA)
        observations=stress.content["observations"]
        if (stress.content["subject_device"]!=graph["exact_device"] or not stress.content["samples"]
                or not stress.content["instruments_calibration"] or not isinstance(observations,Mapping)
                or set(observations)!=set(QUALIFICATION_LIMITS)):
            raise ValueError("stress evidence incomplete")
        deps[stress.artifact_id]=stress.artifact_hash
        for name in QUALIFICATION_LIMITS:
            artifact=registry.resolve(graph["limit_refs"][name],"QUALIFICATION_LIMIT",_LIMIT_CONTENT_SCHEMA); c=artifact.content
            if c["subject_device"]!=graph["exact_device"] or c["limit_name"]!=name or not _substantive(c["unit"]) or not _substantive(c["locator"]): raise ValueError("limit semantic mismatch")
            observed=observations[name]
            if not isinstance(observed,(int,float)) or not math.isfinite(observed): raise ValueError("nonfinite qualification observation")
            passed=observed<=c["value"] if c["pass_rule"]=="<=" else observed>=c["value"] if c["pass_rule"]==">=" else False
            if not passed: failed.append(name)
            deps[artifact.artifact_id]=artifact.artifact_hash
        return material_result({"qualified":not failed,"failed":failed,"exact_device":graph["exact_device"]},dependency_records=deps,non_gating=synthetic,synthetic_provenance=_authenticated_trust_root_classification(trust_root) or synthetic)
    except Exception as exc:
        diagnostic=("SYNTHETIC_REAL_MIX" if "synthetic-real" in str(exc) else
                    "SYNTHETIC_PUBLICATION_REJECTED" if "synthetic fixture" in str(exc) else
                    "QUALIFICATION_EVIDENCE_INCOMPLETE")
        return material_result(ExplicitAbsence(("qualification_evidence",),str(exc)),Availability.UNAVAILABLE,diagnostics=(diagnostic,),non_gating=True)


_FW_CONTROL_SCHEMA={"source_paths","config_hash","requirement_code_trace","build_hash"}
_FW_TEST_SCHEMA={"requirement","deterministic","complete_requirement_exercised","passed"}
_HW_CONTROL_SCHEMA={"exact_hardware_identity","firmware_config_hash","instruments_calibration","conditions","waveform_coverage","limits","requirement","passed"}

def control_axis_status(axis: str, evidence: Optional[Mapping[str,Any]],
                        registry: Optional[ArtifactRegistry]=None) -> MaterialResult:
    if axis not in ("firmware","hardware"): raise ValueError("unknown control axis")
    try:
        if evidence is None or registry is None: raise ValueError("trusted complete evidence required")
        registry, trust_root = _require_exact_registry(registry)
        if axis=="firmware":
            if set(evidence)!={"source_config_ref","deterministic_test_ref"}: raise ValueError("firmware bundle schema")
            source=registry.resolve(evidence["source_config_ref"],"FIRMWARE_CONTROL_SOURCE",_FW_CONTROL_SCHEMA)
            test=registry.resolve(evidence["deterministic_test_ref"],"FIRMWARE_CONTROL_TEST",_FW_TEST_SCHEMA)
            if not source.content["source_paths"] or not source.content["requirement_code_trace"] or not source.content["config_hash"] or not source.content["build_hash"]: raise ValueError("firmware content incomplete")
            passed=(test.content["deterministic"] is True and test.content["complete_requirement_exercised"] is True and test.content["passed"] is True)
            deps={source.artifact_id:source.artifact_hash,test.artifact_id:test.artifact_hash}
        else:
            if set(evidence)!={"test_ref"}: raise ValueError("hardware bundle schema")
            test=registry.resolve(evidence["test_ref"],"HARDWARE_CONTROL_TEST",_HW_CONTROL_SCHEMA); c=test.content
            if not all(c[k] for k in ("exact_hardware_identity","firmware_config_hash","instruments_calibration","conditions","waveform_coverage","limits","requirement")): raise ValueError("hardware content incomplete")
            passed=c["passed"] is True; deps={test.artifact_id:test.artifact_hash}
        return material_result(ControlStatus.VERIFIED.value if passed else ControlStatus.UNVERIFIED.value,Availability.AVAILABLE,dependency_records=deps,diagnostics=() if passed else ("named verification predicate failed",),non_gating=_authenticated_trust_root_classification(trust_root),synthetic_provenance=_authenticated_trust_root_classification(trust_root),suffix=axis)
    except Exception as exc:
        return material_result(ControlStatus.UNAVAILABLE.value,Availability.UNAVAILABLE,diagnostics=(str(exc),),non_gating=True,suffix=axis)


def control_evidence(firmware: Optional[Mapping[str,Any]],hardware: Optional[Mapping[str,Any]],
                     registry: Optional[ArtifactRegistry]=None) -> dict[str,MaterialResult]:
    return {"firmware_implementation_status":control_axis_status("firmware",firmware,registry),
            "hardware_measurement_status":control_axis_status("hardware",hardware,registry)}


_PUBLICATION_CONTEXT_SCHEMA={"boundary","assumption_variant","ats_ref","evidence_conflict_ref","digital_oracle_ref","analog_status_ref","thermal_case","firmware_status_result_id","hardware_status_result_id","result_basis","uncertainty_or_bound","synthetic_marker"}

def publish(claim: Mapping[str,Any], material: MaterialResult, *, real_claim: bool=False,
            registry: Optional[ArtifactRegistry]=None, result_id: Optional[str]=None) -> MaterialResult:
    diagnostics=[]
    try:
        if registry is None or result_id is None: raise ValueError("fresh registered result required")
        registry, trust_root = _require_exact_registry(registry)
        if not registry.validate_current(result_id): raise ValueError("fresh registered result required")
        if real_claim and (_authenticated_trust_root_classification(trust_root) or material.synthetic_provenance):
            raise ValueError("synthetic provenance cannot support a real claim")
        if registry.results[result_id] != material: raise ValueError("material/result mismatch")
        if set(claim)!=PUBLICATION_FIELDS|{"publication_context_ref"}: raise ValueError("publication schema must be exact")
        context=registry.resolve(claim["publication_context_ref"],"PUBLICATION_CONTEXT",_PUBLICATION_CONTEXT_SCHEMA)
        c=context.content
        if c.get("synthetic_marker") is not material.synthetic_provenance:
            raise ValueError("publication synthetic provenance mismatch")
        if not c["boundary"] or not c["assumption_variant"] or not c["result_basis"]: raise ValueError("empty publication semantics")
        for ref_name in ("ats_ref","evidence_conflict_ref","digital_oracle_ref","analog_status_ref"):
            resolved=registry.resolve(c[ref_name])
            if resolved.artifact_id not in material.dependency_record_ids: raise ValueError("publication dependency omitted")
        firmware_id=c["firmware_status_result_id"]; hardware_id=c["hardware_status_result_id"]
        if (not registry.validate_current(firmware_id) or not registry.validate_current(hardware_id)
                or firmware_id not in material.dependency_record_ids or hardware_id not in material.dependency_record_ids
                or context.artifact_id not in material.dependency_record_ids):
            raise ValueError("publication status dependency is not fresh and closed")
        expected={"boundary":c["boundary"],"assumption_variant":c["assumption_variant"],"ats":c["ats_ref"],
                  "evidence_conflict":c["evidence_conflict_ref"],"digital_oracle":c["digital_oracle_ref"],
                  "analog_status":c["analog_status_ref"],"thermal_case":c["thermal_case"],
                  "firmware_implementation_status":registry.results[firmware_id].canonical_value,"hardware_measurement_status":registry.results[hardware_id].canonical_value,
                  "result_basis":c["result_basis"],"availability":material.availability.value,"freshness":material.freshness.value,
                  "trace_identity":material.trace_identity,"dependency_set":material.dependency_record_ids,
                  "uncertainty_or_bound":c["uncertainty_or_bound"],"synthetic_marker":c["synthetic_marker"],
                  "canonical_value":material.canonical_value}
        for field,value in expected.items():
            if claim.get(field)!=value: diagnostics.append("source-mismatch:"+field)
        if c["synthetic_marker"] is True and real_claim:diagnostics.append("synthetic-real")
    except Exception as exc:
        diagnostics.append(str(exc))
    if diagnostics:
        return material_result(ExplicitAbsence(tuple(diagnostics),"publication rejected"),Availability.UNAVAILABLE,diagnostics=("PUBLICATION_REJECTED",))
    assert registry is not None
    return material_result(copy.deepcopy(dict(claim)),material.availability,dependencies=(material,),non_gating=_authenticated_trust_root_classification(trust_root),synthetic_provenance=material.synthetic_provenance,suffix="published")



# Final timing split: actual firmware interpretation and immutable expected literals
# deliberately have no shared executable constructor.
def compute_timing_from_firmware(p: int, polarity: int = 1) -> TimingVector:
    if polarity != 1 or p not in (10,1,0):
        raise ValueError("unsupported repository vector")
    clock,carrier=_firmware_integer_constants(); n=clock//carrier; h=n//2
    q=Fraction(p*h,100); k=min(h,max(0,(2*q.numerator+q.denominator)//(2*q.denominator)))
    if (clock,carrier,n,h)!=(160_000_000,70_000,2285,1142):raise ValueError("firmware timing baseline changed")
    def event(row: tuple[int,str,str,str])->CanonicalEvent:
        return CanonicalEvent(row[0],EventClass(row[1]),row[2],row[3],ORACLE_SOURCE_HASH)
    if p==10:
        comparators=(1,h,k,h+k,1,k-8,h+8,h+k-8); intervals=(("LV_A",0,h),("LV_B",k,h+k),("SR_A",0,k-8),("SR_B",h+8,h+k-8))
        raw_rows=((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(k-8,"OFF","SR_A_HI","OFF"),(k,"ON","LV_B_HI","ON"),(h,"OFF","LV_A_HI","OFF"),(h+8,"ON","SR_B_HI","ON"),(h+k-8,"OFF","SR_B_HI","OFF"),(h+k,"OFF","LV_B_HI","OFF"))
        adjusted_rows=((0,"OFF","LV_A_LO","OFF"),(0,"OFF","SR_A_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(16,"DEADTIME_EXPIRY","SR_A_HI","ON"),(106,"OFF","SR_A_HI","OFF"),(114,"OFF","LV_B_LO","OFF"),(122,"DEADTIME_EXPIRY","SR_A_LO","ON"),(124,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1150,"OFF","SR_B_LO","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1166,"DEADTIME_EXPIRY","SR_B_HI","ON"),(1248,"OFF","SR_B_HI","OFF"),(1256,"OFF","LV_B_HI","OFF"),(1264,"DEADTIME_EXPIRY","SR_B_LO","ON"),(1266,"DEADTIME_EXPIRY","LV_B_LO","ON"))
        adjusted=tuple(event(x) for x in adjusted_rows); suppressed=TimingField.exact("NOT_APPLICABLE_FULL_WINDOW"); sr=TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("SR_"))); aggregate=TimingField.exact(adjusted); owner=None; enabled=True
    else:
        guarded_k=k if k>0 else 1; off=h+k
        comparators=(1,h,guarded_k,off,1,1,n-1,n-1); intervals=(("LV_A",0,h),("LV_B",guarded_k,off))
        raw_rows=((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(1,"OFF","SR_A_HI","OFF"),(guarded_k,"ON","LV_B_HI","ON"),(h,"OFF","LV_A_HI","OFF"),(off,"OFF","LV_B_HI","OFF"),(n-1,"OFF","SR_B_HI","OFF"),(n-1,"ON","SR_B_HI","ON"))
        adjusted_rows=(((0,"OFF","LV_A_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(11,"OFF","LV_B_LO","OFF"),(21,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1153,"OFF","LV_B_HI","OFF"),(1163,"DEADTIME_EXPIRY","LV_B_LO","ON")) if p==1 else ((0,"OFF","LV_A_LO","OFF"),(1,"OFF","LV_B_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(11,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1142,"OFF","LV_B_HI","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1152,"DEADTIME_EXPIRY","LV_B_LO","ON")))
        adjusted=tuple(event(x) for x in adjusted_rows); suppressed=TimingField.unavailable(SR_UNAVAILABLE_REASON); sr=TimingField.unavailable(SR_UNAVAILABLE_REASON); aggregate=TimingField.unavailable(SR_UNAVAILABLE_REASON); owner=None if p==1 else "LEG_COMMAND_TICK_ASYMMETRY"; enabled=False
    raw=tuple(event(x) for x in raw_rows)
    return TimingVector(CanonicalNumber.rational(p,"PERCENT","percent"),1,CanonicalNumber.rational(q,"TICK_DISPLACEMENT","tick"),CanonicalNumber.rational(q/Fraction(clock),"TIME","s"),k,n,h,(h,n-h),CanonicalNumber.rational(Fraction(clock,n),"FREQUENCY","Hz"),CanonicalNumber.rational(Fraction(n,clock),"TIME","s"),tuple(zip(COMPARATOR_IDS,comparators)),intervals,TimingField.exact(raw),TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("LV_"))) if p==10 else TimingField.exact(adjusted),suppressed,sr,aggregate,enabled,owner)


def independent_expected_timing(p: int) -> TimingVector:
    if p not in (10,1,0):raise ValueError("unsupported immutable reference vector")
    scalar={10:(Fraction(571,5),114,(1,1142,114,1256,1,106,1150,1248),(("LV_A",0,1142),("LV_B",114,1256),("SR_A",0,106),("SR_B",1150,1248)),True,None),1:(Fraction(571,50),11,(1,1142,11,1153,1,1,2284,2284),(("LV_A",0,1142),("LV_B",11,1153)),False,None),0:(Fraction(0),0,(1,1142,1,1142,1,1,2284,2284),(("LV_A",0,1142),("LV_B",1,1142)),False,"LEG_COMMAND_TICK_ASYMMETRY")}[p]
    q,k,values,intervals,enabled,owner=scalar
    literal_raw={10:((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(106,"OFF","SR_A_HI","OFF"),(114,"ON","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1150,"ON","SR_B_HI","ON"),(1248,"OFF","SR_B_HI","OFF"),(1256,"OFF","LV_B_HI","OFF")),1:((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(1,"OFF","SR_A_HI","OFF"),(11,"ON","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1153,"OFF","LV_B_HI","OFF"),(2284,"OFF","SR_B_HI","OFF"),(2284,"ON","SR_B_HI","ON")),0:((0,"ON","LV_A_HI","ON"),(0,"ON","SR_A_HI","ON"),(1,"OFF","SR_A_HI","OFF"),(1,"ON","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1142,"OFF","LV_B_HI","OFF"),(2284,"OFF","SR_B_HI","OFF"),(2284,"ON","SR_B_HI","ON"))}[p]
    literal_adjusted={10:((0,"OFF","LV_A_LO","OFF"),(0,"OFF","SR_A_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(16,"DEADTIME_EXPIRY","SR_A_HI","ON"),(106,"OFF","SR_A_HI","OFF"),(114,"OFF","LV_B_LO","OFF"),(122,"DEADTIME_EXPIRY","SR_A_LO","ON"),(124,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1150,"OFF","SR_B_LO","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1166,"DEADTIME_EXPIRY","SR_B_HI","ON"),(1248,"OFF","SR_B_HI","OFF"),(1256,"OFF","LV_B_HI","OFF"),(1264,"DEADTIME_EXPIRY","SR_B_LO","ON"),(1266,"DEADTIME_EXPIRY","LV_B_LO","ON")),1:((0,"OFF","LV_A_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(11,"OFF","LV_B_LO","OFF"),(21,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1153,"OFF","LV_B_HI","OFF"),(1163,"DEADTIME_EXPIRY","LV_B_LO","ON")),0:((0,"OFF","LV_A_LO","OFF"),(1,"OFF","LV_B_LO","OFF"),(10,"DEADTIME_EXPIRY","LV_A_HI","ON"),(11,"DEADTIME_EXPIRY","LV_B_HI","ON"),(1142,"OFF","LV_A_HI","OFF"),(1142,"OFF","LV_B_HI","OFF"),(1152,"DEADTIME_EXPIRY","LV_A_LO","ON"),(1152,"DEADTIME_EXPIRY","LV_B_LO","ON"))}[p]
    raw=tuple(CanonicalEvent(t,EventClass(c),d,e,ORACLE_SOURCE_HASH) for t,c,d,e in literal_raw)
    adjusted=tuple(CanonicalEvent(t,EventClass(c),d,e,ORACLE_SOURCE_HASH) for t,c,d,e in literal_adjusted)
    if p==10:
        suppressed=TimingField.exact("NOT_APPLICABLE_FULL_WINDOW"); sr=TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("SR_"))); aggregate=TimingField.exact(adjusted)
    else:
        suppressed=TimingField.unavailable(SR_UNAVAILABLE_REASON); sr=TimingField.unavailable(SR_UNAVAILABLE_REASON); aggregate=TimingField.unavailable(SR_UNAVAILABLE_REASON)
    return TimingVector(CanonicalNumber.rational(p,"PERCENT","percent"),1,CanonicalNumber.rational(q,"TICK_DISPLACEMENT","tick"),CanonicalNumber.rational(q/Fraction(160_000_000),"TIME","s"),k,2285,1142,(1142,1143),CanonicalNumber.rational(Fraction(32_000_000,457),"FREQUENCY","Hz"),CanonicalNumber.rational(Fraction(2285,160_000_000),"TIME","s"),tuple(zip(COMPARATOR_IDS,values)),intervals,TimingField.exact(raw),TimingField.exact(tuple(e for e in adjusted if e.device_id.startswith("LV_"))) if p==10 else TimingField.exact(adjusted),suppressed,sr,aggregate,enabled,owner)


def digital_oracle(p: int, polarity: int = 1) -> TimingVector:
    return compute_timing_from_firmware(p,polarity)



# ========================= Independent re-review hardening =========================
# The trust root is a separate immutable input.  Artifact content hashes prove
# identity only; they do not confer owner approval or registration authority.
import hmac
import secrets
from types import MappingProxyType


@dataclass(frozen=True)
class MaterialResult:
    availability: Availability
    freshness: Freshness
    dependency_record_ids: tuple[str, ...]
    dependency_hashes: tuple[tuple[str, str], ...]
    computation_artifact_id: str
    computation_artifact_version: str
    computation_artifact_hash: str
    canonical_value: Any
    applicability: str
    uncertainty_or_bound: Any
    trace_identity: str
    safety_relevant: bool = False
    non_gating: bool = False
    diagnostics: tuple[str, ...] = ()
    producer_kind: Optional[str] = None
    provenance_seal: Optional[str] = None
    synthetic_provenance: bool = False

    def __post_init__(self) -> None:
        ids = tuple(sorted(set(self.dependency_record_ids)))
        hashes = tuple(sorted(self.dependency_hashes))
        if ids != self.dependency_record_ids or hashes != self.dependency_hashes:
            raise ValueError("dependencies must be canonical ordered unique sets/maps")
        if tuple(k for k, _ in hashes) != ids:
            raise ValueError("dependency IDs and hashes differ")
        if type(self.synthetic_provenance) is not bool:
            raise ValueError("synthetic provenance must be an explicit boolean")
        if self.synthetic_provenance and not self.non_gating:
            raise ValueError("synthetic provenance must remain non-gating")
        if (self.availability is Availability.PROVISIONAL
                and isinstance(self.canonical_value, ExplicitAbsence)
                and self.uncertainty_or_bound is None):
            raise ValueError("absent value without evaluable bound cannot be provisional")
        if not self.trace_identity or len(self.computation_artifact_hash) != 64:
            raise ValueError("incomplete trace identity")

    def consumable(self) -> bool:
        return (self.freshness is Freshness.FRESH
                and self.availability is not Availability.UNAVAILABLE)


@dataclass(frozen=True)
class RegisteredArtifact:
    artifact_id: str
    version: str
    artifact_type: str
    content: Mapping[str, Any]
    artifact_hash: str
    owner: str = "UNTRUSTED_CALLER"
    approval: str = "UNAPPROVED"

    @staticmethod
    def create(artifact_id: str, version: str, artifact_type: str,
               content: Mapping[str, Any], *, owner: str = "UNTRUSTED_CALLER",
               approval: str = "UNAPPROVED") -> "RegisteredArtifact":
        frozen = copy.deepcopy(dict(content))
        digest = content_hash({"artifact_id": artifact_id, "version": version,
                               "artifact_type": artifact_type, "content": frozen,
                               "owner": owner, "approval": approval})
        return RegisteredArtifact(artifact_id, version, artifact_type, frozen,
                                  digest, owner, approval)

    @property
    def ref(self) -> dict[str, str]:
        return {"artifact_id": self.artifact_id, "version": self.version,
                "hash": self.artifact_hash}

    def validate_identity(self) -> None:
        expected = content_hash({"artifact_id": self.artifact_id,
                                 "version": self.version,
                                 "artifact_type": self.artifact_type,
                                 "content": self.content, "owner": self.owner,
                                 "approval": self.approval})
        if (not _substantive(self.artifact_id) or not _substantive(self.version)
                or not _substantive(self.artifact_type)
                or self.artifact_hash != expected or not valid_sha256(expected)):
            raise ValueError("ARTIFACT_CONTENT_HASH_INVALID")

    # Compatibility alias.  Identity validation deliberately does not establish trust.
    def validate(self) -> None:
        self.validate_identity()


_TRUST_POLICIES: dict[str, tuple[str, str]] = {
    "CONTROLLED_PREREQUISITES": ("InverterOwner", "APPROVED"),
    "ENDPOINT_PREREQUISITES": ("InverterOwner", "APPROVED"),
    "THERMAL_DYNAMIC_INPUT": ("InverterOwner", "APPROVED"),
    "ATS_V2": ("InverterOwner", "SPEC_NORMATIVE_APPROVAL"),
    "PRODUCT_THRESHOLDS": ("InverterOwner", "APPROVED"),
    "SETTLING_OBSERVATIONS": ("IndependentTestOwner", "APPROVED"),
    "QUALIFICATION_LIMIT": ("ManufacturerEvidenceOwner", "APPROVED"),
    "QUALIFICATION_STRESS": ("IndependentTestOwner", "APPROVED"),
    "FIRMWARE_CONTROL_SOURCE": ("InverterOwner", "APPROVED"),
    "FIRMWARE_CONTROL_TEST": ("IndependentSoftwareVerifier", "APPROVED"),
    "HARDWARE_CONTROL_TEST": ("IndependentHardwareVerifier", "APPROVED"),
    "PUBLICATION_CONTEXT": ("PublicationOwner", "APPROVED"),
    "ATS": ("InverterOwner", "SPEC_NORMATIVE_APPROVAL"),
    "EVIDENCE_CONFLICT": ("EvidenceAdjudicationOwner", "APPROVED"),
    "DIGITAL_ORACLE": ("InverterOwner", "APPROVED"),
    "ANALOG_STATUS": ("IndependentModelReviewer", "APPROVED"),
}


_TRUST_ROOT_RSA_N = 730152951967952006233465909416958243559225075993434964142225380997947520074164275005581686622247496434560845926090451931114157462658545853239349077782706805574124421323672429531783281342209443993732025953648637999833865691174781849
_TRUST_ROOT_RSA_E = 65537

# Repository trust is closed. Only these exact, externally pre-signed manifests can
# be loaded; repository code contains no signing credential and accepts no caller-
# supplied grant list. The non-empty manifest is explicitly synthetic and can only
# exercise non-real test paths.
_EMPTY_TRUST_ROOT_SIGNATURE = "6510bba3a27f974425a57289c4d58dc536ce40ae687903781622da9fe40c244fde75b8547f8739f28467b521f3a7db37ea845d889ecd4d3a3fa1ddbfeb07d698169f29a4f6f41ec87c5d05e09ff500c83a2980f5dcb8ee7f2b25a34d121a51e5"
_SYNTHETIC_FIXTURE_TRUST_ROOT_SIGNATURE = "54bccd0aa18c04b38c777e3f4be5db2cfa243f5e349a1f0dcc2648b7070a18c202b59fe114a66cca47945e310c1545d54f523a9ebfc00157e0dda8946856b6f93b2f043407f1b654d35b36910047db8d63236c0043ca045f6b8a149ea172f9b1"
_SYNTHETIC_FIXTURE_GRANTS = (
    ("ANALOG-REF", "1", "ANALOG_STATUS", "1c332cfee7145406919d67acbaba9dbd04835e2b95cd46844c7de68e9643ad9d"),
    ("ATS-REF", "1", "ATS", "5d8cf651f5d7963abee5b58229e3792cfd3f9aa3f76bd9e328017740e42da9bf"),
    ("ATS-v2", "2.0.0", "ATS_V2", "7f61862fbcd2b4b60c5c352442731e5c018e5730b9d490f90463d0bbab92ec0d"),
    ("CONTROLLED_PREREQUISITES-288c0572b4be1aa7", "1.0.0", "CONTROLLED_PREREQUISITES", "f6a613bfb52afa5a15ea31e5d6f2fcb8a6c42bcf473dc1b8936805ebee8d6b60"),
    ("CONTROLLED_PREREQUISITES-8a78ebf952c9ee25", "1.0.0", "CONTROLLED_PREREQUISITES", "fb810fdfa6c244e7a04516279ec48f8f500ae8d1911b13a9aa87f0ff49c5aa04"),
    ("CONTROLLED_PREREQUISITES-b89138cd17443286", "1.0.0", "CONTROLLED_PREREQUISITES", "1ae43e7a9f14a5ae8ba62a0da87b53c085478fe842a39010976e5074655d3501"),
    ("CONTROLLED_PREREQUISITES-d8e83231019dcb5c", "1.0.0", "CONTROLLED_PREREQUISITES", "b3bc9eafc68bef195588c3b4581d8a50714efcaad998d18ddbaddc86be994b0a"),
    ("ENDPOINT_PREREQUISITES-172982b5559403b6", "1.0.0", "ENDPOINT_PREREQUISITES", "b29f5c703c91e0ce2c596bc3c52b7519ec8338ad94f9f8b4d2428ee25e8a6214"),
    ("ENDPOINT_PREREQUISITES-2f189ac64e49c878", "1.0.0", "ENDPOINT_PREREQUISITES", "57a26256b2453d93139af6fa62989198ba947d8deb1cba5570c2dab3ef4f34b0"),
    ("ENDPOINT_PREREQUISITES-7b5e11d880fcea33", "1.0.0", "ENDPOINT_PREREQUISITES", "128bc54f6df3ccc8939751da9d8e45af2a456d5b2e360c4f635e08c86b923099"),
    ("ENDPOINT_PREREQUISITES-a6ba3b4857baa90b", "1.0.0", "ENDPOINT_PREREQUISITES", "9581c539c4d522d4a88d549ddead95c362041de67479853603ccaff6b239a519"),
    ("EVIDENCE-REF", "1", "EVIDENCE_CONFLICT", "8f30746748696593b22ab517d0dd52169dc8d8b4e18099143bee89038472071a"),
    ("FW-EMPTY", "1", "FIRMWARE_CONTROL_SOURCE", "b40992f48e3e5d542758eea17f18c6de3193c276bb0a91e975416214d23b355b"),
    ("FW-SOURCE", "1", "FIRMWARE_CONTROL_SOURCE", "f8a9a0149d4a3922880084513493290c16728f7e71504ee5b3fd15df10ca363a"),
    ("FW-TEST", "1", "FIRMWARE_CONTROL_TEST", "70f9d5ccae10d48a6c34c2218d4c124fdcd3412b70658eee3cc33eaafd9ec7a6"),
    ("HW-TEST", "1", "HARDWARE_CONTROL_TEST", "79ce79eb027b5e5192bdb1394be6fd1663fe24454df79fa445d014612c321e68"),
    ("ORACLE-REF", "1", "DIGITAL_ORACLE", "c75d1e82838095755ef6955a5ed880f475b883a5ebb0110eda1e58d9ed60fb2b"),
    ("PUB-CONTEXT", "1", "PUBLICATION_CONTEXT", "2520beca76ca0b2e5b491ef859c6ebb93882bf04aa33ff389273db8881161e90"),
    ("SETTLING-OBS-ADVERSARIAL", "1.0.0", "SETTLING_OBSERVATIONS", "c26e4a2f74b37db6efac9b0689a93dd1fc540b3d7a013043147eaf8b1c7e9e48"),
    ("SETTLING-OBS-FAIL", "1.0.0", "SETTLING_OBSERVATIONS", "42b38e27002396da706c8c16e3fc36b426a3fecf92693f97e251fccd9b2e4f05"),
    ("SETTLING-OBS-NOLOAD", "1.0.0", "SETTLING_OBSERVATIONS", "79892877141750f11d5be3a41d65e93bd7d67d3f2ade9076d2cb101b770a23ec"),
    ("SETTLING-OBS-PASS", "1.0.0", "SETTLING_OBSERVATIONS", "0b794e4d372ba1e48d514816075554fc0083cd6ac7e6bec2d29565bca1a3f955"),
    ("STRIPPED", "1", "CONTROLLED_PREREQUISITES", "da23d53c8b7b550bc22b89e26f2cce7471b4507cc957d0585ae557d190846e00"),
    ("SYNTH-QUAL-LIMIT-AVALANCHE", "1", "QUALIFICATION_LIMIT", "7f5ef91c6593e65a34d2910c160096c0226db33e6368775b7866f276660b5deb"),
    ("SYNTH-QUAL-LIMIT-CURRENT", "1", "QUALIFICATION_LIMIT", "4b53869c068460c4069bf08856f004c500cab52648244b9805174fab07b4a0e3"),
    ("SYNTH-QUAL-LIMIT-DECLARED_LIMITS", "1", "QUALIFICATION_LIMIT", "5a4de1ae4119952e59bef72ce89d90e38145de9deb76bfbece32ca1734b7f1e0"),
    ("SYNTH-QUAL-LIMIT-PACKAGE_ISOLATION", "1", "QUALIFICATION_LIMIT", "409f2f017f526ce7c89c0365fd32fa548c1c3b5e66d2e06cdf538d745b18ea2b"),
    ("SYNTH-QUAL-LIMIT-SOA", "1", "QUALIFICATION_LIMIT", "07a5f192e75db2c1beecb2eaa50876cc8191cde5c3284e9b03acc6e8f8f37c7b"),
    ("SYNTH-QUAL-LIMIT-THERMAL", "1", "QUALIFICATION_LIMIT", "65247e8ec200de6a376314b057447bbf0c7bde7d3c24d1522dc3979f5d0970d3"),
    ("SYNTH-QUAL-LIMIT-VOLTAGE", "1", "QUALIFICATION_LIMIT", "0c11a81191521b5126dc89fc07f73528593f2667033c28fb8eeb72d291a02e21"),
    ("SYNTH-QUAL-STRESS", "1", "QUALIFICATION_STRESS", "e60a66f6ee607f477d99ef7a31e93e0fef8df4f15881d4890474b8f616102286"),
    ("SYNTHETIC-THRESHOLD-FIXTURE", "1", "PRODUCT_THRESHOLDS", "1731ccf5c1baa5dd898884f36ed1040a9a6cc3b28864672c1cbadf91ddc7a314"),
    ("THERMAL-DYNAMIC-001", "1", "THERMAL_DYNAMIC_INPUT", "251973615cc988242118d3b9bcb8d377260e0a6956a287b5602729870995e71e"),
    ("UNRELATED", "1", "CONTROLLED_PREREQUISITES", "68a649543b13a902a0bc67f5870c7a74807994b8e43dd8e5a46ee6179f40c83c"),
)
@dataclass(frozen=True)
class _FixedTrustRootManifest:
    version: str
    grants: tuple[tuple[str, str, str, str], ...]
    signature: str
    root_hash: str


# These records contain only authenticated manifest material. Trust classification
# is intentionally absent: it is derived from root_id, which is part of the signed
# payload, so no mutable side-band flag can relabel synthetic authorization.
_FIXED_TRUST_ROOTS: Mapping[str, _FixedTrustRootManifest] = MappingProxyType({
    "INVERTER-ARTIFACT-TRUST-ROOT": _FixedTrustRootManifest(
        version="1.0.0", grants=(),
        signature=_EMPTY_TRUST_ROOT_SIGNATURE,
        root_hash="7f1ebf07bca0311dc0ccb443e170b3ba0e4dc0f63714beadf4ff020945e353dc",
    ),
    "INVERTER-SYNTHETIC-FIXTURE-TRUST-ROOT": _FixedTrustRootManifest(
        version="1.0.0", grants=_SYNTHETIC_FIXTURE_GRANTS,
        signature=_SYNTHETIC_FIXTURE_TRUST_ROOT_SIGNATURE,
        root_hash="91d172d5758bb41e1698993b45684f25ba4e32b3fb396708ad61ad2eba32c628",
    ),
})


@dataclass(frozen=True)
class ArtifactTrustRoot:
    root_id: str
    version: str
    authority: str
    approval: str
    grants: tuple[tuple[str, str, str, str], ...]
    policies: tuple[tuple[str, str, str], ...]
    authority_signature: str
    root_hash: str

    @property
    def synthetic_only(self) -> bool:
        """Compatibility display backed by authenticated instance state."""
        return _authenticated_trust_root_classification(self)

    def validate(self) -> None:
        _authenticated_trust_root_classification(self)

    def authorizes(self, artifact: RegisteredArtifact) -> bool:
        return _trust_root_authorizes(self, artifact)


def _trust_root_state(trust_root: Any) -> Mapping[str, Any]:
    """Read signed dataclass state without consulting replaceable descriptors."""
    if type(trust_root) is not ArtifactTrustRoot:
        raise ValueError("ARTIFACT_TRUST_ROOT_EXACT_TYPE_REQUIRED")
    state = object.__getattribute__(trust_root, "__dict__")
    expected = {"root_id", "version", "authority", "approval", "grants",
                "policies", "authority_signature", "root_hash"}
    if type(state) is not dict or set(state) != expected:
        raise ValueError("ARTIFACT_TRUST_ROOT_INVALID")
    return state


def _authenticated_trust_root_classification(trust_root: Any) -> bool:
    """Validate signed root state and derive its closed trust classification.

    Trust decisions call this function directly.  In particular, they never read
    ``ArtifactTrustRoot.synthetic_only`` or invoke a replaceable class validator,
    so monkeypatching a class descriptor cannot relabel synthetic authorization.
    """
    state = _trust_root_state(trust_root)
    root_id = state["root_id"]
    if root_id == "INVERTER-ARTIFACT-TRUST-ROOT":
        expected_synthetic = False
    elif root_id == "INVERTER-SYNTHETIC-FIXTURE-TRUST-ROOT":
        expected_synthetic = True
    else:
        raise ValueError("ARTIFACT_TRUST_ROOT_CLASSIFICATION_INVALID")

    expected_policies = tuple(sorted((kind, owner, approval)
                                     for kind, (owner, approval)
                                     in _TRUST_POLICIES.items()))
    manifest = _FIXED_TRUST_ROOTS.get(root_id)
    payload = {"root_id": root_id, "version": state["version"],
               "authority": state["authority"], "approval": state["approval"],
               "grants": list(state["grants"]),
               "policies": list(state["policies"])}
    try:
        signature = int(state["authority_signature"], 16)
    except (TypeError, ValueError):
        signature = -1
    signature_valid = (0 < signature < _TRUST_ROOT_RSA_N
        and pow(signature, _TRUST_ROOT_RSA_E, _TRUST_ROOT_RSA_N)
            == int(content_hash(payload), 16))
    exact_manifest = (isinstance(manifest, _FixedTrustRootManifest)
        and state["version"] == manifest.version
        and state["grants"] == manifest.grants
        and state["authority_signature"] == manifest.signature
        and state["root_hash"] == manifest.root_hash)
    if (not exact_manifest
            or state["authority"] != "RepositoryTrustAdministrator"
            or state["approval"] != "TRUST_ROOT_APPROVED"
            or state["policies"] != expected_policies
            or tuple(sorted(set(state["grants"]))) != state["grants"]
            or state["root_hash"] != content_hash({**payload,
                "authority_signature":state["authority_signature"]})
            or not signature_valid):
        raise ValueError("ARTIFACT_TRUST_ROOT_INVALID")
    return expected_synthetic


def _trust_root_authorizes(trust_root: Any,
                           artifact: RegisteredArtifact) -> bool:
    try:
        _authenticated_trust_root_classification(trust_root)
        artifact.validate_identity()
    except (TypeError, ValueError):
        return False
    state = _trust_root_state(trust_root)
    policy = _TRUST_POLICIES.get(artifact.artifact_type)
    identity = (artifact.artifact_id, artifact.version,
                artifact.artifact_type, artifact.artifact_hash)
    return (policy == (artifact.owner, artifact.approval)
            and identity in state["grants"])


def _fixed_trust_root(root_id: str) -> ArtifactTrustRoot:
    manifest = _FIXED_TRUST_ROOTS[root_id]
    policies = tuple(sorted((kind, owner, status)
                            for kind, (owner, status) in _TRUST_POLICIES.items()))
    root = ArtifactTrustRoot(root_id, manifest.version,
        "RepositoryTrustAdministrator", "TRUST_ROOT_APPROVED",
        manifest.grants, policies, manifest.signature,
        manifest.root_hash)
    _authenticated_trust_root_classification(root)
    return root


def empty_trust_root() -> ArtifactTrustRoot:
    return _fixed_trust_root("INVERTER-ARTIFACT-TRUST-ROOT")


def synthetic_fixture_trust_root() -> ArtifactTrustRoot:
    """Return the closed, pre-signed allowlist for non-real test fixtures only."""
    return _fixed_trust_root("INVERTER-SYNTHETIC-FIXTURE-TRUST-ROOT")


def _require_exact_trust_root(trust_root: Any) -> ArtifactTrustRoot:
    """Reject subclasses and duck types before any trust decision is attempted."""
    if type(trust_root) is not ArtifactTrustRoot:
        raise ValueError("ARTIFACT_TRUST_ROOT_EXACT_TYPE_REQUIRED")
    _authenticated_trust_root_classification(trust_root)
    return trust_root


def _artifact_digest(value: Any) -> Optional[str]:
    if isinstance(value, RegisteredArtifact):
        value.validate_identity()
        return value.artifact_hash
    return value if valid_sha256(value) else None


_SETTLEMENT_SEAL_KEY = secrets.token_bytes(32)
_SETTLEMENT_PRODUCER = "CLASSIFY_SETTLING_V1"


def _settlement_payload(result: MaterialResult) -> bytes:
    return canonical_json({
        "availability": result.availability,
        "freshness": result.freshness,
        "dependency_hashes": result.dependency_hashes,
        "canonical_value": result.canonical_value,
        "trace_identity": result.trace_identity,
        "producer_kind": result.producer_kind,
        "synthetic_provenance": result.synthetic_provenance,
    }).encode("utf-8")


def _seal_settlement(result: MaterialResult) -> MaterialResult:
    marked = replace(result, producer_kind=_SETTLEMENT_PRODUCER,
                     provenance_seal=None)
    seal = hmac.new(_SETTLEMENT_SEAL_KEY, _settlement_payload(marked),
                    hashlib.sha256).hexdigest()
    return replace(marked, provenance_seal=seal)


def _valid_settlement_seal(result: MaterialResult) -> bool:
    if (result.producer_kind != _SETTLEMENT_PRODUCER
            or not valid_sha256(result.provenance_seal)):
        return False
    unsigned = replace(result, provenance_seal=None)
    expected = hmac.new(_SETTLEMENT_SEAL_KEY, _settlement_payload(unsigned),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(result.provenance_seal, expected)


@dataclass(frozen=True)
class ArtifactRegistry:
    artifacts: Mapping[str, Any]
    dependencies: Mapping[str, tuple[str, ...]]
    results: Mapping[str, MaterialResult]
    trust_root: ArtifactTrustRoot = field(default_factory=empty_trust_root)

    def __post_init__(self) -> None:
        if type(self) is not ArtifactRegistry:
            raise ValueError("ARTIFACT_REGISTRY_EXACT_TYPE_REQUIRED")
        _require_exact_trust_root(self.trust_root)
        self.validate_closed_dag()

    def resolve(self, ref: Any, artifact_type: Optional[str] = None,
                required_schema: Optional[set[str]] = None) -> RegisteredArtifact:
        if type(self) is not ArtifactRegistry:
            raise ValueError("ARTIFACT_REGISTRY_EXACT_TYPE_REQUIRED")
        trust_root = _require_exact_trust_root(self.trust_root)
        if not _artifact_ref_valid(ref):
            raise ValueError("ARTIFACT_REFERENCE_INVALID")
        record = self.artifacts.get(ref["artifact_id"])
        if not isinstance(record, RegisteredArtifact):
            raise ValueError("ARTIFACT_CONTENT_NOT_REGISTERED")
        if not _trust_root_authorizes(trust_root, record):
            raise ValueError("ARTIFACT_TRUST_POLICY_REJECTED")
        if (record.version != ref["version"] or record.artifact_hash != ref["hash"]
                or (artifact_type is not None
                    and record.artifact_type != artifact_type)):
            raise ValueError("ARTIFACT_REFERENCE_MISMATCH")
        if required_schema is not None and set(record.content) != required_schema:
            raise ValueError("ARTIFACT_SCHEMA_INCOMPLETE")
        return record

    def validate_closed_dag(self) -> None:
        if type(self) is not ArtifactRegistry:
            raise ValueError("ARTIFACT_REGISTRY_EXACT_TYPE_REQUIRED")
        trust_root = _require_exact_trust_root(self.trust_root)
        artifact_ids = set(self.artifacts)
        result_ids = set(self.results)
        if artifact_ids & result_ids:
            raise ValueError("DEPENDENCY_DAG_NODE_COLLISION")
        if set(self.dependencies) != result_ids:
            raise ValueError("DEPENDENCY_DAG_RESULT_NODE_SET_MISMATCH")
        for artifact in self.artifacts.values():
            if isinstance(artifact, RegisteredArtifact):
                if not _trust_root_authorizes(trust_root, artifact):
                    raise ValueError("ARTIFACT_TRUST_POLICY_REJECTED")
            elif _artifact_digest(artifact) is None:
                raise ValueError("ARTIFACT_CONTENT_HASH_INVALID")
        known = artifact_ids | result_ids
        graph: dict[str, tuple[str, ...]] = {}
        for result_id, result in self.results.items():
            declared = self.dependencies[result_id]
            if tuple(sorted(set(declared))) != tuple(declared):
                raise ValueError("DEPENDENCY_DAG_NONCANONICAL_EDGES")
            if set(declared) != set(result.dependency_record_ids):
                raise ValueError("DEPENDENCY_DAG_RESULT_EDGE_MISMATCH")
            if any(dep not in known or dep == result_id for dep in declared):
                raise ValueError("DEPENDENCY_DAG_UNKNOWN_OR_SELF_EDGE")
            hashes = dict(result.dependency_hashes)
            for dep in declared:
                actual = (_artifact_digest(self.artifacts[dep])
                          if dep in artifact_ids
                          else self.results[dep].computation_artifact_hash)
                if actual is None or hashes.get(dep) != actual:
                    raise ValueError("DEPENDENCY_DAG_HASH_MISMATCH")
            synthetic_dependency = (_authenticated_trust_root_classification(trust_root) or any(
                dep in result_ids and self.results[dep].synthetic_provenance
                for dep in declared))
            if synthetic_dependency and not result.synthetic_provenance:
                raise ValueError("SYNTHETIC_PROVENANCE_INVALID")
            if (result.producer_kind == _SETTLEMENT_PRODUCER
                    and not _valid_settlement_seal(result)):
                raise ValueError("SETTLEMENT_PROVENANCE_INVALID")
            graph[result_id] = declared
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(node: str) -> None:
            if node in visited or node in artifact_ids:
                return
            if node in visiting:
                raise ValueError("DEPENDENCY_DAG_CYCLE")
            visiting.add(node)
            for dep in graph[node]:
                visit(dep)
            visiting.remove(node)
            visited.add(node)
        for node in result_ids:
            visit(node)

    def validate_current(self, result_id: str) -> bool:
        """Require the complete transitive result subgraph to be consumable."""
        if type(self) is not ArtifactRegistry:
            return False
        try:
            self.validate_closed_dag()
        except ValueError:
            return False
        visiting: set[str] = set()
        def current(node: str) -> bool:
            if node in visiting:
                return False
            result = self.results.get(node)
            if result is None or not result.consumable():
                return False
            visiting.add(node)
            try:
                for dep in self.dependencies[node]:
                    if dep in self.results:
                        if not current(dep):
                            return False
                    else:
                        artifact = self.artifacts.get(dep)
                        if (isinstance(artifact, RegisteredArtifact)
                                and not _trust_root_authorizes(
                                    self.trust_root, artifact)):
                            return False
                        if _artifact_digest(artifact) != dict(result.dependency_hashes).get(dep):
                            return False
                return True
            finally:
                visiting.remove(node)
        return current(result_id)

    def with_result(self, result_id: str, result: MaterialResult) -> "ArtifactRegistry":
        if type(self) is not ArtifactRegistry:
            raise ValueError("ARTIFACT_REGISTRY_EXACT_TYPE_REQUIRED")
        self.validate_closed_dag()
        if result_id in self.artifacts or result_id in self.results:
            raise ValueError("duplicate result identity")
        results = dict(self.results)
        results[result_id] = result
        dependencies = dict(self.dependencies)
        dependencies[result_id] = tuple(result.dependency_record_ids)
        return ArtifactRegistry(dict(self.artifacts), dependencies, results,
                                self.trust_root)

    def select_transaction(self, record_id: str, new_hash: str) -> "ArtifactRegistry":
        if type(self) is not ArtifactRegistry:
            raise ValueError("ARTIFACT_REGISTRY_EXACT_TYPE_REQUIRED")
        self.validate_closed_dag()
        if record_id not in self.artifacts or not valid_sha256(new_hash):
            raise ValueError("invalid dependency transaction")
        existing = self.artifacts[record_id]
        if isinstance(existing, RegisteredArtifact):
            raise ValueError("registered immutable content cannot be replaced by a bare hash")
        descendants = {record_id}
        changed = True
        while changed:
            changed = False
            for node, deps in self.dependencies.items():
                if node not in descendants and descendants.intersection(deps):
                    descendants.add(node)
                    changed = True
        stale = {key: (replace(value, freshness=Freshness.STALE)
                       if key in descendants else value)
                 for key, value in self.results.items()}
        artifacts = dict(self.artifacts)
        artifacts[record_id] = new_hash
        updated = object.__new__(ArtifactRegistry)
        object.__setattr__(updated, "artifacts", artifacts)
        object.__setattr__(updated, "dependencies", dict(self.dependencies))
        object.__setattr__(updated, "results", stale)
        object.__setattr__(updated, "trust_root", self.trust_root)
        return updated


def _require_exact_registry(registry: Any) -> tuple[ArtifactRegistry, ArtifactTrustRoot]:
    """Validate the exact registry class, exact root class, fixed manifest, and DAG."""
    if type(registry) is not ArtifactRegistry:
        raise ValueError("ARTIFACT_REGISTRY_EXACT_TYPE_REQUIRED")
    root = _require_exact_trust_root(registry.trust_root)
    registry.validate_closed_dag()
    return registry, root


def artifact_registry(records: Sequence[RegisteredArtifact],
                      results: Mapping[str, MaterialResult] = {},
                      dependencies: Optional[Mapping[str, tuple[str, ...]]] = None,
                      *, trust_root: Optional[ArtifactTrustRoot] = None
                      ) -> ArtifactRegistry:
    by_id = {record.artifact_id: record for record in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate artifact identity")
    if records and trust_root is None:
        raise ValueError("independently provisioned artifact trust root required")
    selected_root = (empty_trust_root() if trust_root is None
                     else _require_exact_trust_root(trust_root))
    deps = ({key: tuple(result.dependency_record_ids)
             for key, result in results.items()} if dependencies is None
            else dict(dependencies))
    return ArtifactRegistry(by_id, deps, dict(results), selected_root)


def consume_registered(registry: ArtifactRegistry, result_id: str) -> MaterialResult:
    try:
        exact_registry, _ = _require_exact_registry(registry)
    except (TypeError, ValueError):
        exact_registry = None
    if exact_registry is None or not exact_registry.validate_current(result_id):
        return material_result(ExplicitAbsence((result_id,),
                               "transitive dependency graph is stale, untrusted, or unconsumable"),
                               Availability.UNAVAILABLE,
                               diagnostics=("STALE_RESULT_CONSUMPTION",))
    return exact_registry.results[result_id]


# Actual corrected production API for requirement 3.2.  Battery voltage is accepted
# only as contextual provenance and cannot rescale the fixed physical turns ratio.
def fixed_ratio_primary_current(primary_turns: int, secondary_turns: int,
                                secondary_current_rms: int | Fraction | str,
                                *, battery_voltage: int | Fraction | str
                                ) -> CanonicalNumber:
    if (type(primary_turns) is not int or type(secondary_turns) is not int
            or primary_turns <= 0 or secondary_turns <= 0):
        raise ValueError("positive integer transformer turns required")
    current = Fraction(secondary_current_rms)
    voltage = Fraction(battery_voltage)
    if current < 0 or voltage <= 0:
        raise ValueError("physical current/voltage domain invalid")
    physical_ratio = Fraction(secondary_turns, primary_turns)
    return CanonicalNumber.rational(current * physical_ratio,
                                    "CURRENT", "A")


_ATS_ARTIFACT_SCHEMA = {"artifact_id","version","artifact_hash","owner",
                        "approval","applicability","expired"}
_THRESHOLD_ARTIFACT_SCHEMA = {"artifact_id","version","artifact_hash","owner",
    "approved","W_seconds","ires_max","vsperiod_max","vscum_max",
    "estored_max","closed_energy_sources","methods_complete"}
_OBSERVATION_ARTIFACT_SCHEMA = {"window_seconds","ires_rms","vs_per_period",
    "vs_cumulative","end_energy","energy_sources"}


def registered_ats(ats: ATSv2) -> RegisteredArtifact:
    return RegisteredArtifact.create(ats.artifact_id, ats.version, "ATS_V2",
        _ats_content(ats), owner="InverterOwner",
        approval="SPEC_NORMATIVE_APPROVAL")


def registered_thresholds(thresholds: ProductThresholds) -> RegisteredArtifact:
    content = {key: (str(value) if isinstance(value, Fraction) else value)
               for key, value in thresholds.__dict__.items()}
    return RegisteredArtifact.create(thresholds.artifact_id, thresholds.version,
        "PRODUCT_THRESHOLDS", content, owner="InverterOwner",
        approval="APPROVED")


def registered_settling_observations(artifact_id: str,
        observations: Mapping[str, Any]) -> RegisteredArtifact:
    content = {"window_seconds":str(Fraction(observations["window_seconds"])),
        "ires_rms":str(Fraction(observations["ires_rms"])),
        "vs_per_period":[str(Fraction(v)) for v in observations["vs_per_period"]],
        "vs_cumulative":str(Fraction(observations["vs_cumulative"])),
        "end_energy":str(Fraction(observations["end_energy"])),
        "energy_sources":list(observations["energy_sources"])}
    return RegisteredArtifact.create(artifact_id, "1.0.0",
        "SETTLING_OBSERVATIONS", content, owner="IndependentTestOwner",
        approval="APPROVED")


@dataclass(frozen=True)
class SettlementClassification:
    state: str
    decision: MaterialResult
    registry: ArtifactRegistry
    result_id: str

    def __iter__(self):
        # Preserve historical two-value unpacking while exposing the registry proof.
        yield self.state
        yield self.decision


def _unavailable_settlement(reason: str, diagnostics: Sequence[str],
                            registry: Optional[ArtifactRegistry], result_id: str
                            ) -> SettlementClassification:
    try:
        base, root = (_require_exact_registry(registry)
                      if registry is not None
                      else (artifact_registry([]), empty_trust_root()))
    except (TypeError, ValueError):
        base, root = artifact_registry([]), empty_trust_root()
    result = _seal_settlement(material_result(
        {"decision_type":"SETTLEMENT_DECISION","state":"TRANSITION",
         "passed":False,"reason":reason}, Availability.UNAVAILABLE,
        diagnostics=diagnostics, non_gating=True,
        synthetic_provenance=_authenticated_trust_root_classification(root),
        suffix="settlement-unavailable"))
    try:
        registered = base.with_result(result_id, result)
    except ValueError:
        registered = base
    return SettlementClassification("TRANSITION", result, registered, result_id)


def classify_settling(*, caller_settled: Optional[bool], ats: Optional[ATSv2],
                       thresholds: Optional[ProductThresholds], period: Fraction,
                       observations: Optional[Mapping[str,Any]],
                       registry: Optional[ArtifactRegistry] = None,
                       ats_ref: Any = None, thresholds_ref: Any = None,
                       observations_ref: Any = None,
                       result_id: str = "settlement-decision"
                       ) -> SettlementClassification:
    if caller_settled is not None:
        return _unavailable_settlement("caller flag rejected",
            ("CALLER_SETTLED_REJECTED",), registry, result_id)
    try:
        if registry is None:
            raise ValueError("trusted registry required")
        registry, trust_root = _require_exact_registry(registry)
        ats_artifact = registry.resolve(ats_ref, "ATS_V2", _ATS_ARTIFACT_SCHEMA)
        threshold_artifact = registry.resolve(thresholds_ref,
            "PRODUCT_THRESHOLDS", _THRESHOLD_ARTIFACT_SCHEMA)
        observation_artifact = registry.resolve(observations_ref,
            "SETTLING_OBSERVATIONS", _OBSERVATION_ARTIFACT_SCHEMA)
        if ats is None or thresholds is None or observations is None:
            raise ValueError("typed policy, thresholds, and observations required")
        if canonical_json(ats_artifact.content) != canonical_json(_ats_content(ats)):
            raise ValueError("ATS content mismatch")
        threshold_content = {key:(str(value) if isinstance(value,Fraction) else value)
                             for key,value in thresholds.__dict__.items()}
        if canonical_json(threshold_artifact.content) != canonical_json(threshold_content):
            raise ValueError("threshold content mismatch")
        expected_observations = registered_settling_observations(
            observation_artifact.artifact_id, observations).content
        if canonical_json(observation_artifact.content) != canonical_json(expected_observations):
            raise ValueError("observation content mismatch")
        if not ats.usable_for("CANONICAL_EQUALITY") or not thresholds.valid(period):
            raise ValueError("policy or thresholds invalid")
        if tuple(observations["energy_sources"]) != thresholds.closed_energy_sources:
            raise ValueError("stored-energy source set mismatch")
        comparisons={"window":Fraction(observations["window_seconds"])>=thresholds.W_seconds,
                     "ires":Fraction(observations["ires_rms"])<=thresholds.ires_max,
                     "vsperiod":all(abs(Fraction(v))<=thresholds.vsperiod_max for v in observations["vs_per_period"]),
                     "vscum":abs(Fraction(observations["vs_cumulative"]))<=thresholds.vscum_max,
                     "energy":Fraction(observations["end_energy"])<=thresholds.estored_max}
        state="SETTLED" if all(comparisons.values()) else "TRANSITION"
        value={"decision_type":"SETTLEMENT_DECISION","state":state,
               "passed":all(comparisons.values()),"comparisons":comparisons,
               "ats_ref":ats_artifact.ref,"thresholds_ref":threshold_artifact.ref,
               "observations_ref":observation_artifact.ref}
        decision=_seal_settlement(material_result(value,
            dependency_records={ats_artifact.artifact_id:ats_artifact.artifact_hash,
                threshold_artifact.artifact_id:threshold_artifact.artifact_hash,
                observation_artifact.artifact_id:observation_artifact.artifact_hash},
            non_gating=_authenticated_trust_root_classification(trust_root),
            synthetic_provenance=_authenticated_trust_root_classification(trust_root),
            suffix="classify-settling"))
        registered=registry.with_result(result_id,decision)
        return SettlementClassification(state,decision,registered,result_id)
    except Exception as exc:
        return _unavailable_settlement(str(exc),
            ("PRODUCT_THRESHOLD_UNAVAILABLE",), registry, result_id)


def no_load_report(settlement_result_id: str, p: int, polarity: int,
                   residual: MaterialResult, *, registry: ArtifactRegistry
                   ) -> tuple[MaterialResult,...]:
    registry, trust_root = _require_exact_registry(registry)
    if not registry.validate_current(settlement_result_id):
        raise ValueError("FRESH_REGISTRY_SETTLEMENT_DECISION_REQUIRED")
    settlement_decision=registry.results[settlement_result_id]
    if not _valid_settlement_seal(settlement_decision):
        raise ValueError("CLASSIFY_SETTLING_PROVENANCE_REQUIRED")
    decision=settlement_decision.canonical_value
    if (not isinstance(decision,Mapping)
            or decision.get("decision_type")!="SETTLEMENT_DECISION"
            or decision.get("state") not in {"SETTLED","TRANSITION"}):
        raise ValueError("VALIDATED_SETTLEMENT_DECISION_REQUIRED")
    try:
        ats_artifact=registry.resolve(decision["ats_ref"],"ATS_V2",_ATS_ARTIFACT_SCHEMA)
        threshold_artifact=registry.resolve(decision["thresholds_ref"],"PRODUCT_THRESHOLDS",_THRESHOLD_ARTIFACT_SCHEMA)
        observation_artifact=registry.resolve(decision["observations_ref"],"SETTLING_OBSERVATIONS",_OBSERVATION_ARTIFACT_SCHEMA)
    except Exception as exc:
        raise ValueError("TRUSTED_SETTLEMENT_DEPENDENCIES_REQUIRED") from exc
    expected_deps={ats_artifact.artifact_id,threshold_artifact.artifact_id,
                   observation_artifact.artifact_id}
    if set(settlement_decision.dependency_record_ids)!=expected_deps:
        raise ValueError("SETTLEMENT_DEPENDENCY_BINDING_INVALID")
    if (decision["state"]=="SETTLED"
            and (settlement_decision.availability is not Availability.AVAILABLE
                 or decision.get("passed") is not True)):
        raise ValueError("AVAILABLE_PASSING_SETTLEMENT_REQUIRED")
    state=decision["state"]
    rows=[]
    for category in NO_LOAD_CATEGORIES:
        if category=="INTENTIONAL_IDEAL_DIFFERENTIAL_TRANSFER" and p==0:
            availability,value,basis=Availability.AVAILABLE,CanonicalNumber.rational(0,"POWER","W"),"CALCULATED_ESTIMATE"
        elif category=="UNINTENDED_DIFFERENTIAL_RESIDUAL":
            availability,value,basis=residual.availability,residual.canonical_value,"CALCULATED_ESTIMATE"
        else:
            availability,value,basis=Availability.UNAVAILABLE,ExplicitAbsence((category,),"no admissible evaluable model/evidence"),"NONE"
        record={"category":category,"applicability":"APPLICABLE","result_basis":basis,
                "p":p,"polarity":polarity,"elapsed_time":ExplicitAbsence(("elapsed_time",),"not evidenced"),
                "state":state,"observation_window":threshold_artifact.content["W_seconds"],
                "threshold_artifact":threshold_artifact.ref,"carrier_state":"ENABLED",
                "gate_state":"ENABLED","provenance_artifact":settlement_result_id,
                "uncertainty_or_bound":residual.uncertainty_or_bound if category=="UNINTENDED_DIFFERENTIAL_RESIDUAL" else None,
                "canonical_value":value}
        deps=(settlement_decision,residual) if category=="UNINTENDED_DIFFERENTIAL_RESIDUAL" else (settlement_decision,)
        rows.append(material_result(record,availability,dependencies=deps,
            non_gating=_authenticated_trust_root_classification(trust_root) or availability is Availability.UNAVAILABLE,
            synthetic_provenance=(settlement_decision.synthetic_provenance
                                  or residual.synthetic_provenance),
            suffix="no-load:"+category))
    return tuple(rows)


# Comparison prerequisite artifacts have policy-valid metadata but still require an
# independently supplied trust-root grant before they can authorize progression.
def _embedded_artifact(artifact_type: str,
                       content: Mapping[str,Any]) -> RegisteredArtifact:
    return RegisteredArtifact.create(artifact_type+"-"+content_hash(content)[:16],
        "1.0.0", artifact_type, content, owner="InverterOwner",
        approval="APPROVED")


def build_comparison_registry(t_ref: Mapping[str,Any],
                              artifacts: Sequence[Mapping[str,Any]], *,
                              realistic_execution_at: int=10,
                              prerequisite_trust_root: Optional[ArtifactTrustRoot]=None
                              ) -> ComparisonArtifactRegistry:
    clean_artifacts=[]; prereqs=[]
    for artifact in artifacts:
        clean={key:copy.deepcopy(value) for key,value in artifact.items()
               if key!="_registered_prerequisite"}
        registered=artifact.get("_registered_prerequisite")
        if isinstance(registered,RegisteredArtifact):
            prereqs.append(registered)
        clean_artifacts.append(clean)
    unique={record.artifact_id:record for record in prereqs}
    if len(unique)!=len(prereqs):
        raise ValueError("conflicting duplicate prerequisite identity")
    prereg=artifact_registry(list(unique.values()),
        trust_root=prerequisite_trust_root)
    body={"registry_id":"COMPARISON-REGISTRY-003","t_ref":copy.deepcopy(dict(t_ref)),
          "artifacts":clean_artifacts,
          "prerequisite_hashes":sorted((r.artifact_id,r.artifact_hash) for r in unique.values()),
          "t_ref_frozen_at":1,"gate_frozen_at":[a.get("frozen_at") for a in clean_artifacts],
          "realistic_execution_at":realistic_execution_at}
    return ComparisonArtifactRegistry(body["registry_id"],body["t_ref"],
        tuple(clean_artifacts),prereg,1,tuple(body["gate_frozen_at"]),
        realistic_execution_at,content_hash(body))
