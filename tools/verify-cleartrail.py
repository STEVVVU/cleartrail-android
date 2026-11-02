"""Hosted native Android verification; no UI automation on the user's computer."""

import argparse
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "com.google.samples.apps.nowinandroid.demo.debug"
TEST_CLASS = "com.google.samples.apps.nowinandroid.ui.NavigationTest"
TEST_RUNNER = PACKAGE + ".test/com.google.samples.apps.nowinandroid.core.testing.NiaTestRunner"
NATIVE_PNGS = ("native-launch.png", "brief-picker.png", "brief-preview.png", "brief-invalidated.png", "brief-saved.png")
NATIVE_FILES = ("launch-ui.xml", "instrumentation.log", "brief-instrumentation.log", "brief-captures.json",
                "room-instrumentation-0.log", "room-instrumentation-1.log", "data-writeDraft.log",
                "data-readDraftAfterProcessRestart.log", "brief-expected.json", "brief-provider.json")


def finalize_native_receipt(result, run, checks_passed, emulator_stopped, cleanup_error=None):
    missing = []
    for name in NATIVE_FILES:
        path = run / name
        try:
            retained = path.is_file() and path.stat().st_size > 0
        except OSError:
            retained = False
        if not retained:
            missing.append(name)
    for name in NATIVE_PNGS:
        path = run / name
        try:
            retained = path.is_file() and path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        except OSError:
            retained = False
        if not retained:
            missing.append(name)
    expected, provider = run / "brief-expected.json", run / "brief-provider.json"
    try:
        if expected.is_file() and provider.is_file() and expected.read_bytes() != provider.read_bytes():
            missing.append("provider bytes differ from preview")
    except OSError as error:
        missing.append("provider bytes could not be read: " + str(error))
    result["cleanup"] = {"emulatorStopped": emulator_stopped, "evidenceRetained": not missing}
    if missing:
        result["cleanup"]["missingEvidence"] = missing
    if cleanup_error:
        result["cleanup"]["error"] = cleanup_error
    result["nativeAcceptance"] = bool(checks_passed and not result.get("error") and emulator_stopped and not cleanup_error and not missing)



def append_json_record(path, record):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
        stream.flush()


def write_and_close_stdin(process, input_text):
    try:
        process.stdin.write(input_text.encode())
    finally:
        process.stdin.close()


