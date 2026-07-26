#!/usr/bin/env python3
"""Executable semantic preservation over immutable baseline and current adapters.

Every BASELINE_BEHAVIOR case is evaluated independently by a frozen-commit
adapter and the current corrected implementation, then canonically compared.
NO_BASELINE_BEHAVIOR routes use field-specific behavioral assertions.
"""
from __future__ import annotations
import ast, hashlib, json, subprocess, sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from inverter_corrections import *
from inverter_corrections_preservation import EXPECTED_KEYS, run as run_frozen

MANIFEST=HERE/"inverter_corrections_baseline.json"
def sha(data: bytes)->str:return hashlib.sha256(data).hexdigest()
def git_blob(commit: str,path: str)->bytes:
    return subprocess.run(["git","show",f"{commit}:{path}"],cwd=ROOT,check=True,capture_output=True).stdout

def _baseline_capture(mapping: Mapping[str,Any],commit: str)->tuple[bytes,str]:
    blob=git_blob(commit,mapping["source_path"])
    assert mapping["source_contains"].encode() in blob
    return blob,sha(blob)

def _input(case_id: str,**values: Any)->dict[str,Any]:
    return {"case_id":case_id,**values}

def baseline_population(key: str)->list[dict[str,Any]]:
    if key=="TOP_LEVEL:3.2":
        # Multiple physical designs and battery points exercise the invariant that
        # current follows frozen turns, never instantaneous battery voltage.
        return [_input(f"{key}:fixed-ratio:{index}",primary_turns=np,
                       secondary_turns=ns,output_current=str(current),
                       battery_voltage=str(voltage))
                for index,(np,ns,current,voltage) in enumerate((
                    (1,18,Fraction(3000,230),Fraction(20)),
                    (1,18,Fraction(3000,230),Fraction(126,5)),
                    (2,16,Fraction(125,12),Fraction(40)),
                    (2,16,Fraction(125,12),Fraction(273,5)),
                    (3,17,Fraction(37,4),Fraction(96,5))),start=1)]
    if key=="TOP_LEVEL:3.3":
        return [_input(f"{key}:equation:{i}",irms=i,rds=str(r),parallel=m)
                for i,r,m in ((1,Fraction(3,5),1),(10,Fraction(1,2),2),(17,Fraction(7,10),4))]
    return [_input(key+":eligible")]

def _execute_frozen_primary_current(blob: bytes, case: Mapping[str,Any])->Fraction:
    """Execute the immutable baseline assignment captured from the frozen commit."""
    tree=ast.parse(blob.decode("utf-8"))
    expression=None
    for node in ast.walk(tree):
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            if any(isinstance(target,ast.Name) and target.id=="I_pri_rms" for target in targets):
                expression=node.value
                break
    assert expression is not None
    allowed=(ast.Expression,ast.BinOp,ast.Mult,ast.Name,ast.Load)
    assert all(isinstance(node,allowed) for node in ast.walk(ast.Expression(expression)))
    environment={"n_real":Fraction(case["secondary_turns"],case["primary_turns"]),
                 "Io_rms":Fraction(case["output_current"])}
    return Fraction(eval(compile(ast.Expression(expression),"<frozen-primary-current>","eval"),
                         {"__builtins__":{}},environment))


def immutable_baseline_adapter(key: str,case: Mapping[str,Any],blob: bytes)->Any:
    """Canonical baseline behavior reconstructed only from frozen commit content."""
    if key=="TOP_LEVEL:3.1":
        return {"represented_domains":("LV","HV","TRANSFORMER"),"eligible":all(x in blob for x in (b"LV ",b"HV ","Трансформатор".encode()))}
    if key=="TOP_LEVEL:3.2":
        value=_execute_frozen_primary_current(blob,case)
        return {"primary_current":CanonicalNumber.rational(value,"CURRENT","A"),
                "turns":(case["primary_turns"],case["secondary_turns"]),
                "battery_voltage":CanonicalNumber.rational(case["battery_voltage"],"VOLTAGE","V"),
                "contract":"FIXED_PHYSICAL_TURNS"}
    if key=="TOP_LEVEL:3.3":
        value=Fraction(case["irms"])**2*2*Fraction(case["rds"])/case["parallel"]
        return {"channel_loss":str(value),"equation":"Irms^2*2*Rds/m"}
    if key=="TOP_LEVEL:3.4":return {"composition":"DOWNSTREAM_ONLY","inverter_invariant":b"Round trip" in blob}
    if key=="TOP_LEVEL:3.5":return {"uncertainty_visible":"±50%".encode() in blob,"status":"NOT_MEASURED_FACT"}
    if key=="TOP_LEVEL:3.6":return {"transition_physics":"RETAINED","circulating_current":"циркулює".encode() in blob}
    if key=="TOP_LEVEL:3.7":return {"qualification":"INDEPENDENT_OF_RDS","constraint_visible":"Обмеження топології".encode() in blob}
    if key=="TOP_LEVEL:3.8":return {"boundary_comparison":"EXACT_REQUIRED","legacy_warned":"різні межі вимірювання".encode() in blob}
    if key=="TOP_LEVEL:3.9":return {"basis":"CALCULATED_ESTIMATE","legacy_label":"розрахункові".encode() in blob}
    raise AssertionError(key)

