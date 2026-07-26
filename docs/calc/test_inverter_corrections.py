#!/usr/bin/env python3
"""Finite unit, property-style, integration, trace, and publication tests.

All property generators are deterministic and bounded; no watcher or network is used.
"""
from __future__ import annotations

import copy
import hashlib
import math
import sys
import unittest
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

CALC = Path(__file__).resolve().parent
ROOT = CALC.parents[1]
if str(CALC) not in sys.path: sys.path.insert(0,str(CALC))

from inverter_corrections import *


def temperatures(): return {n:25.0 for n in THERMAL_NODES}
def domains(): return {n:(-40.0,175.0) for n in THERMAL_NODES}
def tref():
    body={"value":75.0,"unit":"degC","baseline_domain":[-40.0,175.0],"replacement_domain":[-40.0,175.0]}
    return {**body,"artifact_hash":content_hash(body)}
def valid_artifacts(controlled=None,endpoint=None):
    controlled = controlled or controlled_threefold(10.0,True,Fraction(3,5),2)
    endpoint = endpoint or endpoint_sensitivity([{"candidate_id":"c1","current":1.0,"conduction_nonempty":True}],CanonicalNumber.rational(1,"RESISTANCE","mOhm"),CanonicalNumber.rational(2,"RESISTANCE","mOhm"),endpoint_evidence=True,policy=normative_ats(),fixed_inputs=True,closed_immutable_set=True)
    return [frozen_gate_artifact("GATE-CONTROLLED-001",GateIdentity.CONTROLLED_THREEFOLD,controlled,frozen_at=2),frozen_gate_artifact("GATE-ENDPOINT-001",GateIdentity.ENDPOINT_SENSITIVITY,endpoint,frozen_at=3)]
def valid_registry(controlled=None,endpoint=None):
    return build_comparison_registry(tref(),valid_artifacts(controlled,endpoint))
def thermal_artifact(dynamic=True):
    if dynamic:
        content={"temperatures":temperatures(),"domains":domains(),"cth":{"junction":1,"case":2,"heatsink":3},"rth":{"junction":1,"case":1,"heatsink":1},"elapsed":1,"hot_start":True,"boundary_temperatures":{"ambient":25},"cooling_mode":"FORCED_AIR","applied_power":{"junction":3,"case":3,"heatsink":3},"integration_method":"EXPLICIT_EULER","step_control":{"step":1},"convergence_control":{"iterations":10},"error_control":{"absolute":0.01}}
        artifact=RegisteredArtifact.create("THERMAL-DYNAMIC-001","1","THERMAL_DYNAMIC_INPUT",content)
        return artifact,artifact_registry([artifact])
    body={"artifact_id":"THERMAL-STEADY-001","version":"1","owner":"InverterOwner","approval":"APPROVED","rth_network":{"junction":1},"boundary_temperatures":{"ambient":25},"cooling_mode":"FORCED_AIR","loss_model":"CONSTANT_TEST_POWER","supported_domains":{"junction":(-40,175)},"solver_method":"CLOSED_FORM","convergence_control":{"absolute":0.01},"error_control":{"absolute":0.01}}
    return {**body,"artifact_hash":content_hash(body)}

def publication_fixture():
    refs=[]
    for artifact_type,name in (("ATS","ATS-REF"),("EVIDENCE_CONFLICT","EVIDENCE-REF"),("DIGITAL_ORACLE","ORACLE-REF"),("ANALOG_STATUS","ANALOG-REF")):
        refs.append(RegisteredArtifact.create(name,"1",artifact_type,{"status":"VALIDATED"}))
    return refs
def residual_record(source_type="LEG_COMMAND_TICK_ASYMMETRY",owner="owner-1"):
    val=PhysicalField.value_of("waveform-1")
    return ResidualRecord("case",owner,source_type,None,("artifact","1","a"*64),val,PhysicalField.value_of(1),PhysicalField.value_of(0),PhysicalField.value_of(-1),PhysicalField.value_of(Fraction(1,10)),Fraction(1,100),Availability.PROVISIONAL)


