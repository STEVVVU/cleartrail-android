import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("cleartrail_verifier", Path(__file__).with_name("verify-cleartrail.py"))
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


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
        self.artifacts = self.root / "artifacts"
        verifier.package_apks(self.artifacts, self.source, {"app.apk": app, "tests.apk": tests})

    def test_same_commit_and_exact_bytes_are_accepted(self):
        self.assertEqual(verifier.validated_apks(self.artifacts, self.source)["sourceCommit"], self.source)

    def test_foreign_commit_is_rejected(self):
        with self.assertRaises(ValueError):
            verifier.validated_apks(self.artifacts, "b" * 40)

    def test_modified_apk_is_rejected(self):
        (self.artifacts / "app.apk").write_bytes(b"different bytes")
        with self.assertRaises(ValueError):
            verifier.validated_apks(self.artifacts, self.source)

    def test_unsupported_schema_is_rejected(self):
        for schema in [2, True, 1.0]:
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


class InstrumentationBoundaryTests(unittest.TestCase):
    def test_completed_class_with_existing_ignore_is_accepted(self):
        output = "INSTRUMENTATION_STATUS_CODE: -3\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n"
        self.assertEqual(verifier.completed_navigation_tests(output), {"completedTests": 11, "ignoredTests": 1})

    def test_shell_success_does_not_hide_test_failure(self):
        for output in [
            "FAILURES!!!\nINSTRUMENTATION_CODE: -1\n",
            "INSTRUMENTATION_STATUS_CODE: -2\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n",
            "INSTRUMENTATION_STATUS_CODE: -1\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n",
            "INSTRUMENTATION_FAILED: process crashed\nOK (11 tests)\nINSTRUMENTATION_CODE: -1\n",
        ]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                verifier.completed_navigation_tests(output)

    def test_missing_or_truncated_execution_is_rejected(self):
        for output in ["", "OK (0 tests)\nINSTRUMENTATION_CODE: -1\n", "OK (10 tests)\nINSTRUMENTATION_CODE: -1\n", "OK (11 tests)\n"]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                verifier.completed_navigation_tests(output)

    def test_additional_ignored_test_is_rejected(self):
        with self.assertRaises(ValueError):
            verifier.completed_navigation_tests("INSTRUMENTATION_STATUS_CODE: -3\n" * 2 + "OK (11 tests)\nINSTRUMENTATION_CODE: -1\n")


if __name__ == "__main__":
    unittest.main()
