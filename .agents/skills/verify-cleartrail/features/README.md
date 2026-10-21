# Feature map

| Feature | Driver and acceptance |
| --- | --- |
| Build and artifact transfer | `tools/verify-cleartrail.py --mode build` builds both real APKs. `--mode native --apk-dir ...` requires the same source commit and exact hashes. Local boundary tests pass; hosted transfer pending. |
| Native demo app launch | Actual install/MainActivity launch, package/navigation readiness, PNG and hierarchy. Driver subprocess starts, spawns, completions and failures are retained in `command-events.jsonl`, with recurring interpreter stacks in `python-stacks.log`; append-only adb boot call records are in `boot-probes.jsonl`. Guest boot and splash observed in run 39519290354; normal navigation pending. Run 39526496486 ended before native evidence or cleanup proof. |
| Existing navigation | Entire unchanged app NavigationTest through packaged NiaTestRunner, with upstream animation setting. Require at least 11 completed tests and no new ignores/failures. Emulator execution pending. |
| Original data-flow/consent workflow | Planned. No product implementation or acceptance yet. Actual document-provider resolution is recorded before adopting an export path. |
| iOS / cross-platform mobile | Outside this Android app's scope. |
