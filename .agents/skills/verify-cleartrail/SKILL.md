---
name: verify-cleartrail
description: Build the real demo Android APKs, validate their transfer, drive an isolated hosted emulator and preserve native evidence after cleanup.
---

# Verify Cleartrail

Push CI runs demo unit tests for the draft repository and Saved feature, lints the touched Compose feature, compiles the instrumentation tests and builds four APKs, and retains the generated schema 15 snapshot in build evidence. The emulator job is optional through workflow dispatch with `native=true`. A skipped emulator job never establishes native UI or document-provider acceptance.

Status: draft. Run 41417601001 compiled and installed all four APKs and passed 11 navigation tests with one additional upstream ignore. Original export, persistence and rendered acceptance remain open. The Windows workspace has no configured Android SDK or emulator.

## Launch

Use the `Cleartrail native checks` workflow on branch `cleartrail`. Its Linux build job runs JDK 21 and the checked-in checksum-pinned Gradle wrapper. Its Ubuntu 24.04 native job owns a fresh standard AOSP API 30 x86_64 emulator. The [official SDK repository metadata](https://dl.google.com/android/repository/sys-img/android/sys-img2-1.xml) lists `system-images;android-30;default;x86_64` as the default Android system image, revision 11. Device operations are confined to this dedicated hosted runner.

The maintained commands are:

```sh
python -m unittest discover -s tools -p test_verify_cleartrail.py
python tools/verify-cleartrail.py <unique-build-name> --mode build
python tools/verify-cleartrail.py <unique-native-name> --mode native --apk-dir <same-run-artifact-directory>
```

The workflow transfers `app.apk`, `tests.apk`, `room-tests.apk`, `data-tests.apk` and `manifest.json` through the official artifact actions. The native job requires the successful build job and downloads only that run's named artifact. It checks schema version, source commit, exact file names and SHA-256 hashes before installation. These checks establish integrity within this workflow, not independently signed provenance. A failed native job can be rerun using the successful build artifact without compiling again.

## Doctor

Record Java, SDK, available memory, source hashes, emulator version and acceleration preflight. Build `demoDebug` and its app, database and data native test APKs using a 6 GiB Gradle heap, 2 GiB Kotlin heap and three workers. The build also runs `:core:data:testDemoDebugUnitTest`, `:feature:bookmarks:impl:testDemoDebugUnitTest`, `:feature:bookmarks:impl:lintDemoDebug`, `:core:database:assembleDemoDebugAndroidTest` and `:core:data:assembleDemoDebugAndroidTest`. The build evidence retains the exported Room schema 15 for review and check-in. Never autoaccept SDK licenses, change KVM permissions or install a hypervisor. Refuse occupied emulator ports and existing evidence directories.

Create the owned AVD directories and require its index and emulator discovery. Check acceleration after SDK installation and bound actual guest boot/package readiness to 900 seconds, retaining elapsed time. `command-events.jsonl` records flushed start, spawn, completion or failure events for each subprocess; repeated Python stack snapshots go to `python-stacks.log`. The append-only `boot-probes.jsonl` records each started and completed adb call plus readiness state, so a truncated hosted job identifies its last completed call. These diagnostics do not extend command or job deadlines. Record the real `CREATE_DOCUMENT` resolver result in `document-picker.json` and require a resolved component before installing APKs or launching the app.

Before launching on Linux, record the existing `/dev/kvm` device type, permissions and access in `kvm-preflight.json` and fail if the runner cannot read and write it. Do not change permissions. The native AVD requests two cores; retain the guest's online CPU list after boot or in failure probes. GitHub documents [Android hardware acceleration on hosted Linux runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) and the [emulator's source](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/android-emu/android/cmdline-options.h) defines `-cores`. Actual Linux KVM access, guest core count and boot performance are not yet observed.

Run 41424042735 on Ubuntu 24.04 found the existing KVM character device mode 0660, owner 0:993, unreadable and unwritable by the job user. The separate manual `Cleartrail read-only KVM preflight` workflow observes Ubuntu 22.04's current state using the same `kvm_preflight` helper, `id`, and the preinstalled emulator's bounded `-accel-check`. It installs no SDK components, creates no AVD and changes no permissions. It retains raw identity/host logs and JSON even on failure. This is a one-host environment probe, not native acceptance or a guarantee that the full image can boot within its existing bounds. Ubuntu 22.04 access is unknown until the hosted result; if it is inaccessible, stop rather than alter permissions.

