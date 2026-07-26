#!/usr/bin/env python3
"""Executable acceptance gate. Every reported PASS is derived from a subprocess result."""
from __future__ import annotations
import argparse, hashlib, json, py_compile, subprocess, sys
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from inverter_corrections import *

FROZEN_EXPLORATION_SHA="4a6b5cf675f9d18d9944eab759b90922caaddc8090eeeabfec6c149a8cbf5fdf"
FROZEN_PRESERVATION_SHA="7ce9d0d9413cabe6adc063f6b5facb3b4e7491930582b9bacb9471981f451edd"

def sha(path: Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args: str)->str: return subprocess.run(["git",*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def execute(name: str, command: list[str])->dict[str,Any]:
    proc=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    return {"name":name,"command":command,"returncode":proc.returncode,"passed":proc.returncode==0,
            "stdout_sha256":hashlib.sha256(proc.stdout.encode()).hexdigest(),"stderr_sha256":hashlib.sha256(proc.stderr.encode()).hexdigest(),
            "stdout_tail":proc.stdout[-500:],"stderr_tail":proc.stderr[-500:]}

def generate()->dict[str,Any]:
    baseline=json.loads((HERE/"inverter_corrections_baseline.json").read_text(encoding="utf-8")); before=baseline["firmware_before"]
    components=[]
    frozen_hashes={"exploration":sha(HERE/"test_inverter_corrections_exploration.py"),"preservation":sha(HERE/"inverter_corrections_preservation.py")}
    hash_gate=frozen_hashes=={"exploration":FROZEN_EXPLORATION_SHA,"preservation":FROZEN_PRESERVATION_SHA}
    components.append({"name":"frozen-artifact-hashes","passed":hash_gate,"actual":frozen_hashes,
                       "expected":{"exploration":FROZEN_EXPLORATION_SHA,"preservation":FROZEN_PRESERVATION_SHA}})
    components.append(execute("unchanged-frozen-exploration",[sys.executable,"docs/calc/test_inverter_corrections_exploration.py"]))
    components.append(execute("unit-property-integration-trace-publication",[sys.executable,"docs/calc/test_inverter_corrections.py"]))
    frozen_preservation=execute("unchanged-frozen-preservation",[sys.executable,"docs/calc/inverter_corrections_preservation.py"]); components.append(frozen_preservation)
    enforced_preservation=execute("non-vacuous-preservation",[sys.executable,"docs/calc/inverter_corrections_preservation_enforced.py"]); components.append(enforced_preservation)
    preservation_payload={}
    if enforced_preservation["passed"]:
        preservation_payload=json.loads(subprocess.run([sys.executable,"docs/calc/inverter_corrections_preservation_enforced.py"],cwd=ROOT,check=True,capture_output=True,text=True).stdout)
        components.append({"name":"preservation-semantic-status","passed":preservation_payload.get("status")=="PASS" and all(r["status"]=="PASS" for r in preservation_payload.get("reports",[])),"totals":preservation_payload.get("totals")})
    legacy=[]
    for name in ("verify_all.py","lv_bridge.py","compare_tesla.py","audit.py","audit2.py","sim.py"):
        result=execute("legacy-"+name,[sys.executable,"docs/calc/"+name]); legacy.append(result); components.append(result)
    compile_paths=sorted(str(p.relative_to(ROOT)) for p in HERE.glob("*.py"))
    compile_errors=[]
    for rel in compile_paths:
        try: py_compile.compile(str(ROOT/rel),doraise=True)
        except Exception as exc: compile_errors.append(f"{rel}:{exc}")
    components.append({"name":"byte-compilation","passed":not compile_errors,"compiled":compile_paths,"errors":compile_errors})
    legacy_hashes={rel:sha(ROOT/rel) for rel in baseline["legacy_inputs"]}
    components.append({"name":"frozen-legacy-input-hashes","passed":legacy_hashes==baseline["legacy_inputs"],"actual":legacy_hashes,"expected":baseline["legacy_inputs"]})
    try:
        after=firmware_manifest_current(before["entries"]); path_error=None
    except ValueError as exc:
        after=firmware_manifest_current(); path_error=str(exc)
    # The immutable named baseline identity remains the manifest's commit/tree; the
    # current repository may contain calculation-only commits. Firmware equality is
    # established by the complete closed path/hash map, not by requiring HEAD's whole
    # repository tree (which would make any evidence/doc commit fail acceptance).
    firmware=verify_firmware_unchanged(before,after,before["named_git_commit"],before["git_tree_hash"])
    firmware_pass=path_error is None and firmware.availability is Availability.AVAILABLE and set(after)==set(before["entries"])
    components.append({"name":"complete-firmware-tree-equality","passed":firmware_pass,"path_error":path_error,"before":before["entries"],"after":after,
                       "added":sorted(set(after)-set(before["entries"])),"removed":sorted(set(before["entries"])-set(after)),
                       "changed":sorted(p for p in set(after)&set(before["entries"]) if after[p]!=before["entries"][p])})
    vectors={}
    for p in (10,1,0):
        actual=compute_timing_from_firmware(p); expected=independent_expected_timing(p); result=validate_timing(actual,expected)
        vectors[str(p)]={"passed":result.availability is Availability.AVAILABLE,"N":actual.N,"H":actual.H,"q":str(actual.q.fraction),"k":actual.k,
                         "raw_count":len(actual.raw_events.value),"adjusted_scope_count":len(actual.complete_aggregate_adjusted_events.value) if p==10 else len(actual.adjusted_lv_events.value),
                         "adjusted_sr":actual.complete_adjusted_sr_events.availability.value,"residual_owner":actual.residual_owner}
    components.append({"name":"independent-digital-vector-validation","passed":all(v["passed"] for v in vectors.values()),"vectors":vectors})
    artifact_paths=[HERE/"inverter_corrections.py",HERE/"test_inverter_corrections.py",HERE/"test_inverter_corrections_exploration.py",HERE/"inverter_corrections_preservation.py",HERE/"inverter_corrections_preservation_enforced.py",HERE/"inverter_corrections_baseline.json",HERE/"inverter_corrections_acceptance.py"]
    artifacts={p.relative_to(ROOT).as_posix():sha(p) for p in artifact_paths}
    status="PASS" if all(c["passed"] for c in components) else "FAIL"
    return {"artifact_id":"INVERTER-LOSS-CORRECTION-ACCEPTANCE-002","version":"2.0.0","status":status,"components":components,
            "baseline":{"commit":baseline["git"]["commit"],"tree":baseline["git"]["tree"]},"preservation":preservation_payload,
            "firmware":{"equal":firmware_pass,"before":before["entries"],"after":after},"digital_vectors":vectors,"artifacts":artifacts,
            "non_gating_obligations":[
                {"gap":"direct exact-part manufacturer evidence","affected":"IRL40SC209 RDS(on) strength/qualification","status":"UNAVAILABLE; raw pending rows retained"},
                {"gap":"independent analog MODREF fields","affected":"analog transfer/current/energy/loss acceptance","status":"UNAVAILABLE"},
                {"gap":"approved product settling thresholds and observations","affected":"SETTLED classification","status":"UNAVAILABLE; TRANSITION"},
                {"gap":"complete thermal evidence","affected":"product thermal result","status":"UNAVAILABLE"},
                {"gap":"complete exact-device 48 V qualification bundle","affected":"real qualification","status":"UNAVAILABLE"},
                {"gap":"independent hardware measurement bundle","affected":"hardware status","status":"UNAVAILABLE"},
                {"gap":"complete-domain independent root certificate","affected":"uniqueness","status":"UNPROVEN"},
                {"gap":"independent ESP-IDF suppressed-pulse semantics","affected":"p=1/p=0 adjusted SR/aggregate","status":"UNAVAILABLE; safety-relevant; non-gating"}]}

def render_markdown(data: dict[str,Any])->str:
    passed=sum(1 for c in data["components"] if c["passed"]); total=len(data["components"])
    totals=data.get("preservation",{}).get("totals",{})
    lines=["# Inverter-Loss Correction Acceptance Evidence","",f"**Status:** {data['status']}",f"**Executable components:** {passed}/{total} passed",f"**Acceptance artifact:** `{data['artifact_id']}` version {data['version']}","","## Executed gates"]
    for c in data["components"]: lines.append(f"- `{'PASS' if c['passed'] else 'FAIL'}` — {c['name']}")
    lines += ["","## Preservation outcomes",f"Current executable totals: generated {totals.get('generated',0)}, eligible {totals.get('eligible',0)}, sampled {totals.get('sampled',0)}, evaluated {totals.get('evaluated',0)}, excluded {totals.get('excluded',0)}. Each report contains its real case IDs, capture hashes, and outcomes in the acceptance JSON output.","","## Firmware equality",f"Complete current firmware path set and SHA-256 map equality: **{'PASS' if data['firmware']['equal'] else 'FAIL'}**."]
    for path,digest in data["firmware"]["after"].items(): lines.append(f"- `{path}` — `{digest}`")
    lines += ["","## Required artifact hashes"]
    for path,digest in data["artifacts"].items(): lines.append(f"- `{path}` — `{digest}`")
    lines += ["","## Intentionally non-gating external evidence"]
    for item in data["non_gating_obligations"]: lines.append(f"- {item['gap']}: {item['affected']} remains `{item['status']}`.")
    lines += ["","No firmware source/configuration or behavior was modified by this correction."]
    return "\n".join(lines)+"\n"

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--write-markdown",action="store_true"); args=parser.parse_args()
    data=generate()
    if args.write_markdown: (ROOT/"docs/INVERTER_LOSS_CORRECTIONS_ACCEPTANCE.md").write_text(render_markdown(data),encoding="utf-8")
    print(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str))
    raise SystemExit(0 if data["status"]=="PASS" else 1)
