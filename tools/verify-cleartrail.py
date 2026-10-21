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
import time


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "com.google.samples.apps.nowinandroid.demo.debug"
TEST_CLASS = "com.google.samples.apps.nowinandroid.ui.NavigationTest"
TEST_RUNNER = PACKAGE + ".test/com.google.samples.apps.nowinandroid.core.testing.NiaTestRunner"


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
    manifest = {"schemaVersion": 1, "sourceCommit": source_commit, "files": {}}
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
    if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1 or manifest.get("sourceCommit") != source_commit:
        raise ValueError("APK manifest schema or source commit does not match this workflow.")
    if not source_commit or set(manifest.get("files", {})) != {"app.apk", "tests.apk"}:
        raise ValueError("APK manifest must name exactly the app and test APKs.")
    for name, digest in manifest["files"].items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("APK integrity check failed for " + name)
    return manifest


def completed_navigation_tests(output):
    count = re.search(r"^OK \((\d+) tests?\)\s*$", output, re.MULTILINE)
    completed = re.search(r"^INSTRUMENTATION_CODE:\s*-1\s*$", output, re.MULTILINE)
    failures = re.search(r"^INSTRUMENTATION_STATUS_CODE:\s*-(?:1|2|4)\s*$", output, re.MULTILINE)
    ignored = len(re.findall(r"^INSTRUMENTATION_STATUS_CODE:\s*-3\s*$", output, re.MULTILINE))
    if not count or int(count[1]) < 11 or not completed or failures or ignored > 1 or "FAILURES!!!" in output or "INSTRUMENTATION_FAILED" in output:
        raise ValueError("Navigation instrumentation did not complete the mapped test class successfully. Inspect instrumentation.log.")
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
        return subprocess.run([str(sdk / "platform-tools" / "adb"), "-s", "emulator-5580", *arguments],
                              env=env, capture_output=True, timeout=timeout, check=True).stdout

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
            command(["./gradlew", ":app:assembleDemoDebug", ":app:assembleDemoDebugAndroidTest", *gradle_options],
                    "build.log", timeout=1800)
            package_apks(run / "apks", os.environ["GITHUB_SHA"], {
                "app.apk": ROOT / "app/build/outputs/apk/demo/debug/app-demo-debug.apk",
                "tests.apk": ROOT / "app/build/outputs/apk/androidTest/demo/debug/app-demo-debug-androidTest.apk",
            })
            validated_apks(run / "apks", os.environ["GITHUB_SHA"])
            result["actions"].append({"action": "build", "variant": "demoDebug", "manifest": "apks/manifest.json"})
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
        deadline = boot_started + 900
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
        counts = completed_navigation_tests((run / "instrumentation.log").read_text(encoding="utf-8"))
        result["actions"].append({"action": "native-navigation-tests", "class": TEST_CLASS, **counts})
        result["nativeAcceptance"] = True
    except BaseException as error:
        result["error"] = str(error)
        if emulator is not None:
            probes = {}
            for name, arguments in [
                ("devices", ["devices", "-l"]),
                ("properties", ["-s", "emulator-5580", "shell", "getprop"]),
                ("processes", ["-s", "emulator-5580", "shell", "ps", "-A"]),
                ("logcat", ["-s", "emulator-5580", "logcat", "-d", "-t", "200"]),
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
        result["cleanup"] = {"emulatorStopped": False, "evidenceRetained": run.exists()}
        try:
            if emulator is not None and emulator.poll() is None:
                os.killpg(emulator.pid, signal.SIGTERM)
                try:
                    emulator.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(emulator.pid, signal.SIGKILL)
                    emulator.wait(timeout=10)
            deadline = time.monotonic() + 10
            while listening(5580) and time.monotonic() < deadline:
                time.sleep(0.1)
            result["cleanup"]["emulatorStopped"] = not listening(5580) and (emulator is None or emulator.poll() is not None)
        finally:
            faulthandler.cancel_dump_traceback_later()
            stack_log.close()
            emulator_log.close()
            (run / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("EVIDENCE " + str(run / "result.json"), flush=True)
        if not result["cleanup"]["emulatorStopped"]:
            raise RuntimeError("Owned emulator did not stop. Inspect result.json and emulator.log.")


if __name__ == "__main__":
    main()
