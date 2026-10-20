---
name: verify-cleartrail
description: Build and drive the real demo Android app on an isolated hosted emulator, retain native UI evidence and stop only owned processes.
---

# Verify Cleartrail

Status: draft until the hosted baseline completes Launch, Doctor, Drive, Evidence and Cleanup. A successful compile alone is not native acceptance. The current Windows host has no Android SDK or emulator.

## Launch

Use the `Cleartrail native checks` workflow on branch `cleartrail`. It runs on an isolated Ubuntu 24.04 hosted runner with JDK 21 and the preinstalled Android SDK. The maintained driver is `python tools/verify-cleartrail.py <unique-run-name>`. Native device operations are confined to this dedicated hosted test runner, not the user's computer.

The driver builds only `demoDebug` and its native test APK. It uses the checked-in checksum-pinned Gradle wrapper and existing dependency repositories. It does not publish build scans, accept service terms, change KVM permissions, deploy releases or configure a production backend. SDK installation runs noninteractively; missing accepted SDK licenses are a setup blocker, not consent to accept them automatically.

## Doctor

The driver records actual Java/SDK tools, available acceleration, isolated emulator directory and build outcomes. It refuses existing evidence directories and occupied emulator ports. Emulator readiness is checked through actual boot/package-manager state with a bounded deadline. App readiness requires the real package's visible navigation labels, not an arbitrary startup sleep.

## Drive

Install the actual demo APK and launch its MainActivity. Retain a native screenshot and UI hierarchy of the unmodified production demo graph. Run the existing app NavigationTest through the Android instrumentation runner. Those tests drive the real MainActivity with the upstream test graph; distinguish their fixture data from the separate normal-app launch.

Do not substitute Robolectric component snapshots for emulator execution or infer native iOS coverage from Android. Extend the feature map and native tests when original behavior is added.

## Evidence

The driver retains `result.json`, emulator/build/instrumentation logs, the actual native screenshot and UI hierarchy under ignored `.audit/verification/<run>/`. CI uploads these and native test reports. Download the artifacts and inspect the actual rendered screenshot before marking visual acceptance. Keep generated evidence separate from maintained drivers and source screenshot baselines; upstream requires screenshot baselines to be generated in CI.

## Cleanup

The driver terminates only its own emulator process group and checks its console port closed. The isolated AVD/profile and all evidence remain in the run directory until the hosted job's normal teardown. It never kills a pre-existing emulator, rewrites device permissions or deletes user profiles. Confirm cleanup in the retained result and that the screenshot survives cleanup.

See [the feature map](features/README.md). If SDK, licenses, acceleration or boot are blocked, preserve the precise failed stage and keep this skill a draft while continuing independent authorized work.
