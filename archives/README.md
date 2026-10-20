# Preserved V1

`v1_snapshot.zip` contains the exact 52-file reviewed public candidate before V2 changes, including original code, sources, questions, dependency pins and all measured reports. No virtual environment, Git metadata, private notes or real records is included. Individual SHA256 hashes are recorded in v1_file_manifest.json; ZIP SHA256: `4d4886065896ca12e3342ed4041af2b456c4d2a20469ccdb6264fb1d24261d67`.

V1 failures remain part of the project history. A readable copy of the original result files is in reports/v1. Relative links inside that unchanged historical report refer to its original root layout; use the ZIP layout when following those links. No old result was recalculated using V2 code.

To reproduce original code, extract the ZIP into a new folder, read its README, create a separate virtual environment/private storage, and run with the recorded model digests. Temperature zero is not a guarantee of identical generations. The archived app is an experimental local prototype, not validated medical software.

## Preserved V2

`v2_snapshot.zip` contains the exact 62-file reviewed V2 public candidate, including its top-three runtime and measured results. All 18 files listed in its frozen `eval/manifest.json` were hash-checked against the preserved candidate before archiving. Individual hashes are in `v2_file_manifest.json`; ZIP SHA256: `da78c79c827abac6a741de3ca9fc5a0d382ee3d9b2765b1208fdb538431247eb`.

Extract it into a separate folder to rerun the original V2 evaluator with the recorded models. Its README contains the historical counts and instructions as they appeared then; the current root README corrects the corpus counts to 8 sources, 14 sections and 23 chunks. The archived app retains its historical retrieval/UI limitations. It contains no Git metadata, local databases, caches or private model traces. Current development acceptance runs do not replace or recalculate V2 results.
