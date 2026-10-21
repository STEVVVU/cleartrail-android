---
name: verify-cleartrail
description: Build the real demo Android APKs, validate their transfer, drive an isolated hosted emulator and preserve native evidence after cleanup.
---

# Verify Cleartrail

Status: draft. Both APKs and emulator boot have been observed, but normal navigation and the existing instrumentation class have not passed together. The Windows workspace has no configured Android SDK or emulator.

## Launch

Use the `Cleartrail native checks` workflow on branch `cleartrail`. Its Linux build job runs JDK 21 and the checked-in checksum-pinned Gradle wrapper. Its Intel macOS 26 native job owns a fresh API 30 x86_64 ATD emulator. Device operations are confined to this dedicated hosted runner.

The maintained commands are:

```sh
python -m unittest discover -s tools -p test_verify_cleartrail.py
python tools/verify-cleartrail.py <unique-build-name> --mode build
python tools/verify-cleartrail.py <unique-native-name> --mode native --apk-dir <same-run-artifact-directory>
```

The workflow transfers `app.apk`, `tests.apk` and `manifest.json` through the official artifact actions. The native job requires the successful build job and downloads only that run's named artifact. It checks schema version, source commit, exact file names and SHA-256 hashes before installation. These checks establish integrity within this workflow, not independently signed provenance. A failed native job can be rerun using the successful build artifact without compiling again.

## Doctor

Record Java, SDK, available memory, source hashes, emulator version and acceleration preflight. Build only `demoDebug` and its native test APK using a 6 GiB Gradle heap, 2 GiB Kotlin heap and three workers. Never autoaccept SDK licenses, change KVM permissions or install a hypervisor. Refuse occupied emulator ports and existing evidence directories.

Create the owned AVD directories and require its index and emulator discovery. Check acceleration after SDK installation and bound actual guest boot/package readiness to 900 seconds, retaining elapsed time. Record the real `CREATE_DOCUMENT` resolver result in `document-picker.json`; its availability is a prerequisite for a future document-export feature, not a baseline requirement.

## Drive

Install the validated app APK and launch its MainActivity without ActivityManager's separate `-W` wait. The driver then requires the real package and visible `Now in Android`, `For you` and `Interests` navigation labels within 90 seconds. Preserve the actual native screenshot and hierarchy of this normal demo graph.

Install the test APK with adb's test-package flag. Confirm the registered component and target, then run the entire unchanged `com.google.samples.apps.nowinandroid.ui.NavigationTest` through its packaged `NiaTestRunner` with `am instrument -w -r --no-window-animation`. The animation flag preserves the existing Gradle convention's `animationsDisabled = true`. See [AGP TestOptions](https://developer.android.com/reference/tools/gradle-api/8.11/com/android/build/api/dsl/TestOptions#animationsDisabled).

Require a completed raw instrumentation protocol with at least 11 tests, no failure or assumption-failure status, and at most the class's one existing ignored test. A zero adb exit code alone is insufficient. The instrumentation tests use the upstream test graph; their fixtures are distinct from the separate normal-app launch.

Do not substitute Robolectric snapshots for emulator execution or infer iOS coverage. Extend the feature map and native tests when original behavior is added.

## Evidence

Keep generated data under ignored `.audit/verification/<run>/`. The build phase retains its result, Gradle logs and staged APK manifest. The native phase retains validation results, launch output, hierarchy, screenshot, instrumentation output, emulator logs and bounded failure probes. CI uploads evidence separately from APKs. Download and inspect the actual PNG before accepting the UI. Keep maintained drivers separate from generated evidence. Upstream screenshot baselines remain CI-generated.

## Cleanup

Terminate only the owned emulator process group and require its console port to close. Record emulator cleanup and evidence retention in `result.json`. The isolated profile and evidence survive until hosted-job teardown. Never kill a pre-existing emulator or remove user profiles. Confirm the screenshot survives cleanup.

See [the feature map](features/README.md). A missing SDK license, failed acceleration, failed boot, splash-only screen or failed instrumentation keeps acceptance open.

## Observed baseline

[Run 39513191318](https://github.com/STEVVVU/cleartrail-android/actions/runs/39513191318) completed both APK builds after restoring three workers. Earlier two-worker configuration stalled; lowering concurrency is not assumed safe here. Later probes separately established AVD discovery and Hypervisor.Framework preflight. Acceleration alone did not establish boot readiness.

[Run 39519290354](https://github.com/STEVVVU/cleartrail-android/actions/runs/39519290354) booted the guest, built both APKs and installed the app. `am start -W` returned `Status: timeout` while the retained PNG showed the splash screen. The driver aborted before its own UI-readiness gate. No completed navigation or instrumentation is claimed. Cleanup and evidence retention passed. The separate build/native workflow and non-waiting launch are corrections awaiting hosted proof. No original Kotlin product feature has been added.

[Run 39524380971](https://github.com/STEVVVU/cleartrail-android/actions/runs/39524380971) passed both APK builds, artifact transfer and exact source/hash validation. Its accelerated Intel guest did not complete boot within 300 seconds. Retained logs show one virtual CPU, a live system_server and slow package parsing rather than an observed guest panic. Cleanup passed. The emulator's [upstream macOS code](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android-qemu2-glue/main.cpp) forces one guest CPU on hosts with fewer than six logical cores, so adding a cores flag is not assumed to override it. The next bounded probe allows 900 seconds with the same image and required boot/package predicates. This tests cold-boot duration; it does not establish that more time resolves startup or change acceptance to a partial boot.
