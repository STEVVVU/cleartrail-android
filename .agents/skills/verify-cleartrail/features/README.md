# Feature map

| Feature | Driver and acceptance |
| --- | --- |
| Build and artifact transfer | `tools/verify-cleartrail.py --mode build` builds both real APKs. `--mode native --apk-dir ...` requires the same source commit and exact hashes. Local boundary tests pass; hosted transfer pending. |
| Native demo app launch | Actual install/MainActivity launch, package/navigation readiness, PNG and hierarchy. Driver subprocess starts, spawns, completions and failures are retained in `command-events.jsonl`, with recurring interpreter stacks in `python-stacks.log`; append-only adb boot call records are in `boot-probes.jsonl`. Guest boot and splash observed in run 39519290354; normal navigation pending. Run 39526496486 ended before native evidence or cleanup proof. |
| Existing navigation | Entire unchanged app NavigationTest through packaged NiaTestRunner, with upstream animation setting. Require at least 11 completed tests and no new ignores/failures. Emulator execution pending. |
| Consent-gated reading brief | Saved screen owns explicit draft replacement, an optional private note, exact JSON preview and SHA-256, source labels, a document-picker destination, one-use in-memory approval, revocation, and a provider write. Room stores content only. Repository and feature unit tests cover known and unknown labels, edit and destination binding, revocation, replay, write failure, and replacement. A Room reopen test covers draft persistence. Emulator rendering, picker resolution, provider bytes, execution of the Room test, and upgrade from an existing database remain unverified. |
| iOS / cross-platform mobile | Outside this Android app's scope. |
