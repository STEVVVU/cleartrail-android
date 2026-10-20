"""Hosted native Android verification; no UI automation on the user's computer."""

import argparse
import json
import os
from pathlib import Path
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
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.name != "posix":
        parser.error("Native driving requires the dedicated Linux hosted workflow. No local SDK/device is configured.")
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

    def command(argv, log_name, timeout=1200, input_text=""):
        with (run / log_name).open("ab") as log:
            subprocess.run([str(part) for part in argv], cwd=ROOT, env=env,
                           input=input_text.encode(), stdout=log, stderr=subprocess.STDOUT,
                           timeout=timeout, check=True)

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
        accelerated = os.access("/dev/kvm", os.R_OK | os.W_OK)
        result["actions"].append({"action": "doctor", "compileSdk": 36, "kvmAccessible": accelerated})
        command(["./gradlew", ":app:assembleDemoDebug", ":app:assembleDemoDebugAndroidTest", "--console=plain", "--no-daemon"],
                "build.log", timeout=1800)
        result["actions"].append({"action": "build", "variant": "demoDebug"})
        image = "system-images;android-30;aosp_atd;x86_64"
        command([sdkmanager, "emulator", image], "sdk.log", timeout=300)
        avd = "cleartrail-" + args.run_name
        command([avdmanager, "create", "avd", "--name", avd, "--package", image, "--device", "pixel_4"],
                "avd.log", input_text="no\n")
        emulator = subprocess.Popen([str(sdk / "emulator" / "emulator"), "-avd", avd, "-port", "5580",
                                     "-no-window", "-no-audio", "-no-snapshot", "-gpu", "swiftshader_indirect",
                                     "-camera-back", "none", "-camera-front", "none", "-memory", "2048",
                                     "-accel", "on" if accelerated else "off"],
                                    env=env, cwd=ROOT, stdout=emulator_log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        result["actions"].append({"action": "launch-emulator", "pid": emulator.pid, "accelerated": accelerated})
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if emulator.poll() is not None:
                raise RuntimeError("Owned emulator exited. Inspect emulator.log.")
            try:
                if adb("shell", "getprop", "sys.boot_completed").strip() == b"1" and b"package:" in adb("shell", "pm", "path", "android"):
                    break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
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
                 "--console=plain", "--no-daemon"], "instrumentation.log", timeout=900)
        result["actions"].append({"action": "native-navigation-tests", "class": test_class})
        result["nativeAcceptance"] = True
    except BaseException as error:
        result["error"] = str(error)
        raise
    finally:
        try:
            if emulator is not None and emulator.poll() is None:
                os.killpg(emulator.pid, signal.SIGTERM)
                emulator.wait(timeout=30)
            deadline = time.monotonic() + 10
            while listening(5580) and time.monotonic() < deadline:
                time.sleep(0.1)
            result["cleanup"] = {"emulatorStopped": not listening(5580), "evidenceRetained": True}
        finally:
            emulator_log.close()
            (run / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("EVIDENCE " + str(run / "result.json"), flush=True)


if __name__ == "__main__":
    main()
