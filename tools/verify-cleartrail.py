"""Hosted native Android verification; no UI automation on the user's computer."""

import argparse
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


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_name")
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or platform.system() not in ("Linux", "Darwin") or platform.machine() != "x86_64":
        parser.error("Use the dedicated x86_64 Linux/Intel macOS hosted workflow. No local SDK/device is configured.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", args.run_name):
        parser.error("Use a short alphanumeric run name.")
    if listening(5580) or listening(5581):
        parser.error("Owned emulator ports must be free.")
    run = ROOT / ".audit" / "verification" / args.run_name
    run.mkdir(parents=True, exist_ok=False)
    sdk = Path(os.environ.get("ANDROID_HOME", "/nonexistent"))
    result = {"run": args.run_name, "actions": [], "nativeAcceptance": False}
    emulator = None
    emulator_log = (run / "emulator.log").open("wb")
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
        print("RUN " + " ".join(arguments), flush=True)
        deadline = time.monotonic() + timeout
        progress_count = 0
        with (run / log_name).open("ab") as log:
            process = subprocess.Popen(arguments, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                process.stdin.write(input_text.encode())
                process.stdin.close()
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
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)

    def adb(*arguments, timeout=15):
        return subprocess.run([str(sdk / "platform-tools" / "adb"), "-s", "emulator-5580", *arguments],
                              env=env, capture_output=True, timeout=timeout, check=True).stdout

    try:
        assert shutil.which("java"), "JDK 21 is required."
        assert (sdk / "platform-tools" / "adb").is_file(), "Preinstalled Android platform-tools required."
        assert (sdk / "platforms" / "android-36").is_dir(), "Preinstalled compile SDK 36 required."
        sdkmanager = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
        avdmanager = sdk / "cmdline-tools" / "latest" / "bin" / "avdmanager"
        assert sdkmanager.is_file() and avdmanager.is_file(), "Preinstalled Android command-line tools required."
        command(["java", "-version"], "doctor.log", timeout=15)
        memory_command = ["free", "-m"] if platform.system() == "Linux" else ["sysctl", "hw.memsize"]
        command(memory_command, "doctor.log", timeout=15)
        assert (sdk / "emulator" / "emulator").is_file(), "Preinstalled emulator required for the acceleration preflight."
        command([sdk / "emulator" / "emulator", "-accel-check"], "acceleration.log", timeout=30)
        result["actions"].append({"action": "doctor", "compileSdk": 36, "platform": platform.system(),
                                  "architecture": platform.machine(), "accelerationPreflightPassed": True})
        gradle_options = [
            "--console=plain", "--no-daemon", "--max-workers=3",
            "-Dorg.gradle.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=256m -XX:+HeapDumpOnOutOfMemoryError -Xmx6g -Xms512m",
            "-Pkotlin.daemon.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=320m -Xmx2g -Xms256m",
        ]
        result["actions"].append({"action": "build-memory-budget", "gradleHeapGiB": 6, "kotlinHeapGiB": 2, "maxWorkers": 3})
        command(["./gradlew", ":app:assembleDemoDebug", ":app:assembleDemoDebugAndroidTest", *gradle_options],
                "build.log", timeout=1800)
        result["actions"].append({"action": "build", "variant": "demoDebug"})
        image = "system-images;android-30;aosp_atd;x86_64"
        command([sdkmanager, "emulator", image], "sdk.log", timeout=300)
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
                                     "-accel", "on"],
                                    env=env, cwd=ROOT, stdout=emulator_log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        result["actions"].append({"action": "launch-emulator", "pid": emulator.pid, "accelerated": True})
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if emulator.poll() is not None:
                raise RuntimeError("Owned emulator exited. Inspect emulator.log.")
            try:
                completed = adb("shell", "getprop", "sys.boot_completed").strip()
                package = adb("shell", "pm", "path", "android") if completed == b"1" else b""
                (run / "boot-probe.json").write_text(json.dumps({"completed": completed.decode(errors="replace"),
                                                                "package": package.decode(errors="replace")}), encoding="utf-8")
                if completed == b"1" and b"package:" in package:
                    break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                (run / "boot-probe.json").write_text(json.dumps({"error": str(error),
                                                                "stderr": str(getattr(error, "stderr", b""))[:4000]}), encoding="utf-8")
            time.sleep(0.5)
        else:
            raise TimeoutError("Owned emulator did not complete boot within 300 seconds.")
        result["actions"].append({"action": "boot", "api": 30})
        apk = ROOT / "app/build/outputs/apk/demo/debug/app-demo-debug.apk"
        assert apk.is_file(), "Expected demo debug APK is missing."
        adb("install", "-r", str(apk), timeout=60)
        launch = adb("shell", "am", "start", "-W", "-n", PACKAGE + "/com.google.samples.apps.nowinandroid.MainActivity", timeout=30)
        (run / "launch.txt").write_bytes(launch)
        assert b"Error" not in launch and b"Status: ok" in launch
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            hierarchy = adb("exec-out", "uiautomator", "dump", "/dev/tty", timeout=20)
            if b"Now in Android" in hierarchy and b"For you" in hierarchy and b"Interests" in hierarchy:
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
        test_class = "com.google.samples.apps.nowinandroid.ui.NavigationTest"
        command(["./gradlew", ":app:connectedDemoDebugAndroidTest",
                 "-Pandroid.testInstrumentationRunnerArguments.class=" + test_class,
                 *gradle_options], "instrumentation.log", timeout=900)
        result["actions"].append({"action": "native-navigation-tests", "class": test_class})
        result["nativeAcceptance"] = True
    except BaseException as error:
        result["error"] = str(error)
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
            emulator_log.close()
            (run / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("EVIDENCE " + str(run / "result.json"), flush=True)
        if not result["cleanup"]["emulatorStopped"]:
            raise RuntimeError("Owned emulator did not stop. Inspect result.json and emulator.log.")


if __name__ == "__main__":
    main()