class CanonicalAndMaterialTests(unittest.TestCase):
    def test_canonical_numbers_and_signed_zero(self):
        self.assertEqual(CanonicalNumber.rational(Fraction(2,4),"X","u").representation,("REDUCED_RATIONAL",1,2))
        self.assertEqual(CanonicalNumber.finite_float(-0.0,"X","u"),CanonicalNumber.finite_float(0.0,"X","u"))
        for bad in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError): CanonicalNumber.finite_float(bad,"X","u")

    def test_event_order_is_off_deadtime_on_device(self):
        events=canonical_events((CanonicalEvent(2,EventClass.ON,"A","ON",ORACLE_SOURCE_HASH),CanonicalEvent(2,EventClass.OFF,"Z","OFF",ORACLE_SOURCE_HASH),CanonicalEvent(2,EventClass.DEADTIME_EXPIRY,"B","ON",ORACLE_SOURCE_HASH),CanonicalEvent(2,EventClass.OFF,"A","OFF",ORACLE_SOURCE_HASH)))
        self.assertEqual([(e.event_class.value,e.device_id) for e in events],[('OFF','A'),('OFF','Z'),('DEADTIME_EXPIRY','B'),('ON','A')])

    def test_material_availability_freshness_product(self):
        unavailable=material_result(ExplicitAbsence(("x",),"missing"),Availability.UNAVAILABLE)
        provisional=material_result(1,Availability.PROVISIONAL,bound=2)
        self.assertEqual(derive_result([unavailable],2,direct_evidence_complete=True,local_conditions_satisfied=True).availability,Availability.UNAVAILABLE)
        self.assertEqual(derive_result([provisional],2,direct_evidence_complete=True,local_conditions_satisfied=True).availability,Availability.PROVISIONAL)
        with self.assertRaises(ValueError): material_result(ExplicitAbsence(("x",),"missing"),Availability.PROVISIONAL)

    def test_gate_authorization_matrix(self):
        complete=GateAuthorization(GateIdentity.CONTROLLED_THREEFOLD,"PROGRESS_TO_REALISTIC_COMPARISON",True)
        ineligible=GateAuthorization(GateIdentity.ENDPOINT_SENSITIVITY,"PROGRESS_TO_REALISTIC_COMPARISON",True,True)
        req=material_result(1)
        for expected,evidence,conditions in ((Availability.AVAILABLE,True,True),(Availability.PROVISIONAL,False,True),(Availability.UNAVAILABLE,True,False)):
            result=realistic_comparison_result(2,[req],evidence,conditions,[complete,ineligible])
            self.assertEqual(result.availability,expected)
        self.assertFalse(ineligible.completion_claim or ineligible.pass_claim or ineligible.success_claim)
        blocked=realistic_comparison_result(2,[req],True,True,[replace(ineligible,valid=False)])
        self.assertEqual(blocked.availability,Availability.UNAVAILABLE)
        unrelated=derive_result([req],3,direct_evidence_complete=True,local_conditions_satisfied=True,gate_authorizations=[replace(ineligible,valid=False)],operation="PROGRESS_TO_REALISTIC_COMPARISON",unrelated=True)
        self.assertEqual(unrelated.availability,Availability.AVAILABLE)

    def test_dependency_hash_change_stales_transitive_descendants(self):
        a=material_result(1,dependency_records={"source":"a"*64})
        b=material_result(2,dependencies=(a,),dependency_records={"a":"b"*64})
        stale=invalidate_transitively({"a":a,"b":b},"source")
        self.assertEqual(stale["a"].freshness,Freshness.STALE); self.assertEqual(stale["b"].freshness,Freshness.STALE)
        fresh=recompute_result(stale["b"],3,{"source":"c"*64})
        self.assertEqual(fresh.freshness,Freshness.FRESH); self.assertNotEqual(fresh.trace_identity,b.trace_identity)

    def test_property_5_dependency_status_generated(self):
        """**Validates: Requirements 2.5, 2.34, 2.41**"""
        for dep_status in Availability:
            dep=material_result(1,dep_status,bound=2 if dep_status is Availability.PROVISIONAL else None)
            got=derive_result([dep],2,direct_evidence_complete=True,local_conditions_satisfied=True).availability
            self.assertEqual(got,dep_status)

    def test_property_6_display_collisions_do_not_equal(self):
        """**Validates: Requirements 2.18, 2.35, 2.42**"""
        values=[Fraction(10001,10000),Fraction(10002,10000),Fraction(10003,10000)]
        self.assertEqual(len({format(float(v),'.3f') for v in values}),1)
        self.assertEqual(len({CanonicalNumber.rational(v,"POWER","W") for v in values}),3)


class EvidenceTests(unittest.TestCase):
    def test_evidence_catalog_exact_classes_and_pending(self):
        catalog=evidence_catalog(); target=catalog[0]
        self.assertEqual(target.subject,"IRL40SC209"); self.assertEqual(target.evidence_class,EvidenceClass.USER_SPECIFIED_TARGET)
        self.assertTrue(all(x.evidence_class is None and x.conflict_status is ConflictStatus.PENDING and x.subject=="IRL40T209" for x in catalog[1:3]))
        self.assertTrue(all(x.evidence_class is None and not x.selectable for x in catalog[1:]))

    def test_transition_graph_and_immutable_history(self):
        record=replace(evidence_catalog()[0],conflict_status=ConflictStatus.NONE)
        pending=record.transition(ConflictStatus.PENDING,"owner","2026-01-01T00:00:00Z","conflict",("art",))
        accepted=pending.transition(ConflictStatus.ACCEPTED_FOR_FIELD,"owner","2026-01-02T00:00:00Z","selected",("art",))
        superseded=accepted.transition(ConflictStatus.SUPERSEDED,"owner","2026-01-03T00:00:00Z","new evidence",("art2",))
        self.assertEqual(len(record.history),0); self.assertEqual(len(superseded.history),3)
        with self.assertRaises(ValueError): superseded.transition(ConflictStatus.PENDING,"x","t","r",("a",))

    def test_selection_cardinality(self):
        target=evidence_catalog()[0]
        self.assertIs(validate_selection([target],target.record_id),target)
        with self.assertRaises(ValueError): validate_selection([target],"missing")

    def test_properties_3_4_generated_metadata_and_transitions(self):
        """**Validates: Requirements 2.1-2.5**"""
        for record in evidence_catalog(): record.validate()
        for prior in ConflictStatus:
            for after in ConflictStatus:
                if (prior,after) in LEGAL_TRANSITIONS: continue
                base=replace(evidence_catalog()[0],conflict_status=prior)
                with self.assertRaises(ValueError): base.transition(after,"a","t","r",("x",))


