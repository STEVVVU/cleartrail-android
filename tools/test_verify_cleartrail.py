import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib


spec = importlib.util.spec_from_file_location("cleartrail_verifier", Path(__file__).with_name("verify-cleartrail.py"))
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def sample_png(pixel):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\0" + pixel)) + chunk(b"IEND", b""))


def filtered_png(method):
    rows = [bytes((0, 0, 0, 255, 0, 0, 0, 255)), bytes((0, 0, 0, 255, 2, 3, 4, 255))]
    previous = bytes(8)
    raw = bytearray()
    for row in rows:
        raw.append(method)
        for i, value in enumerate(row):
            left = row[i - 4] if i >= 4 else 0
            above = previous[i]
            upper_left = previous[i - 4] if i >= 4 else 0
            p = left + above - upper_left
            choices = (left, above, upper_left)
            distances = tuple(abs(p - choice) for choice in choices)
            predictor = (0, left, above, (left + above) // 2, choices[distances.index(min(distances))])[method]
            raw.append((value - predictor) & 255)
        previous = row
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ArtifactBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="cleartrail-tool-tests-")
        self.root = Path(self.scratch.name).resolve()
        self.assertEqual(self.root.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.scratch.cleanup)
        self.source = "a" * 40
        app = self.root / "producer-app.apk"
        tests = self.root / "producer-tests.apk"
        app.write_bytes(b"synthetic app bytes for integrity validation only")
        tests.write_bytes(b"synthetic test bytes for integrity validation only")
        room_tests = self.root / "producer-room-tests.apk"
        room_tests.write_bytes(b"synthetic Room test bytes")
        data_tests = self.root / "producer-data-tests.apk"
        data_tests.write_bytes(b"synthetic data test bytes")
        self.artifacts = self.root / "artifacts"
        verifier.package_apks(self.artifacts, self.source, {"app.apk": app, "tests.apk": tests, "room-tests.apk": room_tests, "data-tests.apk": data_tests})

    def test_same_commit_and_exact_bytes_are_accepted(self):
        self.assertEqual(verifier.validated_apks(self.artifacts, self.source)["sourceCommit"], self.source)

    def test_json_records_append_without_replacing_prior_evidence(self):
        path = self.root / "events.jsonl"
        verifier.append_json_record(path, {"event": "started"})
        verifier.append_json_record(path, {"event": "completed"})
        self.assertEqual([json.loads(line)["event"] for line in path.read_text().splitlines()], ["started", "completed"])

    def test_foreign_commit_is_rejected(self):
        with self.assertRaises(ValueError):
            verifier.validated_apks(self.artifacts, "b" * 40)

    def test_modified_apk_is_rejected(self):
        for name in ("app.apk", "tests.apk", "room-tests.apk", "data-tests.apk"):
            with self.subTest(name=name):
                path = self.artifacts / name
                original = path.read_bytes()
                path.write_bytes(b"different bytes")
                with self.assertRaises(ValueError):
                    verifier.validated_apks(self.artifacts, self.source)
                path.write_bytes(original)

    def test_unsupported_schema_is_rejected(self):
        for schema in [2, True, 3.0]:
            with self.subTest(schema=schema):
                self.change_manifest(lambda value: value.update(schemaVersion=schema))
                with self.assertRaises(ValueError):
                    verifier.validated_apks(self.artifacts, self.source)

    def test_unexpected_file_name_is_rejected(self):
        self.change_manifest(lambda value: value["files"].update({"../outside.apk": "0" * 64}))
        with self.assertRaises(ValueError):
            verifier.validated_apks(self.artifacts, self.source)

    def change_manifest(self, update):
        path = self.artifacts / "manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        update(value)
        path.write_text(json.dumps(value), encoding="utf-8")


class ProcessInputTests(unittest.TestCase):
    def test_stdin_closes_even_when_write_fails(self):
        class FailingInput:
            closed = False

            def write(self, _value):
                raise BrokenPipeError("child closed stdin")

            def close(self):
                self.closed = True

        process = type("Process", (), {})()
        process.stdin = FailingInput()
        with self.assertRaises(BrokenPipeError):
            verifier.write_and_close_stdin(process, "no\n")
        self.assertTrue(process.stdin.closed)


class InstallEvidenceTests(unittest.TestCase):
    def test_timeout_preserves_partial_output_and_propagates_failure(self):
        with tempfile.TemporaryDirectory(prefix="cleartrail-install-tests-") as scratch:
            receipt = Path(scratch) / "installs.jsonl"
            error = verifier.subprocess.TimeoutExpired(["adb"], 60, output=b"partial output", stderr=b"partial error")
            with patch.object(verifier.subprocess, "run", side_effect=error), self.assertRaises(verifier.subprocess.TimeoutExpired):
                verifier.install_apk(Path("adb"), Path("tests.apk"), True, {}, receipt, 60)
            started, failed = [json.loads(line) for line in receipt.read_text().splitlines()]
            self.assertEqual(started["event"], "started")
            self.assertIn("-t", started["argv"])
            self.assertEqual(failed["event"], "failed")
            self.assertEqual(failed["stdout"], "partial output")
            self.assertEqual(failed["stderr"], "partial error")
            self.assertGreaterEqual(failed["elapsedSeconds"], 0)

    def test_completed_install_preserves_output(self):
        with tempfile.TemporaryDirectory(prefix="cleartrail-install-tests-") as scratch:
            receipt = Path(scratch) / "installs.jsonl"
            completed = verifier.subprocess.CompletedProcess(["adb"], 0, b"Success\n", b"")
            with patch.object(verifier.subprocess, "run", return_value=completed):
                verifier.install_apk(Path("adb"), Path("app.apk"), False, {}, receipt, 60)
            started, done = [json.loads(line) for line in receipt.read_text().splitlines()]
            self.assertNotIn("-t", started["argv"])
            self.assertEqual(done["stdout"], "Success\n")
            self.assertEqual(done["returncode"], 0)


class NativeReceiptTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="cleartrail-receipt-tests-")
        self.addCleanup(self.scratch.cleanup)
        self.run = Path(self.scratch.name)
        for name in verifier.NATIVE_FILES:
            (self.run / name).write_bytes(b"evidence")
        for name in verifier.NATIVE_PNGS:
            (self.run / name).write_bytes(sample_png(b"\xff\x00\x00\xff"))

    def test_acceptance_requires_completed_cleanup_and_retained_evidence(self):
        result = {"nativeAcceptance": False}
        verifier.finalize_native_receipt(result, self.run, True, True)
        self.assertTrue(result["nativeAcceptance"])
        self.assertTrue(result["cleanup"]["evidenceRetained"])
        verifier.finalize_native_receipt(result, self.run, False, True)
        self.assertFalse(result["nativeAcceptance"])

    def test_cleanup_failure_cannot_accept_or_erase_primary_error(self):
        result = {"nativeAcceptance": True, "error": "original instrumentation failure"}
        verifier.finalize_native_receipt(result, self.run, True, False, "emulator still running")
        self.assertFalse(result["nativeAcceptance"])
        self.assertEqual(result["error"], "original instrumentation failure")
        self.assertEqual(result["cleanup"]["error"], "emulator still running")
        self.assertTrue(result["cleanup"]["evidenceRetained"])

        result = {"nativeAcceptance": True}
        verifier.finalize_native_receipt(result, self.run, True, False, "emulator still running")
        self.assertFalse(result["nativeAcceptance"])
        self.assertEqual(result["cleanup"]["error"], "emulator still running")

    def test_missing_screenshot_cannot_accept(self):
        (self.run / "brief-preview.png").unlink()
        result = {"nativeAcceptance": True}
        verifier.finalize_native_receipt(result, self.run, True, True)
        self.assertFalse(result["nativeAcceptance"])
        self.assertFalse(result["cleanup"]["evidenceRetained"])
        self.assertIn("brief-preview.png", result["cleanup"]["missingEvidence"])

    def test_black_or_truncated_screenshot_cannot_accept(self):
        for data in (sample_png(b"\0\0\0\xff"), b"\x89PNG\r\n\x1a\n"):
            with self.subTest(data=data):
                (self.run / "native-launch.png").write_bytes(data)
                result = {"nativeAcceptance": True}
                verifier.finalize_native_receipt(result, self.run, True, True)
                self.assertFalse(result["nativeAcceptance"])
                self.assertIn("native-launch.png", result["cleanup"]["missingEvidence"])

    def test_screenshot_decoder_accepts_png_row_filters(self):
        for method in range(5):
            with self.subTest(method=method):
                path = self.run / "filtered.png"
                path.write_bytes(filtered_png(method))
                self.assertTrue(verifier.visible_screenshot(path))

    def test_changed_provider_bytes_cannot_accept(self):
        (self.run / "brief-provider.json").write_bytes(b"different")
        result = {"nativeAcceptance": True}
        verifier.finalize_native_receipt(result, self.run, True, True)
        self.assertFalse(result["nativeAcceptance"])
        self.assertIn("provider bytes differ from preview", result["cleanup"]["missingEvidence"])


class InstrumentationBoundaryTests(unittest.TestCase):
    def test_completed_class_with_existing_ignore_is_accepted(self):
        output = "INSTRUMENTATION_STATUS_CODE: -3\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n"
        self.assertEqual(verifier.completed_tests(output, 11, 1), {"completedTests": 11, "ignoredTests": 1})

    def test_shell_success_does_not_hide_test_failure(self):
        for output in [
            "FAILURES!!!\nINSTRUMENTATION_CODE: -1\n",
            "INSTRUMENTATION_STATUS_CODE: -2\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n",
            "INSTRUMENTATION_STATUS_CODE: -1\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n",
            "INSTRUMENTATION_FAILED: process crashed\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n",
        ]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                verifier.completed_tests(output, 11, 1)

    def test_missing_or_truncated_execution_is_rejected(self):
        for output in ["", "OK (0 tests)\nINSTRUMENTATION_CODE: -1\n", "OK (10 tests)\nINSTRUMENTATION_CODE: -1\n", "OK (11 tests)\n"]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                verifier.completed_tests(output, 11, 1)

    def test_additional_ignored_test_is_rejected(self):
        with self.assertRaises(ValueError):
            verifier.completed_tests("INSTRUMENTATION_STATUS_CODE: -3\n" * 2 + "OK (11 tests)\nINSTRUMENTATION_CODE: -1\n", 11, 1)

    def test_room_requires_a_completed_nonignored_test(self):
        self.assertEqual(verifier.completed_tests("OK (1 test)\nINSTRUMENTATION_CODE: -1\n", 1), {"completedTests": 1, "ignoredTests": 0})
        with self.assertRaises(ValueError):
            verifier.completed_tests("INSTRUMENTATION_STATUS_CODE: -3\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n", 1)


if __name__ == "__main__":
    unittest.main()
