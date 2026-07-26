# Inverter-Loss Correction Acceptance Evidence

**Status:** PASS
**Executable components:** 16/16 passed
**Acceptance artifact:** `INVERTER-LOSS-CORRECTION-ACCEPTANCE-002` version 2.0.0

## Executed gates
- `PASS` — frozen-artifact-hashes
- `PASS` — unchanged-frozen-exploration
- `PASS` — unit-property-integration-trace-publication
- `PASS` — unchanged-frozen-preservation
- `PASS` — non-vacuous-preservation
- `PASS` — preservation-semantic-status
- `PASS` — legacy-verify_all.py
- `PASS` — legacy-lv_bridge.py
- `PASS` — legacy-compare_tesla.py
- `PASS` — legacy-audit.py
- `PASS` — legacy-audit2.py
- `PASS` — legacy-sim.py
- `PASS` — byte-compilation
- `PASS` — frozen-legacy-input-hashes
- `PASS` — complete-firmware-tree-equality
- `PASS` — independent-digital-vector-validation

## Preservation outcomes
Current executable totals: generated 73, eligible 73, sampled 73, evaluated 73, excluded 0. Each report contains its real case IDs, capture hashes, and outcomes in the acceptance JSON output.

## Firmware equality
Complete current firmware path set and SHA-256 map equality: **PASS**.
- `firmware/CMakeLists.txt` — `02f6a0a5808f9d78c2b2e60a610ce5ae47370c19a680a533c8089e4109c1afba`
- `firmware/README.md` — `5bd7fa1737003a3fc3e7d55dc150a789b29021d711797dd2fed72eed2dc606bb`
- `firmware/main/CMakeLists.txt` — `09aac60483cdb7fecc88f9904864ed43faa5057cf83a6c2b725119970f04fd4e`
- `firmware/main/inv_config.h` — `60e8cb8b7a2af6ad6dc7748a914aa3bc314a0e750e4f32c95a410c01fcb533aa`
- `firmware/main/main.c` — `23b2654c44936fd22d3f1135e333778effb7ce8d5fee09b5af677fa88c78ec85`
- `firmware/main/modulation.c` — `1f0703f5fcc48c7acc42852b217d50669e4c074863d2615bfd4c23133b9b5aff`
- `firmware/main/modulation.h` — `f08763d37daeedbe138e89dcd8334452409b6e490551b95b2f25aa7f72516b1d`
- `firmware/main/pwm.c` — `50cd5954bcc69984f4cdfe62573f863b8489d35e8a7cba2e81e17e44caf41b78`
- `firmware/main/pwm.h` — `be004e85ec92880233855075c7b85d4226fac633ded32416355436931ebf07c5`
- `firmware/sdkconfig.defaults` — `f2031e8e84a341bd9b1e9a7a6cbf636e275d3badce762b145894813d621189ab`

## Required artifact hashes
- `docs/calc/inverter_corrections.py` — `e9bd7e8dff2afda86e0e2f86a8469a1372c8f52be9491fbc5ecce6526441d3ce`
- `docs/calc/test_inverter_corrections.py` — `a6be08a4052e4c251c4a65226dc78a4f9cd1bc728fd48d9bdc59cd0e1785a9e4`
- `docs/calc/test_inverter_corrections_exploration.py` — `4a6b5cf675f9d18d9944eab759b90922caaddc8090eeeabfec6c149a8cbf5fdf`
- `docs/calc/inverter_corrections_preservation.py` — `7ce9d0d9413cabe6adc063f6b5facb3b4e7491930582b9bacb9471981f451edd`
- `docs/calc/inverter_corrections_preservation_enforced.py` — `d515641a66c16ad03324edcf27548c93cf0dcfdb6cf76a55ba57fd60a2c8b92e`
- `docs/calc/inverter_corrections_baseline.json` — `267ed0c98e8960b19020006501a9f4d8f6de60ca9e83b9c0f9ab939020f78692`
- `docs/calc/inverter_corrections_acceptance.py` — `a4a849146648ff8858b153110ace0c6f411cffc2c33547620039e90ed950b504`

## Intentionally non-gating external evidence
- direct exact-part manufacturer evidence: IRL40SC209 RDS(on) strength/qualification remains `UNAVAILABLE; raw pending rows retained`.
- independent analog MODREF fields: analog transfer/current/energy/loss acceptance remains `UNAVAILABLE`.
- approved product settling thresholds and observations: SETTLED classification remains `UNAVAILABLE; TRANSITION`.
- complete thermal evidence: product thermal result remains `UNAVAILABLE`.
- complete exact-device 48 V qualification bundle: real qualification remains `UNAVAILABLE`.
- independent hardware measurement bundle: hardware status remains `UNAVAILABLE`.
- complete-domain independent root certificate: uniqueness remains `UNPROVEN`.
- independent ESP-IDF suppressed-pulse semantics: p=1/p=0 adjusted SR/aggregate remains `UNAVAILABLE; safety-relevant; non-gating`.

No firmware source/configuration or behavior was modified by this correction.