class DigitalOracleTests(unittest.TestCase):
    def test_exact_compiled_semantics(self):
        v=digital_oracle(10)
        self.assertEqual((v.N,v.H,v.interval_lengths),(2285,1142,(1142,1143)))
        self.assertEqual(v.actual_carrier.fraction,Fraction(32_000_000,457)); self.assertEqual(v.period.fraction,Fraction(2285,160_000_000))
        self.assertEqual(v.q.fraction,Fraction(571,5)); self.assertEqual(v.k,114)
        self.assertEqual(tuple(x[1] for x in v.comparators),(1,1142,114,1256,1,106,1150,1248))
        self.assertEqual(len(v.raw_events.value),8); self.assertEqual(len(v.complete_aggregate_adjusted_events.value),16)

    def test_p1_p0_vectors_and_unavailable_sr(self):
        expected={1:((1,1142,11,1153,1,1,2284,2284),11,None),0:((1,1142,1,1142,1,1,2284,2284),0,"LEG_COMMAND_TICK_ASYMMETRY")}
        for p,(comparators,k,owner) in expected.items():
            v=digital_oracle(p); self.assertEqual(tuple(x[1] for x in v.comparators),comparators); self.assertEqual(v.k,k)
            self.assertEqual(len(v.raw_events.value),8); self.assertEqual(len(v.adjusted_lv_events.value),8); self.assertEqual(v.residual_owner,owner)
            tick=[e for e in v.raw_events.value if e.tick==2284]
            self.assertEqual([e.event_class for e in tick],[EventClass.OFF,EventClass.ON])
            for field in (v.suppressed_pulse,v.complete_adjusted_sr_events,v.complete_aggregate_adjusted_events):
                self.assertEqual(field.availability,Availability.UNAVAILABLE); self.assertTrue(field.safety_relevant and field.non_gating)

    def test_timing_mutations_rejected(self):
        for p in (10,1,0):
            expected=digital_oracle(p)
            mutations=[replace(expected,N=2286),replace(expected,H=1143),replace(expected,interval_lengths=(1143,1143)),replace(expected,k=expected.k+1)]
            if p==10: mutations.append(replace(expected,complete_aggregate_adjusted_events=TimingField.exact(expected.complete_aggregate_adjusted_events.value[:-1])))
            else:
                for bad in (TimingField.exact(()),TimingField.exact(0),TimingField(Availability.UNAVAILABLE,(),SR_UNAVAILABLE_REASON,True,True)):
                    mutations.append(replace(expected,complete_adjusted_sr_events=bad))
            for actual in mutations: self.assertEqual(validate_timing(actual,expected).availability,Availability.UNAVAILABLE)

    def test_property_7_one_field_oracle_mutations(self):
        """**Validates: Requirements 2.6-2.9, 2.36**"""
        v=digital_oracle(10)
        for name,value in (("N",2286),("H",1143),("actual_carrier",CanonicalNumber.rational(70000,"FREQUENCY","Hz")),("interval_lengths",(1143,1143))):
            self.assertEqual(validate_timing(replace(v,**{name:value}),v).availability,Availability.UNAVAILABLE)

    def test_property_8_analog_independence(self):
        """**Validates: Requirements 2.8, 2.9, 2.11, 2.12, 2.35**"""
        analog=analog_modref_unavailable(("transfer","current","energy","loss"))
        self.assertTrue(all(r.availability is Availability.UNAVAILABLE and r.non_gating for r in analog.values()))
        self.assertEqual(validate_timing(compute_timing_from_firmware(10),independent_expected_timing(10)).availability,Availability.AVAILABLE)


class ResidualSettlingTests(unittest.TestCase):
    def test_residual_matrix_complete_and_p0_owner(self):
        matrix=normative_residual_matrix(); matrix.validate(); self.assertEqual(len(matrix.rows),12)
        row=matrix.rows[("HF_LINK_PSFB","ZERO_SETTLED","DISABLED","DISABLED")]
        self.assertEqual(row["LEG_COMMAND_TICK_ASYMMETRY"][0],"REQUIRED")
        result=aggregate_residuals(("HF_LINK_PSFB","ZERO_SETTLED","DISABLED","DISABLED"),[residual_record()],matrix)
        self.assertEqual(result.availability,Availability.PROVISIONAL)

    def test_missing_duplicate_forbidden_and_uncertainty_not_loss(self):
        case=("HF_LINK_PSFB","ZERO_SETTLED","DISABLED","DISABLED")
        self.assertEqual(aggregate_residuals(case,[]).availability,Availability.UNAVAILABLE)
        self.assertIn("RESIDUAL_OWNER_DUPLICATE",aggregate_residuals(case,[residual_record(),residual_record()]).diagnostics)
        forbidden=residual_record("SR_COMMUTATION","owner-2")
        self.assertIn("FORBIDDEN_RESIDUAL_SOURCE",aggregate_residuals(case,[residual_record(),forbidden]).diagnostics)
        got=aggregate_residuals(case,[replace(residual_record(),uncertainty_or_bound=1000)])
        self.assertEqual(got.canonical_value.fraction,Fraction(1,10))

    def test_settling_absent_exceeded_pass(self):
        period=Fraction(2285,160_000_000); ats=normative_ats()
        state,result=classify_settling(caller_settled=None,ats=ats,thresholds=None,period=period,observations=None)
        self.assertEqual(state,"TRANSITION"); self.assertEqual(result.availability,Availability.UNAVAILABLE); self.assertTrue(result.non_gating)
        thresholds=make_test_thresholds(period)
        base={"window_seconds":thresholds.W_seconds,"ires_rms":0,"vs_per_period":[0],"vs_cumulative":0,"end_energy":0,"energy_sources":thresholds.closed_energy_sources}
        self.assertEqual(classify_settling(caller_settled=None,ats=ats,thresholds=thresholds,period=period,observations=base)[0],"SETTLED")
        failed={**base,"ires_rms":1}
        state,result=classify_settling(caller_settled=None,ats=ats,thresholds=thresholds,period=period,observations=failed)
        self.assertEqual(state,"TRANSITION"); self.assertEqual(result.availability,Availability.AVAILABLE)

    def test_all_no_load_categories_and_loaded_constants(self):
        residual=aggregate_residuals(("HF_LINK_PSFB","ZERO_SETTLED","DISABLED","DISABLED"),[residual_record()])
        period=Fraction(2285,160_000_000)
        _,decision=classify_settling(caller_settled=None,ats=normative_ats(),thresholds=None,period=period,observations=None)
        report=no_load_report(decision,0,1,residual,None)
        self.assertEqual({r.canonical_value["category"] for r in report},set(NO_LOAD_CATEGORIES)); self.assertEqual(len(report),8)
        self.assertTrue(all(isinstance(r,MaterialResult) for r in report))
        nonzero=no_load_report(decision,10,1,residual,None)
        ideal=next(r for r in nonzero if r.canonical_value["category"]=="INTENTIONAL_IDEAL_DIFFERENTIAL_TRANSFER")
        self.assertEqual(ideal.availability,Availability.UNAVAILABLE)
        fake=material_result({"decision_type":"SETTLEMENT_DECISION","state":"SETTLED","passed":True})
        with self.assertRaises(ValueError): no_load_report(fake,0,1,residual,None)
        for x in (36.0,42.8): self.assertEqual(reject_loaded_constant_no_load(x,"LOADED","NO_LOAD").availability,Availability.UNAVAILABLE)

    def test_properties_9_10_11_19(self):
        """**Validates: Requirements 2.10-2.12, 2.32, 2.33, 2.35-2.37**"""
        self.assertEqual(digital_oracle(0).residual_owner,"LEG_COMMAND_TICK_ASYMMETRY")
        self.assertEqual(digital_oracle(0).complete_aggregate_adjusted_events.availability,Availability.UNAVAILABLE)
        for gate,sr in product(("ENABLED","DISABLED"),repeat=2):
            row=normative_residual_matrix().rows[("HF_LINK_PSFB","ZERO_TRANSITION",gate,sr)]
            self.assertEqual(set(row),set(RESIDUAL_TYPES))


