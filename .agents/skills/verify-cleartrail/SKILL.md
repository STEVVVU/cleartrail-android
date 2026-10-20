---
name: verify-cleartrail
description: Build and drive the real demo Android app on an isolated hosted emulator, retain native UI evidence and stop only owned processes.
---

# Verify Cleartrail

Status: draft until the hosted baseline completes Launch, Doctor, Drive, Evidence and Cleanup. A successful compile alone is not native acceptance. The current Windows host has no Android SDK or emulator.

## Launch

Use the `Cleartrail native checks` workflow on branch `cleartrail`. It runs on an isolated Intel macOS 26 hosted runner with JDK 21 and the preinstalled Android SDK. The maintained driver is `python tools/verify-cleartrail.py <unique-run-name>`. Native device operations are confined to this dedicated hosted test runner, not the user's computer.

The driver builds only `demoDebug` and its native test APK. It uses the checked-in checksum-pinned Gradle wrapper and existing dependency repositories. It does not publish build scans, accept service terms, change KVM permissions, deploy releases or configure a production backend. SDK installation runs noninteractively; missing accepted SDK licenses are a setup blocker, not consent to accept them automatically.

## Doctor

The driver records actual Java/SDK tools, platform/memory, emulator acceleration preflight, isolated emulator directory and build outcomes. It requires the existing hypervisor to pass `emulator -accel-check` before spending time building; it never changes device permissions, enables a hypervisor or falls back silently to an unaccelerated guest. It refuses existing evidence directories and occupied emulator ports. Emulator readiness is checked through actual boot/package-manager state with a bounded deadline. App readiness requires the real package's visible navigation labels, not an arbitrary startup sleep.

## Drive

Install the actual demo APK and launch its MainActivity. Retain a native screenshot and UI hierarchy of the unmodified production demo graph. Run the existing app NavigationTest through the Android instrumentation runner. Those tests drive the real MainActivity with the upstream test graph; distinguish their fixture data from the separate normal-app launch.

Do not substitute Robolectric component snapshots for emulator execution or infer native iOS coverage from Android. Extend the feature map and native tests when original behavior is added.

## Evidence

The driver retains `result.json`, emulator/build/instrumentation logs, the actual native screenshot and UI hierarchy under ignored `.audit/verification/<run>/`. CI uploads these and native test reports. Download the artifacts and inspect the actual rendered screenshot before marking visual acceptance. Keep generated evidence separate from maintained drivers and source screenshot baselines; upstream requires screenshot baselines to be generated in CI.

## Cleanup

The driver terminates only its own emulator process group and checks its console port closed. The isolated AVD/profile and all evidence remain in the run directory until the hosted job's normal teardown. It never kills a pre-existing emulator, rewrites device permissions or deletes user profiles. Confirm cleanup in the retained result and that the screenshot survives cleanup.

See [the feature map](features/README.md). If SDK, licenses, acceleration or boot are blocked, preserve the precise failed stage and keep this skill a draft while continuing independent authorized work.

## Hosted build diagnosis

The driver records available memory and uses a6GiB Gradle heap,2GiB Kotlin heap and the upstream CI concurrency floor of3workers. Run39507012126 built the app APK but failed test-APK D8 dexing with heap exhaustion. Lowering workers to2 produced a distinct configuration stall:39508607286 timed out before task execution;39512526139 preserved a daemon thread dump showing nested configuration queues waiting for worker leases. The diagnostic probe was cancelled after capture and did not retain final JSON, so normal cleanup is not claimed for it.

Restoring3workers with the same heap caps completed both APK builds on [39513191318](https://github.com/STEVVVU/cleartrail-android/actions/runs/39513191318),654tasks in7m48s. This clears the observed build gate, not native acceptance. Existing upstream warnings remain visible; the driver disables no product checks.

That run then failed before boot: the emulator could not discover its AVD index. The owned ANDROID_AVD_HOME directory had not been created before avdmanager. The driver now creates the owned directories and requires both the expected index file and emulator discovery before launch. This behavior is also documented in the [Web Platform Tests Android driver](https://chromium.googlesource.com/external/github.com/web-platform-tests/wpt/+/refs/tags/merge_pr_61730/tools/wpt/android.py). See Android's [environment variable reference](https://developer.android.com/tools/variables) for discovery paths. The current native rerun must still prove boot, actual UI, instrumentation and cleanup. KVM access remains unchanged.

Run [39514321709](https://github.com/STEVVVU/cleartrail-android/actions/runs/39514321709) completed both APK builds and passed owned AVD index/discovery, confirming that setup correction. Its unaccelerated Linux guest did not reach boot/package readiness within 300 seconds. Both cleanup flags passed. No native screenshot or instrumentation result was obtained. Logs show TCG emulation and inaccessible KVM; they do not prove that more time alone would complete boot.

The next probe uses the standard `macos-26-intel` runner, retaining the same x86_64 system image and heap/worker settings. [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) lists that Intel runner; its Apple Silicon runner has a documented nested-virtualization limitation, so it is not used for Android. [Android's acceleration guide](https://developer.android.com/studio/run/emulator-acceleration) describes the built-in macOS Hypervisor.Framework and `-accel-check`. This is a source-qualified alternative, not a guarantee the hosted preflight will pass. The actual probe decides acceptance. No HAXM install, privilege escalation, SDK-license acceptance or KVM change is added. The last boot readiness/error probe is retained as JSON.