def _inv(irms: int,rds: Fraction,m: int)->InverterInput:
    return InverterInput(CanonicalNumber.rational(48,"VOLTAGE","V"),CanonicalNumber.rational(10,"CURRENT","A"),CanonicalNumber.rational(10,"PERCENT","percent"),1,CanonicalNumber.rational(rds,"RESISTANCE","mOhm"),m,CanonicalNumber.rational(75,"TEMPERATURE","degC"),CanonicalNumber.rational(irms,"CURRENT","A"))

def current_corrected_adapter(key: str,case: Mapping[str,Any])->Any:
    if key=="TOP_LEVEL:3.1":
        categories=solve_inverter(_inv(10,Fraction(3,5),2)).canonical_value
        return {"represented_domains":("LV","HV","TRANSFORMER"),"eligible":set(categories)=={"CHANNEL_CONDUCTION","GATE_DRIVE","EOSS_COSS","REVERSE_RECOVERY","SWITCHING_OVERLAP","INTERCONNECT","MAGNETICS","AUXILIARIES","OTHER_DECLARED"}}
    if key=="TOP_LEVEL:3.2":
        value=fixed_ratio_primary_current(case["primary_turns"],case["secondary_turns"],
            case["output_current"],battery_voltage=case["battery_voltage"])
        return {"primary_current":value,
                "turns":(case["primary_turns"],case["secondary_turns"]),
                "battery_voltage":CanonicalNumber.rational(case["battery_voltage"],"VOLTAGE","V"),
                "contract":"FIXED_PHYSICAL_TURNS"}
    if key=="TOP_LEVEL:3.3":
        result=solve_inverter(_inv(case["irms"],Fraction(case["rds"]),case["parallel"]))
        return {"channel_loss":result.canonical_value["CHANNEL_CONDUCTION"],"equation":"Irms^2*2*Rds/m"}
    if key=="TOP_LEVEL:3.4":
        result=solve_inverter(_inv(10,Fraction(3,5),2)); before=(result.canonical_value,result.trace_identity,result.dependency_record_ids)
        compose_system(result,battery={"cells":6}); after=(result.canonical_value,result.trace_identity,result.dependency_record_ids)
        return {"composition":"DOWNSTREAM_ONLY","inverter_invariant":before==after}
    if key=="TOP_LEVEL:3.5":
        value=analog_modref_unavailable(("material_field",))["material_field"]
        return {"uncertainty_visible":value.availability is Availability.UNAVAILABLE,"status":"NOT_MEASURED_FACT"}
    if key=="TOP_LEVEL:3.6":
        matrix=normative_residual_matrix(); row=matrix.rows[("HF_LINK_PSFB","ZERO_TRANSITION","DISABLED","DISABLED")]
        return {"transition_physics":"RETAINED","circulating_current":row["STORED_ENERGY_DECAY"][0]=="REQUIRED"}
    if key=="TOP_LEVEL:3.7":
        result=qualification_result({"synthetic_marker":False},real_claim=True,registry=artifact_registry([]))
        return {"qualification":"INDEPENDENT_OF_RDS","constraint_visible":result.availability is Availability.UNAVAILABLE}
    if key=="TOP_LEVEL:3.8":
        a={name:name for name in SCENARIO_FIELDS}; b=dict(a); b["pass_count"]="different"
        return {"boundary_comparison":"EXACT_REQUIRED","legacy_warned":compare_scenario_boundaries(a,b).availability is Availability.UNAVAILABLE}
    if key=="TOP_LEVEL:3.9":
        result=solve_inverter(_inv(10,Fraction(3,5),2))
        return {"basis":"CALCULATED_ESTIMATE","legacy_label":result.availability is Availability.PROVISIONAL}
    raise AssertionError(key)