class BoundaryThermalTests(unittest.TestCase):
    def make_input(self):
        return InverterInput(CanonicalNumber.rational(48,"VOLTAGE","V"),CanonicalNumber.rational(10,"CURRENT","A"),CanonicalNumber.rational(10,"PERCENT","percent"),1,CanonicalNumber.rational(Fraction(3,5),"RESISTANCE","mOhm"),2,CanonicalNumber.rational(75,"TEMPERATURE","degC"),CanonicalNumber.rational(10,"CURRENT","A"))

    def test_boundary_partition_and_excluded_mutation(self):
        inv=boundary_inventory(); inv.validate()
        inp=self.make_input()
        system={"inverter":{"dc_terminal":{"voltage":inp.dc_voltage,"current":inp.dc_current},"control":{"phase_percent":inp.phase_percent,"polarity":inp.polarity},"component":{"rds_on":inp.rds_on,"parallel_count":inp.parallel_count},"thermal":{"junction_temperature":inp.junction_temperature},"output":{"load_current":inp.load_current_rms}},
                "battery":{"cells":6,"internal_resistance":0.01},"upstream":{"pack_interconnect":0.001,"bms":"A"},"charger":{"efficiency":0.9},"system":{"c_rate":1,"round_trip_efficiency":0.8}}
        baseline=solve_system_inverter(system); frozen_inverter=canonical_json(system["inverter"])
        locations={"battery.cells":("battery","cells"),"battery.internal_resistance":("battery","internal_resistance"),"upstream.pack_interconnect":("upstream","pack_interconnect"),"upstream.bms":("upstream","bms"),"charger.efficiency":("charger","efficiency"),"system.c_rate":("system","c_rate"),"system.round_trip_efficiency":("system","round_trip_efficiency")}
        for path in sorted(inv.excluded_paths):
            for value in (1,2):
                mutated=copy.deepcopy(system); parent,key=locations[path]; mutated[parent][key]=value
                self.assertEqual(canonical_json(mutated["inverter"]),frozen_inverter)
                got=solve_system_inverter(mutated)
                self.assertEqual((got.canonical_value,got.availability,got.trace_identity,got.dependency_record_ids),(baseline.canonical_value,baseline.availability,baseline.trace_identity,baseline.dependency_record_ids))

    def test_scenario_boundary_closed_tuple(self):
        a={k:k for k in SCENARIO_FIELDS}; self.assertEqual(compare_scenario_boundaries(a,dict(a)).availability,Availability.AVAILABLE)
        b=dict(a); b["pass_count"]="two"; self.assertEqual(compare_scenario_boundaries(a,b).availability,Availability.UNAVAILABLE)

    def test_thermal_modes(self):
        self.assertEqual(cold_snapshot(temperatures(),domains()).canonical_value["mode"],"COLD_T0")
        missing=dict(temperatures()); missing.pop("coolant"); self.assertEqual(cold_snapshot(missing,domains()).availability,Availability.UNAVAILABLE)
        method,registry=thermal_artifact(True)
        transient=thermal_transient(temperatures(),domains(),{"junction":1,"case":2,"heatsink":3},{"junction":1,"case":1,"heatsink":1},1,method.ref,hot_start=True,registry=registry)
        self.assertEqual(transient.canonical_value["mode"],"HOT_START_TRANSIENT")
        # Caller-supplied physical values may not disagree with the registered artifact.
        self.assertEqual(thermal_transient(temperatures(),domains(),{"junction":999,"case":999,"heatsink":999},{"junction":999,"case":999,"heatsink":999},1,method.ref,hot_start=True,registry=registry).availability,Availability.UNAVAILABLE)
        self.assertEqual(thermal_transient(temperatures(),domains(),{"junction":1,"case":2,"heatsink":3},{"junction":1,"case":1,"heatsink":1},1,method.ref,hot_start=True).availability,Availability.UNAVAILABLE)
        steady_method=thermal_artifact(False)
        steady1=steady_state({"junction":1},{"ambient":25},10,domains(),steady_method,{"junction":1})
        steady2=steady_state({"junction":1},{"ambient":25},10,domains(),steady_method,{"junction":999})
        self.assertEqual((steady1.canonical_value,steady1.trace_identity,steady1.dependency_record_ids),(steady2.canonical_value,steady2.trace_identity,steady2.dependency_record_ids))

    def test_seeds_and_uniqueness(self):
        seeds=thermal_seeds((0,0),(100,100)); self.assertEqual(seeds,((0,0),(50.0,50.0),(100,100)))
        agreement=classify_multi_seed(seeds,((50,50),(50.05,49.95),(50,50)),(0.001,0.001,0.001),10,normative_ats())
        self.assertEqual(agreement.canonical_value["status"],"MULTI_SEED_AGREEMENT")
        self.assertEqual(verify_root_certificate(None,None).canonical_value,"UNPROVEN")

    def test_properties_12_13_14(self):
        """**Validates: Requirements 2.17-2.24, 3.8**"""
        inv=boundary_inventory(); self.assertEqual(len(inv.allowed_paths|inv.excluded_paths),len(SYSTEM_SCHEMA_PATHS))
        expected=None
        for cth in (0.1,1,100):
            got=steady_state({"junction":1},{"ambient":25},10,domains(),thermal_artifact(False),{"junction":cth})
            if expected is None: expected=(got.canonical_value,got.trace_identity,got.dependency_record_ids)
            self.assertEqual((got.canonical_value,got.trace_identity,got.dependency_record_ids),expected)