Native execution has an overall 1,800-second budget inside the 40-minute job. Individual command and boot deadlines remain upper bounds; the remaining overall budget can shorten them. Failure probes and cleanup run after that budget so the workflow has time to retain evidence.

## Drive

Install all four validated APKs before starting the app, with `-t` for test packages. `install-events.jsonl` retains each install's start, elapsed time, output and failure; each remains subject to its 60-second upper bound. Launch MainActivity without ActivityManager's separate `-W` wait. The driver then requires the real package and `Now in Android`, `For you` and `Interests` navigation labels within 90 seconds. Preserve the actual native screenshot and hierarchy of this normal demo graph.

Confirm the installed test APK's registered component and target, then run the entire unchanged `com.google.samples.apps.nowinandroid.ui.NavigationTest` through its packaged `NiaTestRunner` with `am instrument -w -r --no-window-animation`. The animation flag preserves the existing Gradle convention's `animationsDisabled = true`. See [AGP TestOptions](https://developer.android.com/reference/tools/gradle-api/8.11/com/android/build/api/dsl/TestOptions#animationsDisabled).

Require a completed raw instrumentation protocol with at least 11 tests, no failure or assumption-failure status, and at most the class's one existing ignored test. A zero adb exit code alone is insufficient. The instrumentation tests use the upstream test graph; their fixtures are distinct from the separate normal-app launch.

The draft original-feature journey seeds a synthetic draft through the test graph, drives the real system document picker to Downloads, checks the exact preview, edits after approval and requires the write action to disappear, then reviews and approves again. The host compares the exported provider file byte for byte with the preview fixture and retains picker, preview, invalidation and saved-state screenshots. The test graph uses a fake draft repository, so this journey does not prove Room persistence. The separate Room instrumentation APK executes schema 14 migration and DAO reopen. A separate data-module instrumentation APK injects the production repository and writes a synthetic draft, then runs a read assertion in a second instrumentation process; the driver requires distinct process IDs. No ignored tests are permitted in either path. The [Android 11 DocumentsUI layout](https://android.googlesource.com/platform/packages/apps/DocumentsUI/+/refs/heads/android11-release/res/layout/fragment_save.xml) identifies the save control as `android:id/button1`. Android documents describe the [system document picker](https://developer.android.com/training/data-storage/shared/documents-files) and [cross-app UI Automator](https://developer.android.com/training/testing/other-components/ui-automator). This extension is a draft until hosted compilation and execution succeed.

Do not substitute Robolectric snapshots for emulator execution or infer iOS coverage. Extend the feature map and native tests when original behavior is added.

## Evidence

Keep generated data under ignored `.audit/verification/<run>/`. The build phase retains its result, Gradle logs and staged APK manifest. The native phase retains validation results, launch output, hierarchy, screenshot, instrumentation output, emulator logs, command lifecycle records, Python stack snapshots, append-only boot probes and bounded failure probes. Brief file capture outcomes and errors are recorded in `brief-captures.json`; a failure also triggers a separate screenshot and hierarchy probe. CI uploads evidence separately from APKs. Download and inspect the actual PNG before accepting the UI. Keep maintained drivers separate from generated evidence. Upstream screenshot baselines remain CI-generated.

## Cleanup

Terminate only the owned emulator process group and require its console port to close. Record emulator cleanup and evidence retention in `result.json`. Native acceptance requires successful cleanup and retained native screenshots, instrumentation logs and matching provider and preview bytes after cleanup. Screenshots must decode as supported 8-bit RGB or RGBA PNGs and contain nonblack pixels; this is a blank-frame guard, not a substitute for visual inspection. Cleanup errors are recorded separately from any primary failure. The isolated profile and evidence survive until hosted-job teardown. Never kill a pre-existing emulator or remove user profiles. Confirm the screenshot survives cleanup.

See [the feature map](features/README.md). A missing SDK license, failed acceleration, failed boot, splash-only screen or failed instrumentation keeps acceptance open.

## Current code delivery

[Run 39543402892](https://github.com/STEVVVU/cleartrail-android/actions/runs/39543402892) at `96b11db5` passed 11 verifier boundary tests, 49 scoped unit tests, feature lint without errors, database instrumentation compilation, and both app APK builds. The main agent downloaded both APKs, matched their SHA-256 values to the exact source-commit manifest, inspected test and lint XML, and compared the generated Room schema 15 to the checked-in snapshot. Lint retains 27 inherited warnings. `buildAccepted` is true, `nativeAcceptance` is false, and evidence retention passed. The optional emulator job was skipped under the user's code-delivery scope. Real UI, document-provider writes and Room migration execution remain unverified.

## Observed baseline

[Run 41413512619](https://github.com/STEVVVU/cleartrail-android/actions/runs/41413512619) at `f162d6b4` compiled all four APKs and reached the normal-app navigation hierarchy after a 352.384-second ATD boot. Its document resolver returned `No activity found` despite exit code zero, and both retained screenshots are solid black. [Android's ATD documentation](https://developer.android.com/studio/test/managed-devices#use-automated-test-devices) states that ATDs disable hardware rendering and do not support screenshot tests that depend on it. The standard image is selected to test the required picker and rendered UI; availability and rendering still require hosted proof. The app test APK installation separately timed out after 60 seconds while the app was foregrounded. Retained process and logcat probes show dex2oat running and app startup work; they do not establish the timeout's cause or an adb streaming failure. Installing before launch remains a bounded contention experiment, not a confirmed fix. Native tests, provider bytes and visible screenshots remain unverified.

[Run 41419414030](https://github.com/STEVVVU/cleartrail-android/actions/runs/41419414030) used the standard image on accelerated Intel macOS but did not finish boot within 900 seconds. Guest adb and system_server responded while first-boot dex2oat work continued. The emulator logged that it forced one virtual core on the host; the matching [emulator source](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android-qemu2-glue/main.cpp) applies that macOS fallback after setting the requested core count. The Linux runner is a bounded environment experiment, not a proven cure, and its existing KVM access must pass preflight.

[Run 39513191318](https://github.com/STEVVVU/cleartrail-android/actions/runs/39513191318) completed both APK builds after restoring three workers. Earlier two-worker configuration stalled; lowering concurrency is not assumed safe here. Later probes separately established AVD discovery and Hypervisor.Framework preflight. Acceleration alone did not establish boot readiness.

[Run 39519290354](https://github.com/STEVVVU/cleartrail-android/actions/runs/39519290354) booted the guest, built both APKs and installed the app. `am start -W` returned `Status: timeout` while the retained PNG showed the splash screen. The driver aborted before its own UI-readiness gate. No completed navigation or instrumentation is claimed. Cleanup and evidence retention passed. The separate build/native workflow and non-waiting launch are corrections awaiting hosted proof. At that baseline revision, the original reading-brief feature had not yet been added.

[Run 39524380971](https://github.com/STEVVVU/cleartrail-android/actions/runs/39524380971) passed both APK builds, artifact transfer and exact source/hash validation. Its accelerated Intel guest did not complete boot within 300 seconds. Retained logs show one virtual CPU, a live system_server and slow package parsing rather than an observed guest panic. Cleanup passed. The emulator's [upstream macOS code](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android-qemu2-glue/main.cpp) forces one guest CPU on hosts with fewer than six logical cores, so adding a cores flag is not assumed to override it. The next bounded probe allows 900 seconds with the same image and required boot/package predicates. This tests cold-boot duration; it does not establish that more time resolves startup or change acceptance to a partial boot.

[Run 39526496486](https://github.com/STEVVVU/cleartrail-android/actions/runs/39526496486) passed both APK builds and artifact transfer, but its 45-minute native job was cancelled after the visible log stopped at `emulator -list-avds`. No native artifact, CLI logs or cleanup proof survived. The earlier output did not identify whether process creation or a later call stalled. The current diagnostics retain subprocess lifecycle events and repeated Python stack snapshots, and append each boot probe before recording its result. These changes improve diagnosis and evidence retention only. Native boot, navigation, instrumentation and cleanup remain unproved; one bounded hosted native run is required before accepting the driver change.