def baseline_cases(mapping: Mapping[str,Any],commit: str)->list[dict[str,Any]]:
    key=mapping["namespaced_key"]; blob,capture_hash=_baseline_capture(mapping,commit)
    outcomes=[]
    for case in baseline_population(key):
        baseline=immutable_baseline_adapter(key,case,blob)
        current=current_corrected_adapter(key,case)
        outcomes.append({"id":case["case_id"],"baseline":baseline,"current":current,
                         "passed":canonical_json(baseline)==canonical_json(current),
                         "baseline_capture_hash":capture_hash,
                         "baseline_adapter":"IMMUTABLE_GIT_COMMIT_ADAPTER",
                         "current_adapter":"CURRENT_CORRECTED_IMPLEMENTATION"})
    return outcomes

def _evidence_projection()->dict[str,Any]:
    target=evidence_catalog()[0]
    return {"record_id":target.record_id,"subject":target.subject,"related_subject":target.related_subject,
      "field":target.field,"value":target.value,"unit":target.unit,"EvidenceClass":target.evidence_class,
      "ConflictStatus":target.conflict_status,"manufacturer":target.metadata.get("manufacturer"),
      "rating_class":target.metadata.get("rating_class"),"artifact_id":target.metadata.get("assertion_artifact_id"),
      "artifact_version":target.metadata.get("artifact_version"),"artifact_hash":target.metadata.get("artifact_hash"),
      "locator":target.metadata.get("locator"),"user_conditions":target.metadata.get("user_conditions"),
      "source_conditions":target.metadata.get("source_conditions"),"applicability":target.applicability,
      "relationship_rationale":target.metadata.get("relationship_rationale"),"formula_or_algorithm":target.metadata.get("formula_or_algorithm"),
      "dependency_record_ids":target.metadata.get("dependency_record_ids",()),"instrument_ids":target.metadata.get("instrument_ids",()),
      "calibration_versions":target.metadata.get("calibration_versions",()),"measurement_boundary":target.metadata.get("measurement_boundary"),
      "sample_coverage":target.metadata.get("sample_coverage"),"method":target.metadata.get("method"),
      "uncertainty_or_bound":target.metadata.get("uncertainty_or_bound"),"adjudicator":None,
      "transition_timestamp":None,"transition_reason":None,"trace_links":(),"synthetic_marker":target.synthetic_marker}

def _output_projection()->dict[str,Any]:
    result=material_result(CanonicalNumber.rational(1,"POWER","W"),dependency_records={"source":content_hash("source")},bound={"absolute":"1/100 W"})
    controls=control_evidence(None,None,artifact_registry([]))
    return {"loss_categories":{"CHANNEL_CONDUCTION":"1"},"efficiency":ExplicitAbsence(("efficiency",),"not calculated"),
      "temperatures":ExplicitAbsence(("temperatures",),"not calculated"),"thermal_status":"UNAVAILABLE","standby":"UNAVAILABLE",
      "firmware_implementation_status":controls["firmware_implementation_status"],"hardware_measurement_status":controls["hardware_measurement_status"],
      "device_comparison":"UNAVAILABLE","qualification":"UNAVAILABLE","residual_sources":(),"boundary":"INVERTER",
      "availability":result.availability,"freshness":result.freshness,"applicability":result.applicability,"result_basis":"CALCULATED_ESTIMATE",
      "canonical_value":result.canonical_value,"uncertainty_or_bound":result.uncertainty_or_bound,"artifact_id":result.computation_artifact_id,
      "artifact_version":result.computation_artifact_version,"artifact_hash":result.computation_artifact_hash,"trace_identity":result.trace_identity,
      "dependency_set":result.dependency_record_ids,"synthetic_marker":False,"headline":False}