class ComparisonTests(unittest.TestCase):
    def test_controlled_completed_and_three_iff_rows(self):
        completed=controlled_threefold(10,True,Fraction(3,5),2); self.assertEqual(completed["kind"],"COMPLETED")
        auth,diag=validate_comparison_registry(valid_registry(completed,None)); self.assertFalse(diag); self.assertTrue(all(a.valid for a in auth))
        rows=[(0,True,"INELIGIBLE_ZERO_IRMS"),(1,False,"INELIGIBLE_EMPTY_CONDUCTION_INTERVAL"),(0,False,"INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL")]
        for current,conducts,code in rows:
            result=controlled_threefold(current,conducts,Fraction(3,5),2); self.assertEqual(result["canonical_code"],code)
            self.assertEqual(result["evaluated_case_count"],0); self.assertFalse(any(result[k] for k in FALSE_CLAIM_KEYS))
        self.assertEqual(controlled_threefold(-1,True,Fraction(3,5),2)["kind"],"UNRESOLVED")

    def test_endpoint_completed_ineligible_and_invalid(self):
        low=CanonicalNumber.rational(1,"RESISTANCE","mOhm"); high=CanonicalNumber.rational(2,"RESISTANCE","mOhm"); ats=normative_ats()
        complete=endpoint_sensitivity([{"candidate_id":"a","current":1.0,"conduction_nonempty":True}],low,high,endpoint_evidence=True,policy=ats,fixed_inputs=True,closed_immutable_set=True)
        self.assertEqual(complete["kind"],"COMPLETED")
        no_case=endpoint_sensitivity([{"candidate_id":"a","current":0.0,"conduction_nonempty":False}],low,high,endpoint_evidence=True,policy=ats,fixed_inputs=True,closed_immutable_set=True)
        self.assertEqual(no_case["canonical_code"],ENDPOINT_CODE); self.assertEqual(no_case["evaluated_case_count"],0)
        invalid=endpoint_sensitivity([],low,high,endpoint_evidence=False,policy=ats,fixed_inputs=True,closed_immutable_set=True)
        self.assertEqual(invalid["kind"],"UNRESOLVED")

    def test_registry_valid_ineligibility_authorizes_without_claims(self):
        controlled=controlled_threefold(0,True,Fraction(3,5),2)
        endpoint=endpoint_sensitivity([{"candidate_id":"a","current":0.0,"conduction_nonempty":False}],CanonicalNumber.rational(1,"RESISTANCE","mOhm"),CanonicalNumber.rational(2,"RESISTANCE","mOhm"),endpoint_evidence=True,policy=normative_ats(),fixed_inputs=True,closed_immutable_set=True)
        artifacts=valid_artifacts(controlled,endpoint); registry=build_comparison_registry(tref(),artifacts); auth,diag=validate_comparison_registry(registry)
        self.assertFalse(diag); self.assertTrue(all(a.authorizes("PROGRESS_TO_REALISTIC_COMPARISON") for a in auth)); self.assertTrue(all(a.permitted_ineligibility for a in auth))
        original=copy.deepcopy(artifacts)
        outputs=[realistic_comparison_result(1,[material_result(1)],e,c,auth).availability for e,c in ((True,True),(False,True),(True,False))]
        self.assertEqual(outputs,[Availability.AVAILABLE,Availability.PROVISIONAL,Availability.UNAVAILABLE]); self.assertEqual(artifacts,original)

    def test_registry_rejects_every_structural_bypass(self):
        base=valid_artifacts()
        mutations=[[],base[:1],base+[copy.deepcopy(base[0])]]
        alias=copy.deepcopy(base); alias[1]["artifact_id"]=alias[0]["artifact_id"]; alias[1]["artifact_hash"]=content_hash({k:v for k,v in alias[1].items() if k!="artifact_hash"}); mutations.append(alias)
        late=copy.deepcopy(base); late[0]["frozen_before_realistic_execution"]=False; mutations.append(late)
        multi=copy.deepcopy(base); multi[0]["outcomes"].append(copy.deepcopy(multi[0]["outcomes"][0])); multi[0]["artifact_hash"]=content_hash({k:v for k,v in multi[0].items() if k!="artifact_hash"}); mutations.append(multi)
        badcode=valid_artifacts(controlled_threefold(0,True,Fraction(3,5),2)); badcode[0]["outcomes"][0]["canonical_code"]="INELIGIBLE"; badcode[0]["artifact_hash"]=content_hash({k:v for k,v in badcode[0].items() if k!="artifact_hash"}); mutations.append(badcode)
        for artifacts in mutations:
            auth,diag=validate_comparison_registry(build_comparison_registry(tref(),artifacts)); self.assertTrue(diag); self.assertTrue(all(not a.valid for a in auth))
            dependent=realistic_comparison_result(1,[material_result(1)],True,True,auth); self.assertEqual(dependent.availability,Availability.UNAVAILABLE)

    def test_comparison_prerequisites_resolve_registered_complete_content(self):
        controlled=controlled_threefold(0,True,Fraction(3,5),2)
        endpoint=endpoint_sensitivity([{"candidate_id":"a","current":0.0,"conduction_nonempty":False}],CanonicalNumber.rational(1,"RESISTANCE","mOhm"),CanonicalNumber.rational(2,"RESISTANCE","mOhm"),endpoint_evidence=True,policy=normative_ats(),fixed_inputs=True,closed_immutable_set=True)
        artifacts=valid_artifacts(controlled,endpoint)
        # Review probe 1: strip every controlled prerequisite except current/conduction.
        original=controlled["_registered_prerequisite"]
        stripped=RegisteredArtifact.create("STRIPPED","1","CONTROLLED_PREREQUISITES",{"irms_bits":original.content["irms_bits"],"conduction_nonempty":True})
        bad_controlled=copy.deepcopy(controlled); bad_controlled["prerequisite_ref"]=stripped.ref; bad_controlled["_registered_prerequisite"]=stripped
        bad_artifacts=valid_artifacts(bad_controlled,endpoint)
        auth,diag=validate_comparison_registry(build_comparison_registry(tref(),bad_artifacts))
        self.assertIn("CONTROLLED_INELIGIBILITY_PREREQUISITE_INVALID",diag); self.assertTrue(all(not a.valid for a in auth))
        # Review probe 2: endpoint reference points to unrelated registered content.
        unrelated=RegisteredArtifact.create("UNRELATED","1","CONTROLLED_PREREQUISITES",original.content)
        bad_endpoint=copy.deepcopy(endpoint); bad_endpoint["prerequisite_ref"]=unrelated.ref; bad_endpoint["_registered_prerequisite"]=unrelated
        auth,diag=validate_comparison_registry(build_comparison_registry(tref(),valid_artifacts(controlled,bad_endpoint)))
        self.assertIn("ENDPOINT_EVIDENCE_OR_POLICY_INVALID",diag); self.assertTrue(all(not a.valid for a in auth))

    def test_tref_failures_and_reconciliation(self):
        for mutation in ({"unit":""},{"value":math.inf},{"baseline_domain":[80,100]}):
            t=tref(); t.update(mutation); t["artifact_hash"]=content_hash({k:v for k,v in t.items() if k!="artifact_hash"}); auth,diag=validate_comparison_registry(build_comparison_registry(t,valid_artifacts())); self.assertIn("COMPARISON_TREF_INVALID_OR_LATE",diag)
        late=build_comparison_registry(tref(),valid_artifacts(),realistic_execution_at=2); self.assertIn("COMPARISON_TREF_INVALID_OR_LATE",validate_comparison_registry(late)[1])
        got=reconcile_comparison({"CHANNEL":Fraction(-2)},{"CHANNEL":Fraction(1)},Fraction(-1),normative_ats()); self.assertTrue(got.canonical_value["reconciled"])

    def test_property_15_generated_code_predicate_cross(self):
        """**Validates: Requirements 2.25, 2.26, 2.29-2.31, 2.38, 3.11**"""
        for current,conducts,correct in ((0,True,"INELIGIBLE_ZERO_IRMS"),(1,False,"INELIGIBLE_EMPTY_CONDUCTION_INTERVAL"),(0,False,"INELIGIBLE_ZERO_IRMS_AND_EMPTY_CONDUCTION_INTERVAL")):
            for code in (*CONTROLLED_CODES,"INELIGIBLE","INELIGIBLE_NO_POSITIVE_CURRENT_CASE"):
                outcome=controlled_threefold(current,conducts,Fraction(3,5),2); outcome["canonical_code"]=code
                artifact=frozen_gate_artifact("C",GateIdentity.CONTROLLED_THREEFOLD,outcome)
                endpoint=valid_artifacts()[1]
                registry=build_comparison_registry(tref(),[artifact,endpoint])
                auth,diag=validate_comparison_registry(registry)
                self.assertEqual(not diag,code==correct)