def package_apks(destination, source_commit, files):
    destination.mkdir()
    manifest = {"schemaVersion": 3, "sourceCommit": source_commit, "files": {}}
    for name, source in files.items():
        target = destination / name
        shutil.copyfile(source, target)
        manifest["files"][name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def validated_apks(directory, source_commit):
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("APK manifest must be a regular file.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 3 or manifest.get("sourceCommit") != source_commit:
        raise ValueError("APK manifest schema or source commit does not match this workflow.")
    if not source_commit or set(manifest.get("files", {})) != {"app.apk", "tests.apk", "room-tests.apk", "data-tests.apk"}:
        raise ValueError("APK manifest must name exactly the app, app test, Room test and data test APKs.")
    for name, digest in manifest["files"].items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("APK integrity check failed for " + name)
    return manifest


def completed_tests(output, minimum, max_ignored=0):
    count = re.search(r"^OK \((\d+) tests?\)\s*$", output, re.MULTILINE)
    completed = re.search(r"^INSTRUMENTATION_CODE:\s*-1\s*$", output, re.MULTILINE)
    failures = re.search(r"^INSTRUMENTATION_STATUS_CODE:\s*-(?:1|2|4)\s*$", output, re.MULTILINE)
    ignored = len(re.findall(r"^INSTRUMENTATION_STATUS_CODE:\s*-3\s*$", output, re.MULTILINE))
    if not count or int(count[1]) < minimum or not completed or failures or ignored > max_ignored or "FAILURES!!!" in output or "INSTRUMENTATION_FAILED" in output:
        raise ValueError("Instrumentation did not complete the mapped test class successfully.")
    return {"completedTests": int(count[1]), "ignoredTests": ignored}


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_name")
    parser.add_argument("--mode", choices=("build", "native"), required=True)
    parser.add_argument("--apk-dir", type=Path)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or platform.system() not in ("Linux", "Darwin") or platform.machine() != "x86_64":
        parser.error("Use the dedicated x86_64 Linux/Intel macOS hosted workflow. No local SDK/device is configured.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", args.run_name):
        parser.error("Use a short alphanumeric run name.")
    if args.mode == "native" and args.apk_dir is None:
        parser.error("Native verification requires the same-run APK artifact directory.")
    if args.mode == "native" and (listening(5580) or listening(5581)):
        parser.error("Owned emulator ports must be free.")
    run = ROOT / ".audit" / "verification" / args.run_name
    run.mkdir(parents=True, exist_ok=False)
    sdk = Path(os.environ.get("ANDROID_HOME", "/nonexistent"))
    result = {"run": args.run_name, "stage": args.mode, "actions": [], "nativeAcceptance": False}
    native_checks_passed = False
    native_deadline = time.monotonic() + 1800 if args.mode == "native" else None
    emulator = None
    emulator_log = (run / "emulator.log").open("wb")
    stack_log = (run / "python-stacks.log").open("a", encoding="utf-8")
    faulthandler.dump_traceback_later(60, repeat=True, file=stack_log)
    env = dict(os.environ, ANDROID_AVD_HOME=str(run / "avd"), ANDROID_EMULATOR_HOME=str(run / "emulator-home"))

    def gradle_diagnostics():
        listing = subprocess.check_output(["jcmd", "-l"], env=env, timeout=15).decode()
        for line in listing.splitlines():
            if "org.gradle.launcher.daemon.bootstrap.GradleDaemon" not in line:
                continue
            pid = line.split()[0]
            with (run / ("gradle-thread-" + pid + ".log")).open("wb") as diagnostic:
                subprocess.run(["jcmd", pid, "Thread.print", "-l"], env=env, stdout=diagnostic,
                               stderr=subprocess.STDOUT, timeout=20, check=True)
            dump = (run / ("gradle-thread-" + pid + ".log")).read_text(encoding="utf-8", errors="replace")
            print("GRADLE THREAD DIAGNOSTIC\n" + dump[:24_000], flush=True)

    def command(argv, log_name, timeout=1200, input_text=""):
        arguments = [str(part) for part in argv]
        if native_deadline is not None:
            timeout = min(timeout, native_deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("Native execution exceeded its 1800-second budget.")
        deadline = time.monotonic() + timeout
        progress_count = 0
        command_id = str(time.time_ns())
        append_json_record(run / "command-events.jsonl", {
            "id": command_id, "event": "started", "log": log_name,
            "argv": arguments, "timeoutSeconds": timeout, "elapsedSeconds": 0,
        })
        print("RUN " + " ".join(arguments), flush=True)
        process = None
        with (run / log_name).open("ab") as log:
            try:
                process = subprocess.Popen(arguments, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                append_json_record(run / "command-events.jsonl", {
                    "id": command_id, "event": "spawned", "pid": process.pid,
                    "elapsedSeconds": round(time.monotonic() - (deadline - timeout), 3),
                })
                write_and_close_stdin(process, input_text)
                while process.poll() is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(arguments, timeout)
                    try:
                        process.wait(timeout=min(60, remaining))
                    except subprocess.TimeoutExpired:
                        progress_count += 1
                        tail = (run / log_name).read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
                        print("PROGRESS " + log_name + "\n" + "\n".join(tail), flush=True)
                        if log_name == "build.log" and progress_count == 2:
                            gradle_diagnostics()
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, arguments)
                append_json_record(run / "command-events.jsonl", {
                    "id": command_id, "event": "completed", "returncode": process.returncode,
                    "elapsedSeconds": round(time.monotonic() - (deadline - timeout), 3),
                })
            except BaseException as error:
                append_json_record(run / "command-events.jsonl", {
                    "id": command_id, "event": "failed", "error": str(error),
                    "elapsedSeconds": round(time.monotonic() - (deadline - timeout), 3),
                })
                raise
            finally:
                if process is not None and process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)

    def adb(*arguments, timeout=15):
        if native_deadline is not None:
            timeout = min(timeout, native_deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("Native execution exceeded its 1800-second budget.")
        return subprocess.run([str(sdk / "platform-tools" / "adb"), "-s", "emulator-5580", *arguments],
                              env=env, capture_output=True, timeout=timeout, check=True).stdout

    def retain_brief_evidence():
        captures = {}
        paths = {name: "/sdcard/Android/data/" + PACKAGE + "/files/" + name for name in
                 ("picker.png", "preview.png", "invalidated.png", "saved.png", "expected.json")}
        paths["provider.json"] = "/sdcard/Download/reading-brief.json"
        for name, path in paths.items():
            try:
                capture = subprocess.run([str(sdk / "platform-tools" / "adb"), "-s", "emulator-5580", "exec-out", "cat", path],
                                         env=env, capture_output=True, timeout=15)
                captures[name] = {"returncode": capture.returncode, "stderr": capture.stderr.decode(errors="replace")[:4000]}
                if capture.returncode == 0:
                    (run / ("brief-" + name)).write_bytes(capture.stdout)
            except (OSError, subprocess.TimeoutExpired) as error:
                captures[name] = {"error": str(error)}
        (run / "brief-captures.json").write_text(json.dumps(captures, indent=2), encoding="utf-8")

    try:
        assert shutil.which("java"), "JDK 21 is required."
        assert (sdk / "platforms" / "android-36").is_dir(), "Preinstalled compile SDK 36 required."
        command(["java", "-version"], "doctor.log", timeout=15)
        memory_command = ["free", "-m"] if platform.system() == "Linux" else ["sysctl", "hw.memsize"]
        command(memory_command, "doctor.log", timeout=15)
        if args.mode == "build":
            result["actions"].append({"action": "doctor", "compileSdk": 36, "platform": platform.system(), "stage": "build"})
            gradle_options = [
                "--console=plain", "--no-daemon", "--max-workers=3",
                "-Dorg.gradle.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=256m -XX:+HeapDumpOnOutOfMemoryError -Xmx6g -Xms512m",
                "-Pkotlin.daemon.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=320m -Xmx2g -Xms256m",
            ]
            result["actions"].append({"action": "build-memory-budget", "gradleHeapGiB": 6, "kotlinHeapGiB": 2, "maxWorkers": 3})
            generated_schema = ROOT / "core/database/schemas/com.google.samples.apps.nowinandroid.core.database.NiaDatabase/15.json"
            try:
                command([
                    "./gradlew",
                    ":core:data:testDemoDebugUnitTest",
                    ":feature:bookmarks:impl:testDemoDebugUnitTest",
                    ":feature:bookmarks:impl:lintDemoDebug",
                    ":core:database:assembleDemoDebugAndroidTest",
                    ":core:data:assembleDemoDebugAndroidTest",
                    ":app:assembleDemoDebug",
                    ":app:assembleDemoDebugAndroidTest",
                    *gradle_options,
                ], "build.log", timeout=1800)
            finally:
                if generated_schema.is_file():
                    shutil.copyfile(generated_schema, run / "room-schema-15.json")
            assert generated_schema.is_file(), "Room did not export the schema 15 snapshot."
            room_apks = list((ROOT / "core/database/build/outputs/apk/androidTest/demo/debug").glob("*-androidTest.apk"))
            assert len(room_apks) == 1, "Expected exactly one Room instrumentation APK."
            data_apks = list((ROOT / "core/data/build/outputs/apk/androidTest/demo/debug").glob("*-androidTest.apk"))
            assert len(data_apks) == 1, "Expected exactly one data instrumentation APK."
            package_apks(run / "apks", os.environ["GITHUB_SHA"], {
                "app.apk": ROOT / "app/build/outputs/apk/demo/debug/app-demo-debug.apk",
                "tests.apk": ROOT / "app/build/outputs/apk/androidTest/demo/debug/app-demo-debug-androidTest.apk",
                "room-tests.apk": room_apks[0],
                "data-tests.apk": data_apks[0],
            })
            validated_apks(run / "apks", os.environ["GITHUB_SHA"])
            result["actions"].append({
                "action": "build-and-focused-tests",
                "variant": "demoDebug",
                "tasks": [
                    ":core:data:testDemoDebugUnitTest",
                    ":feature:bookmarks:impl:testDemoDebugUnitTest",
                    ":feature:bookmarks:impl:lintDemoDebug",
                    ":core:database:assembleDemoDebugAndroidTest",
                    ":core:data:assembleDemoDebugAndroidTest",
                ],
                "roomSchema": "room-schema-15.json",
                "manifest": "apks/manifest.json",
            })
            result["buildAccepted"] = True
            return
        manifest = validated_apks(args.apk_dir, os.environ["GITHUB_SHA"])
        result["actions"].append({"action": "validate-build-artifact", "manifest": manifest})
        assert (sdk / "platform-tools" / "adb").is_file(), "Preinstalled Android platform-tools required."
        sdkmanager = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
        avdmanager = sdk / "cmdline-tools" / "latest" / "bin" / "avdmanager"
        assert sdkmanager.is_file() and avdmanager.is_file(), "Preinstalled Android command-line tools required."
        assert (sdk / "emulator" / "emulator").is_file(), "Preinstalled emulator required for the acceleration preflight."
        command([sdk / "emulator" / "emulator", "-accel-check"], "acceleration.log", timeout=30)
        result["actions"].append({"action": "doctor", "compileSdk": 36, "platform": platform.system(),
                                  "architecture": platform.machine(), "accelerationPreflightPassed": True})
        image = "system-images;android-30;aosp_atd;x86_64"
        command([sdkmanager, "emulator", image], "sdk.log", timeout=300)
        command([sdk / "emulator" / "emulator", "-version"], "emulator-version.log", timeout=15)
        command([sdk / "emulator" / "emulator", "-accel-check"], "acceleration-after-install.log", timeout=30)
        avd = "cleartrail-" + args.run_name
        avd_home = Path(env["ANDROID_AVD_HOME"])
        avd_home.mkdir()
        Path(env["ANDROID_EMULATOR_HOME"]).mkdir()
        command([avdmanager, "create", "avd", "--name", avd, "--package", image, "--device", "pixel_4"],
                "avd.log", input_text="no\n")
        avd_index = avd_home / (avd + ".ini")
        assert avd_index.is_file(), "AVD manager did not create the index in the owned directory."
        (run / "avd-index.txt").write_bytes(avd_index.read_bytes())
        command([sdk / "emulator" / "emulator", "-list-avds"], "avd-list.log", timeout=30)
        assert avd in (run / "avd-list.log").read_text(encoding="utf-8").splitlines(), "Emulator cannot discover the owned AVD."
        emulator = subprocess.Popen([str(sdk / "emulator" / "emulator"), "-avd", avd, "-port", "5580",
                                     "-no-window", "-no-audio", "-no-snapshot", "-gpu", "swiftshader_indirect",
                                     "-camera-back", "none", "-camera-front", "none", "-memory", "2048",
                                     "-accel", "on", "-show-kernel", "-logcat", "*:W", "-no-metrics"],
                                    env=env, cwd=ROOT, stdout=emulator_log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        result["actions"].append({"action": "launch-emulator", "pid": emulator.pid, "accelerated": True})
        boot_started = time.monotonic()
        deadline = min(boot_started + 900, native_deadline)
        boot_path = run / "boot-probes.jsonl"
        while time.monotonic() < deadline:
            if emulator.poll() is not None:
                raise RuntimeError("Owned emulator exited. Inspect emulator.log.")
            try:
                probe_started = time.monotonic()
                append_json_record(boot_path, {"event": "started", "elapsedSeconds": round(probe_started - boot_started, 3),
                                               "call": "getprop sys.boot_completed"})
                completed = adb("shell", "getprop", "sys.boot_completed").strip()
                append_json_record(boot_path, {"event": "completed", "elapsedSeconds": round(time.monotonic() - boot_started, 3),
                                               "call": "getprop sys.boot_completed", "output": completed.decode(errors="replace")})
                package = b""
                if completed == b"1":
                    append_json_record(boot_path, {"event": "started", "elapsedSeconds": round(time.monotonic() - boot_started, 3),
                                                   "call": "pm path android"})
                    package = adb("shell", "pm", "path", "android")
                    append_json_record(boot_path, {"event": "completed", "elapsedSeconds": round(time.monotonic() - boot_started, 3),
                                                   "call": "pm path android", "output": package.decode(errors="replace")})
                append_json_record(boot_path, {"event": "state", "elapsedSeconds": round(time.monotonic() - boot_started, 3),
                                               "deadlineSeconds": 900, "completed": completed.decode(errors="replace"),
                                               "packageReady": b"package:" in package})
                if completed == b"1" and b"package:" in package:
                    break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                append_json_record(boot_path, {"event": "failed", "elapsedSeconds": round(time.monotonic() - boot_started, 3),
                                               "error": str(error), "stderr": str(getattr(error, "stderr", b""))[:4000]})
            time.sleep(0.5)
        else:
            raise TimeoutError("Owned emulator did not complete boot within 900 seconds.")
        result["actions"].append({"action": "boot", "api": 30, "elapsedSeconds": round(time.monotonic() - boot_started, 3)})
        try:
            picker = subprocess.run([str(sdk / "platform-tools" / "adb"), "-s", "emulator-5580", "shell", "cmd", "package",
                                     "resolve-activity", "--brief", "-a", "android.intent.action.CREATE_DOCUMENT",
                                     "-c", "android.intent.category.OPENABLE", "-t", "application/json"],
                                    env=env, capture_output=True, timeout=15)
            picker_probe = {"returncode": picker.returncode, "stdout": picker.stdout.decode(errors="replace"),
                            "stderr": picker.stderr.decode(errors="replace")}
        except (OSError, subprocess.TimeoutExpired) as picker_error:
            picker_probe = {"error": str(picker_error)}
        (run / "document-picker.json").write_text(json.dumps(picker_probe, indent=2), encoding="utf-8")
        apk = args.apk_dir / "app.apk"
        adb("install", "-r", str(apk), timeout=60)
        launch = adb("shell", "am", "start", "-n", PACKAGE + "/com.google.samples.apps.nowinandroid.MainActivity", timeout=30)
        (run / "launch.txt").write_bytes(launch)
        assert b"Error" not in launch, "ActivityManager rejected the MainActivity launch. Inspect launch.txt."
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            hierarchy = adb("exec-out", "uiautomator", "dump", "/dev/tty", timeout=20)
            if PACKAGE.encode() in hierarchy and b"Now in Android" in hierarchy and b"For you" in hierarchy and b"Interests" in hierarchy:
                break
            time.sleep(0.2)
        else:
            (run / "launch-ui.xml").write_bytes(hierarchy)
            raise AssertionError("Native demo navigation did not render within 90 seconds.")
        (run / "launch-ui.xml").write_bytes(hierarchy)
        screenshot = adb("exec-out", "screencap", "-p")
        assert screenshot.startswith(b"\x89PNG\r\n\x1a\n")
        (run / "native-launch.png").write_bytes(screenshot)
        result["actions"].append({"action": "normal-app-launch", "package": PACKAGE, "nativeScreenshot": True})
        adb("install", "-r", "-t", str(args.apk_dir / "tests.apk"), timeout=60)
        instrumentation = adb("shell", "pm", "list", "instrumentation")
        (run / "instrumentation-components.txt").write_bytes(instrumentation)
        assert TEST_RUNNER.encode() in instrumentation and ("target=" + PACKAGE).encode() in instrumentation
        command([sdk / "platform-tools" / "adb", "-s", "emulator-5580", "shell", "am", "instrument", "-w", "-r", "--no-window-animation",
                 "-e", "class", TEST_CLASS, TEST_RUNNER], "instrumentation.log", timeout=900)
        counts = completed_tests((run / "instrumentation.log").read_text(encoding="utf-8"), 11, 1)
        result["actions"].append({"action": "native-navigation-tests", "class": TEST_CLASS, **counts})
        brief_class = "com.google.samples.apps.nowinandroid.ui.ReadingBriefAcceptanceTest"
        try:
            command([sdk / "platform-tools" / "adb", "-s", "emulator-5580", "shell", "am", "instrument", "-w", "-r", "--no-window-animation", "-e", "class", brief_class, TEST_RUNNER], "brief-instrumentation.log", timeout=900)
        finally:
            retain_brief_evidence()
        counts = completed_tests((run / "brief-instrumentation.log").read_text(encoding="utf-8"), 1)
        expected = (run / "brief-expected.json").read_bytes()
        actual = (run / "brief-provider.json").read_bytes()
        assert expected and actual == expected, "Real document provider bytes differ from the reviewed preview."
        for name in ("picker.png", "preview.png", "invalidated.png", "saved.png"):
            assert (run / ("brief-" + name)).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "Missing native brief screenshot."
        result["actions"].append({"action": "native-brief-export", "class": brief_class, "sha256": hashlib.sha256(actual).hexdigest(), **counts})
        adb("install", "-r", "-t", str(args.apk_dir / "room-tests.apk"), timeout=60)
        instrumentation = adb("shell", "pm", "list", "instrumentation").decode()
        (run / "room-instrumentation-components.txt").write_text(instrumentation, encoding="utf-8")
        room_runners = re.findall(r"^instrumentation:(\S+/androidx\.test\.runner\.AndroidJUnitRunner) \(target=(\S+)\)\r?$", instrumentation, re.MULTILINE)
        room_runners = [(runner, target) for runner, target in room_runners if runner.split("/")[0].startswith("com.google.samples.apps.nowinandroid.core.database")]
        assert len(room_runners) == 1, "Expected exactly one Room instrumentation component and target."
        room_runner, room_target = room_runners[0]
        (run / "room-component.txt").write_text(room_runner + " target=" + room_target + "\n", encoding="utf-8")
        room_classes = ["com.google.samples.apps.nowinandroid.core.database.ReadingBriefMigrationTest", "com.google.samples.apps.nowinandroid.core.database.dao.ReadingBriefDraftDaoTest"]
        for index, room_class in enumerate(room_classes):
            log = "room-instrumentation-" + str(index) + ".log"
            command([sdk / "platform-tools" / "adb", "-s", "emulator-5580", "shell", "am", "instrument", "-w", "-r", "--no-window-animation", "-e", "class", room_class, room_runner], log, timeout=900)
            counts = completed_tests((run / log).read_text(encoding="utf-8"), 1)
            result["actions"].append({"action": "native-room-test", "class": room_class, **counts})
        adb("install", "-r", "-t", str(args.apk_dir / "data-tests.apk"), timeout=60)
        instrumentation = adb("shell", "pm", "list", "instrumentation").decode()
        (run / "data-instrumentation-components.txt").write_text(instrumentation, encoding="utf-8")
        data_runners = re.findall(r"^instrumentation:(\S+/com\.google\.samples\.apps\.nowinandroid\.core\.data\.repository\.RepositoryTestRunner) \(target=(\S+)\)\r?$", instrumentation, re.MULTILINE)
        assert len(data_runners) == 1, "Expected exactly one data instrumentation component and target."
        data_runner, data_target = data_runners[0]
        (run / "data-component.txt").write_text(data_runner + " target=" + data_target + "\n", encoding="utf-8")
        repository_class = "com.google.samples.apps.nowinandroid.core.data.repository.ReadingBriefRepositoryReopenTest"
        process_ids = []
        for method in ("writeDraft", "readDraftAfterProcessRestart"):
            log = "data-" + method + ".log"
            command([sdk / "platform-tools" / "adb", "-s", "emulator-5580", "shell", "am", "instrument", "-w", "-r", "--no-window-animation", "-e", "class", repository_class + "#" + method, data_runner], log, timeout=900)
            output = (run / log).read_text(encoding="utf-8")
            counts = completed_tests(output, 1)
            process_id = re.findall(r"^INSTRUMENTATION_STATUS: cleartrailProcessId=(\d+)\s*$", output, re.MULTILINE)
            assert len(process_id) == 1, "Repository instrumentation did not report its process ID."
            process_ids.append(process_id[0])
            result["actions"].append({"action": "native-repository-test", "method": method, "processId": process_id[0], **counts})
        assert process_ids[0] != process_ids[1], "Repository reopen test did not use a new process."
        native_checks_passed = True
    except BaseException as error:
        result["error"] = str(error)
        if emulator is not None:
            probes = {}
            for name, arguments in [
                ("devices", ["devices", "-l"]),
                ("properties", ["-s", "emulator-5580", "shell", "getprop"]),
                ("processes", ["-s", "emulator-5580", "shell", "ps", "-A"]),
                ("logcat", ["-s", "emulator-5580", "logcat", "-d", "-t", "200"]),
                ("hierarchy", ["-s", "emulator-5580", "exec-out", "uiautomator", "dump", "/dev/tty"]),
                ("screen", ["-s", "emulator-5580", "exec-out", "screencap", "-p"]),
            ]:
                try:
                    probe = subprocess.run([str(sdk / "platform-tools" / "adb"), *arguments], env=env,
                                           capture_output=True, timeout=10)
                    probes[name] = {"returncode": probe.returncode, "stderr": probe.stderr.decode(errors="replace")[:4000]}
                    if name == "screen":
                        if probe.returncode == 0 and probe.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                            (run / "failure-screen.png").write_bytes(probe.stdout)
                            probes[name]["pngRetained"] = True
                    else:
                        (run / ("failure-" + name + ".log")).write_bytes(probe.stdout)
                except (OSError, subprocess.TimeoutExpired) as probe_error:
                    probes[name] = {"error": str(probe_error)}
            (run / "failure-probes.json").write_text(json.dumps(probes, indent=2), encoding="utf-8")
        raise
    finally:
        primary_error = sys.exc_info()[1]
        emulator_stopped = False
        cleanup_error = None
        try:
            if emulator is not None and emulator.poll() is None:
                os.killpg(emulator.pid, signal.SIGTERM)
                try:
                    emulator.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(emulator.pid, signal.SIGKILL)
                    emulator.wait(timeout=10)
            if emulator is None:
                emulator_stopped = True
            else:
                deadline = time.monotonic() + 10
                while listening(5580) and time.monotonic() < deadline:
                    time.sleep(0.1)
                emulator_stopped = not listening(5580) and emulator.poll() is not None
                if not emulator_stopped:
                    cleanup_error = "Owned emulator did not stop."
        except BaseException as error:
            cleanup_error = str(error) or type(error).__name__
        finally:
            faulthandler.cancel_dump_traceback_later()
            stack_log.close()
            emulator_log.close()
            if args.mode == "native":
                finalize_native_receipt(result, run, native_checks_passed, emulator_stopped, cleanup_error)
            else:
                result["cleanup"] = {"emulatorStopped": emulator_stopped, "evidenceRetained": (run / "build.log").is_file()}
                if cleanup_error:
                    result["cleanup"]["error"] = cleanup_error
            (run / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("EVIDENCE " + str(run / "result.json"), flush=True)
        if primary_error is None:
            if cleanup_error:
                raise RuntimeError("Cleanup failed: " + cleanup_error)
            if args.mode == "native" and not result["nativeAcceptance"]:
                raise RuntimeError("Native evidence was not retained. Inspect result.json.")


if __name__ == "__main__":
    main()