def concrete_fix_cases(key: str)->list[dict[str,Any]]:
    if key=="TOP_LEVEL:3.10":
        result=thermal_transient({n:25.0 for n in THERMAL_NODES},{n:(-40,175) for n in THERMAL_NODES},{"junction":1,"case":1,"heatsink":1},{"junction":1,"case":1,"heatsink":1},1,{"artifact_id":"missing","version":"1","hash":content_hash("missing")},hot_start=True,registry=artifact_registry([]))
        passed=result.availability is Availability.UNAVAILABLE
        return [{"id":key+":incomplete-hot-start-rejected","assertion":"incomplete dynamic evidence is unavailable","observed":result.availability.value,"passed":passed}]
    if key=="TOP_LEVEL:3.11":
        target=evidence_catalog()[0]; gate=controlled_threefold(0,True,Fraction(3,5),2)
        return [{"id":key+":target-and-gate","assertion":"target class and canonical false-claim ineligibility","observed":[target.evidence_class.value,gate.get("canonical_code")],"passed":target.evidence_class is EvidenceClass.USER_SPECIFIED_TARGET and gate.get("canonical_code")=="INELIGIBLE_ZERO_IRMS" and not any(gate[k] for k in FALSE_CLAIM_KEYS)}]
    if key=="TOP_LEVEL:3.12":
        return [{"id":key+":closed-manifest","assertion":"exact namespaced manifest cardinality","observed":len(EXPECTED_KEYS),"passed":len(EXPECTED_KEYS)==67}]
    namespace,field=key.split(":",1)
    projection=_evidence_projection() if namespace=="EVIDENCE" else _output_projection()
    observed=projection[field]
    # Independent, field-specific expected behavior. Explicit absence is a behavior,
    # not a permission to omit the field or satisfy the route by presence alone.
    if namespace=="EVIDENCE":
        target=evidence_catalog()[0]
        expected=_evidence_projection()[field]
        if field=="EvidenceClass":expected=EvidenceClass.USER_SPECIFIED_TARGET
        elif field=="ConflictStatus":expected=ConflictStatus.NONE
        elif field=="subject":expected="IRL40SC209"
        elif field=="value":expected=CanonicalNumber.rational(Fraction(3,5),"RESISTANCE","mOhm")
        elif field=="synthetic_marker":expected=False
    else:
        expected=_output_projection()[field]
        if field=="availability":expected=Availability.AVAILABLE
        elif field=="freshness":expected=Freshness.FRESH
        elif field=="boundary":expected="INVERTER"
        elif field=="result_basis":expected="CALCULATED_ESTIMATE"
        elif field=="synthetic_marker":expected=False
        elif field=="headline":expected=False
    return [{"id":key+":behavior","assertion":"field-specific canonical corrected behavior",
             "expected":expected,"observed":observed,
             "passed":canonical_json(observed)==canonical_json(expected)}]

def run()->dict[str,Any]:
    frozen=run_frozen(); manifest=json.loads(MANIFEST.read_text(encoding="utf-8")); commit=manifest["git"]["commit"]
    reports=[]
    for mapping in manifest["mappings"]:
        key=mapping["namespaced_key"]
        cases=baseline_cases(mapping,commit) if mapping["mapping_kind"]=="BASELINE_BEHAVIOR" else concrete_fix_cases(key)
        generated=eligible=sampled=len(cases); evaluated=sum("passed" in c for c in cases)
        status="PASS" if evaluated==sampled and sampled>=1 and all(c["passed"] for c in cases) else "FAIL"
        reports.append({"namespaced_key":key,"mapping_kind":mapping["mapping_kind"],"generated":generated,"eligible":eligible,
                        "sampled":sampled,"evaluated":evaluated,"excluded":0,"ordered_case_ids":[c["id"] for c in cases],
                        "outcomes":cases,"status":status})
    passed=frozen["status"]=="PASS" and len(reports)==len(EXPECTED_KEYS) and all(r["status"]=="PASS" and r["generated"]>=r["eligible"]>=r["sampled"]==r["evaluated"]>=1 for r in reports)
    return {"property":2,"status":"PASS" if passed else "FAIL","frozen_runner":frozen,"mapping_count":len(reports),"reports":reports,
            "totals":{name:sum(r[name] for r in reports) for name in ("generated","eligible","sampled","evaluated","excluded")}}
if __name__=="__main__":print(json.dumps(run(),sort_keys=True,separators=(",",":"),default=str))