class QualificationControlPublicationTests(unittest.TestCase):
    def test_synthetic_and_incomplete_48v(self):
        synthetic={"synthetic_marker":True,"nodes":[{"synthetic_marker":True}]}
        self.assertEqual(qualification_result(synthetic,real_claim=True).availability,Availability.UNAVAILABLE)
        incomplete={"synthetic_marker":False,"exact_device":"IRL40SC209","limits":{},"dc_voltage":48}
        result=qualification_result(incomplete,real_claim=True); self.assertEqual(result.availability,Availability.UNAVAILABLE); self.assertTrue(result.non_gating)
        mixed={"synthetic_marker":True,"nodes":[{"synthetic_marker":False}]}; self.assertIn("SYNTHETIC_REAL_MIX",qualification_result(mixed,real_claim=False).diagnostics)

    def test_control_axes_all_products_independent(self):
        fw_source=RegisteredArtifact.create("FW-SOURCE","1","FIRMWARE_CONTROL_SOURCE",{"source_paths":["firmware/main/pwm.c"],"config_hash":content_hash("config"),"requirement_code_trace":{"R2.27":"pwm.c"},"build_hash":content_hash("build")})
        fw_test=RegisteredArtifact.create("FW-TEST","1","FIRMWARE_CONTROL_TEST",{"requirement":"R2.27","deterministic":True,"complete_requirement_exercised":True,"passed":True})
        hw_test=RegisteredArtifact.create("HW-TEST","1","HARDWARE_CONTROL_TEST",{"exact_hardware_identity":"prototype-001","firmware_config_hash":content_hash("config"),"instruments_calibration":{"scope":"CAL-1"},"conditions":{"dc_voltage":24},"waveform_coverage":{"seconds":1},"limits":{"phase":1},"requirement":"R2.27","passed":True})
        registry=artifact_registry([fw_source,fw_test,hw_test])
        firmware_ok={"source_config_ref":fw_source.ref,"deterministic_test_ref":fw_test.ref}
        hardware_ok={"test_ref":hw_test.ref}
        for fw,hw in product((None,firmware_ok), (None,hardware_ok)):
            result=control_evidence(fw,hw,registry)
            self.assertEqual(result["firmware_implementation_status"].canonical_value,ControlStatus.UNAVAILABLE.value if fw is None else ControlStatus.VERIFIED.value)
            self.assertEqual(result["hardware_measurement_status"].canonical_value,ControlStatus.UNAVAILABLE.value if hw is None else ControlStatus.VERIFIED.value)
        empty=RegisteredArtifact.create("FW-EMPTY","1","FIRMWARE_CONTROL_SOURCE",{"source_paths":[],"config_hash":"","requirement_code_trace":{},"build_hash":""})
        bad_registry=artifact_registry([empty,fw_test])
        self.assertEqual(control_axis_status("firmware",{"source_config_ref":empty.ref,"deterministic_test_ref":fw_test.ref},bad_registry).availability,Availability.UNAVAILABLE)

    def test_publication_accept_reject(self):
        refs=publication_fixture()
        ref_by_type={r.artifact_type:r for r in refs}
        firmware_status=material_result(ControlStatus.UNAVAILABLE.value,Availability.UNAVAILABLE,non_gating=True,suffix="publication-fw")
        hardware_status=material_result(ControlStatus.UNAVAILABLE.value,Availability.UNAVAILABLE,non_gating=True,suffix="publication-hw")
        context_content={"boundary":"INVERTER","assumption_variant":"TARGET_060","ats_ref":ref_by_type["ATS"].ref,"evidence_conflict_ref":ref_by_type["EVIDENCE_CONFLICT"].ref,"digital_oracle_ref":ref_by_type["DIGITAL_ORACLE"].ref,"analog_status_ref":ref_by_type["ANALOG_STATUS"].ref,"thermal_case":"COLD_T0","firmware_status_result_id":"firmware-status","hardware_status_result_id":"hardware-status","result_basis":"CALCULATED_ESTIMATE","uncertainty_or_bound":{"absolute":"1/100 W"},"synthetic_marker":False}
        context=RegisteredArtifact.create("PUB-CONTEXT","1","PUBLICATION_CONTEXT",context_content)
        records={r.artifact_id:r.artifact_hash for r in (*refs,context)}
        records.update({"firmware-status":firmware_status.computation_artifact_hash,"hardware-status":hardware_status.computation_artifact_hash})
        base=material_result(CanonicalNumber.rational(1,"POWER","W"),dependency_records=records)
        registry=artifact_registry([*refs,context],{"firmware-status":firmware_status,"hardware-status":hardware_status,"result":base})
        claim={"boundary":"INVERTER","assumption_variant":"TARGET_060","ats":ref_by_type["ATS"].ref,"evidence_conflict":ref_by_type["EVIDENCE_CONFLICT"].ref,"digital_oracle":ref_by_type["DIGITAL_ORACLE"].ref,"analog_status":ref_by_type["ANALOG_STATUS"].ref,"thermal_case":"COLD_T0","firmware_implementation_status":"UNAVAILABLE","hardware_measurement_status":"UNAVAILABLE","result_basis":"CALCULATED_ESTIMATE","availability":base.availability.value,"freshness":base.freshness.value,"trace_identity":base.trace_identity,"dependency_set":base.dependency_record_ids,"uncertainty_or_bound":{"absolute":"1/100 W"},"synthetic_marker":False,"canonical_value":base.canonical_value,"publication_context_ref":context.ref}
        self.assertNotEqual(publish(claim,base,registry=registry,result_id="result").availability,Availability.UNAVAILABLE)
        for field,value in (("boundary","INVENTED"),("ats",{"artifact_id":"fake","version":"1","hash":content_hash("fake")}),("result_basis","")):
            bad={**claim,field:value}; self.assertEqual(publish(bad,base,registry=registry,result_id="result").availability,Availability.UNAVAILABLE)
        stale=replace(base,freshness=Freshness.STALE)
        stale_registry=object.__new__(ArtifactRegistry); object.__setattr__(stale_registry,"artifacts",registry.artifacts); object.__setattr__(stale_registry,"dependencies",registry.dependencies); object.__setattr__(stale_registry,"results",{"result":stale})
        self.assertEqual(publish(claim,stale,registry=stale_registry,result_id="result").availability,Availability.UNAVAILABLE)

    def test_properties_16_17_20(self):
        """**Validates: Requirements 2.15, 2.16, 2.27, 2.28, 2.34, 2.39, 2.41, 2.42**"""
        for synthetic,real in product((False,True),repeat=2):
            graph={"synthetic_marker":synthetic,"nodes":[{"synthetic_marker":synthetic}]}
            result=qualification_result(graph,real_claim=real)
            if synthetic and real: self.assertEqual(result.availability,Availability.UNAVAILABLE)
        self.assertNotEqual(control_evidence({},None)["firmware_implementation_status"].trace_identity,control_evidence(None,{})["hardware_measurement_status"].trace_identity)


class FirmwareAndIntegrationTests(unittest.TestCase):
    def test_firmware_manifest_exact_equality_and_mutations(self):
        import json
        baseline=json.loads((CALC/"inverter_corrections_baseline.json").read_text())["firmware_before"]
        after=firmware_manifest_current(baseline["entries"])
        result=verify_firmware_unchanged(baseline,after,baseline["named_git_commit"],baseline["git_tree_hash"])
        self.assertTrue(result.canonical_value["equal"])
        for mutation in ("content","remove","add"):
            bad=dict(after)
            if mutation=="content": bad[next(iter(bad))]="0"*64
            elif mutation=="remove": bad.pop(next(iter(bad)))
            else: bad["firmware/new.c"]="0"*64
            self.assertEqual(verify_firmware_unchanged(baseline,bad,baseline["named_git_commit"],baseline["git_tree_hash"]).availability,Availability.UNAVAILABLE)

    def test_property_18_firmware_immutable(self):
        """**Validates: Requirements 2.40**"""
        self.test_firmware_manifest_exact_equality_and_mutations()

    def test_end_to_end_conservative_pipeline(self):
        target=evidence_catalog()[0]; self.assertEqual(target.evidence_class,EvidenceClass.USER_SPECIFIED_TARGET)
        timing=validate_timing(compute_timing_from_firmware(0),independent_expected_timing(0)); self.assertEqual(timing.availability,Availability.AVAILABLE)
        controlled=controlled_threefold(0,True,Fraction(3,5),2)
        endpoint=endpoint_sensitivity([{"candidate_id":"zero","current":0.0,"conduction_nonempty":False}],CanonicalNumber.rational(1,"RESISTANCE","mOhm"),CanonicalNumber.rational(2,"RESISTANCE","mOhm"),endpoint_evidence=True,policy=normative_ats(),fixed_inputs=True,closed_immutable_set=True)
        auth,diag=validate_comparison_registry(build_comparison_registry(tref(),valid_artifacts(controlled,endpoint))); self.assertFalse(diag)
        realistic=realistic_comparison_result({"delta":"bounded"},[timing],False,True,auth); self.assertEqual(realistic.availability,Availability.PROVISIONAL)
        self.assertFalse(any(controlled[k] for k in FALSE_CLAIM_KEYS)); self.assertFalse(any(endpoint[k] for k in FALSE_CLAIM_KEYS))


class StrengthenedBypassTests(unittest.TestCase):
    def test_placeholder_related_part_cannot_be_classified(self):
        bad=EvidenceRecord("x","IRL40T209","IRL40SC209","RDS_ON",CanonicalNumber.rational(1,"RESISTANCE","mOhm"),"mOhm",EvidenceClass.RELATED_PART,ConflictStatus.NONE,
                           {"manufacturer":"Infineon","document_id":"MISSING_EXTERNAL_DOCUMENT_ID","document_version":"NOT_STATED_BY_SOURCE","artifact_hash":content_hash("placeholder"),"locator":"legacy repository statement only","rating_class":"MAXIMUM","source_conditions":{n:"NOT_STATED_BY_SOURCE" for n in ("VGS","ID","Tj_or_Tc","pulse_or_measurement")},"relationship_rationale":"same die"},"test")
        with self.assertRaises(ValueError): bad.validate()

    def test_minimal_fabricated_completed_outcomes_rejected(self):
        fabricated={"kind":"COMPLETED","requirement":"2.29","valid":True}
        artifacts=valid_artifacts(); artifacts[0]=frozen_gate_artifact("C",GateIdentity.CONTROLLED_THREEFOLD,fabricated)
        auth,diag=validate_comparison_registry(build_comparison_registry(tref(),artifacts))
        self.assertIn("COMPARISON_GATE_COMPLETED_RESULT_INVALID",diag); self.assertTrue(all(not a.valid for a in auth))
        forged=valid_artifacts(); forged[0]["outcomes"][0]["replacement_channel_loss"]="999"; forged[0]["artifact_hash"]=content_hash({k:v for k,v in forged[0].items() if k not in {"artifact_hash","_registered_prerequisite"}})
        self.assertIn("COMPARISON_GATE_COMPLETED_RESULT_INVALID",validate_comparison_registry(build_comparison_registry(tref(),forged))[1])

    def test_thermal_fake_uniqueness_and_missing_power_rejected(self):
        self.assertEqual(verify_root_certificate({"root_count":1},{"root_count":1}).canonical_value,"UNPROVEN")
        method,registry=thermal_artifact(True)
        got=thermal_transient(temperatures(),domains(),{"junction":999,"case":999,"heatsink":999},{"junction":999,"case":999,"heatsink":999},1,method.ref,hot_start=True,registry=registry)
        self.assertEqual(got.availability,Availability.UNAVAILABLE)

    def test_qualification_control_and_publication_direct_bypasses(self):
        fake_limit={n:{"value":1,"unit":"V","rating_class":"MAX","applicability":"all","pass_rule":"<=","artifact":{"artifact_id":"x","version":"1","hash":"fake"},"locator":"x","source_conditions":{},"observed":0,"passed":True} for n in QUALIFICATION_LIMITS}
        graph={"synthetic_marker":False,"nodes":[],"exact_device":"IRL40SC209","limits":fake_limit,"stress":{},"dc_voltage":48,"derating_rule":"x","operating_conditions":"x"}
        self.assertEqual(qualification_result(graph,real_claim=True).availability,Availability.UNAVAILABLE)
        self.assertEqual(control_axis_status("firmware",{"source_config_artifact":"anything"}).availability,Availability.UNAVAILABLE)
        source_hash=content_hash("evidence")
        source=material_result(CanonicalNumber.rational(1,"POWER","W"),dependency_records={"evidence":source_hash})
        registry=ArtifactRegistry({"evidence":source_hash},{"result":("evidence",)},{"result":source})
        claim={k:"present" for k in PUBLICATION_FIELDS}; claim.update({"availability":source.availability.value,"freshness":source.freshness.value,"trace_identity":source.trace_identity,"dependency_set":source.dependency_record_ids,"canonical_value":source.canonical_value,"synthetic_marker":False})
        changed=registry.select_transaction("evidence",content_hash("changed-evidence"))
        self.assertEqual(publish(claim,source,registry=changed,result_id="result").availability,Availability.UNAVAILABLE)

    def test_registry_transaction_stales_all_descendants_before_consumption(self):
        ehash=content_hash("e")
        a=material_result(1,dependency_records={"e":ehash})
        b=material_result(2,dependency_records={"a":a.computation_artifact_hash})
        c=material_result(3,dependency_records={"b":b.computation_artifact_hash})
        registry=ArtifactRegistry({"e":ehash},{"a":("e",),"b":("a",),"c":("b",)},{"a":a,"b":b,"c":c})
        changed=registry.select_transaction("e",content_hash("changed-e"))
        self.assertTrue(all(changed.results[n].freshness is Freshness.STALE for n in ("a","b","c")))
        self.assertEqual(consume_registered(changed,"c").availability,Availability.UNAVAILABLE)
        with self.assertRaises(ValueError): ArtifactRegistry({"e":ehash},{},{"a":a,"b":b,"c":c})
        with self.assertRaises(ValueError): ArtifactRegistry({"e":ehash},{"a":("e",),"b":("a","e"),"c":("b",)},{"a":a,"b":b,"c":c})


if __name__ == "__main__": unittest.main(verbosity=2)
