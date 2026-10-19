import json
import subprocess
import sys
import unittest

from router_core.privacy import (Consent, PrivacyError, SYNTHETIC_SMOKE,
                                 build_task_description)


class PrivacyTests(unittest.TestCase):
    def build(self, text, **kwargs):
        return build_task_description(text, consent=Consent.REAL_TASKS, **kwargs)

    def test_no_consent_never_yields_payload(self):
        with self.assertRaisesRegex(PrivacyError, "no_consent"):
            build_task_description("private project task")

    def test_synthetic_consent_requires_exact_registered_fixture(self):
        description = build_task_description(SYNTHETIC_SMOKE, consent=Consent.SYNTHETIC)
        self.assertEqual(description.text, SYNTHETIC_SMOKE)
        for task in ("private project task", SYNTHETIC_SMOKE + " private code"):
            with self.assertRaisesRegex(PrivacyError, "synthetic_fixture_not_authorized"):
                build_task_description(task, consent=Consent.SYNTHETIC)

    def test_injected_synthetic_registry_is_explicit_immutable_fixture_set(self):
        result = build_task_description("invented fixture", consent=Consent.SYNTHETIC,
                                        synthetic_tasks=frozenset({"invented fixture"}))
        self.assertEqual(result.text, "invented fixture")
        with self.assertRaises(PrivacyError):
            build_task_description("invented fixture", consent=Consent.SYNTHETIC,
                                   synthetic_tasks=["invented fixture"])

    def test_common_credentials_are_absent_from_payload_and_repr(self):
        values = ["sk-proj-abcdefgh12345678", "ghp_123456789abcdefgh", "AKIAABCDEFGHIJKLMNOP",  # gitleaks:allow -- synthetic redaction fixture
                  "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
                  "supersecret"]
        tasks = [f"Inspect auth using {values[0]}", f"Search with {values[1]}",
                 f"Audit AWS {values[2]}", f"Explain JWT {values[3]}",
                 'Update with TYPESAFE_API_KEY="supersecret"',
                 'Update {"password": "supersecret"}',
                 'Use Authorization: Bearer supersecret',
                 'Connect postgres://admin:supersecret@localhost/db',
                 "-----BEGIN PRIVATE KEY-----\nsupersecret\n-----END PRIVATE KEY-----"]  # gitleaks:allow -- invalid synthetic PEM, not a key
        for task in tasks:
            with self.subTest(task=task):
                result = self.build(task)
                for value in values:
                    self.assertNotIn(value, result.text)
                    self.assertNotIn(value, repr(result))
                self.assertGreater(result.redactions, 0)

    def test_quoted_and_multiline_secrets(self):
        text = 'Fix auth password="very private phrase"\n-----BEGIN RSA PRIVATE KEY-----\nabcdef'  # gitleaks:allow -- invalid synthetic PEM
        result = self.build(text)
        for value in ("very private phrase", "abcdef"):
            self.assertNotIn(value, result.text)

    def test_escaped_quoted_assignments_redact_the_entire_value(self):
        import json
        for value in ('prefix"SYNTHETIC_SECRET_TAIL', "prefix'SYNTHETIC_SECRET_TAIL",
                      'prefix\\"SYNTHETIC_SECRET_TAIL', 'prefix\\\\SYNTHETIC_SECRET_TAIL',
                      'prefix\nSYNTHETIC_SECRET_TAIL', 'prefix\tSYNTHETIC_SECRET_TAIL'):
            with self.subTest(value=value):
                raw = 'Inspect configuration ' + json.dumps({'password': value}) + ' then review tests'
                result = self.build(raw)
                self.assertNotIn('SYNTHETIC_SECRET_TAIL', result.text)
                self.assertIn('then review tests', result.text)
                self.assertGreater(result.redactions, 0)
        for raw in ('password="prefix\\"SYNTHETIC_SECRET_TAIL" after',
                    "password='prefix\\'SYNTHETIC_SECRET_TAIL' after",
                    'password="prefix\nSYNTHETIC_SECRET_TAIL" after',
                    'password="SYNTHETIC_SECRET_TAIL',
                    'password="SYNTHETIC_SECRET_TAIL\\'):
            with self.subTest(raw=raw):
                self.assertNotIn('SYNTHETIC_SECRET_TAIL', self.build(raw).text)

    def test_code_fences_removed_including_unterminated(self):
        for fence in ("```", "~~~"):
            for suffix in ("", f"\n{fence}\nWrite unit tests"):
                result = self.build(f"Review the authentication boundary\n{fence}python\nPRIVATE_CODE{suffix}")
                self.assertNotIn("PRIVATE_CODE", result.text)
                self.assertTrue(result.omitted_code)
                self.assertIn("authentication boundary", result.text)

    def test_redaction_before_truncation_avoids_partial_key(self):
        result = self.build("Fix " + "sk-proj-" + "secret"*1000, max_bytes=64)
        self.assertNotIn("secret", result.text)
        self.assertFalse(result.truncated)

    def test_byte_bounded_unicode_truncation(self):
        result = self.build("Implement " + "á"*100, max_bytes=64)
        self.assertLessEqual(len(result.text.encode()), 64)
        self.assertTrue(result.truncated)
        self.assertTrue(result.text.endswith("[truncated]"))

    def test_metadata_contains_no_text_and_payload_is_minimal(self):
        result = self.build("Fix the private concurrency regression")
        self.assertNotIn("private", json.dumps(result.safe_metadata()))
        self.assertNotIn("private", repr(result))
        self.assertEqual(set(result.provider_state()), {"task_summary"})

    def test_size_types_controls_and_sanitized_errors(self):
        for text in (None, {}, "x"*100001, "\ud800", "\x00\x01\n"):
            with self.assertRaises(PrivacyError) as error:
                self.build(text)
            self.assertNotIn("x"*50, str(error.exception))
        for size in (True, -1, 63, 8193, 64.5):
            with self.assertRaises(PrivacyError):
                self.build("Task", max_bytes=size)
        with self.assertRaises(PrivacyError):
            build_task_description("Task", consent="real_tasks")
        self.assertEqual(self.build("  Fix\t bug\x00 \n\n add tests ").text, "Fix\t bug\nadd tests")

    def test_adversarial_repeated_secret_labels_do_not_stall_hook(self):
        # Run in a bounded process so a regex regression cannot stall the suite.
        code = ("from router_core.privacy import build_task_description,Consent; "
                "build_task_description('token'*20000,consent=Consent.REAL_TASKS); "
                "build_task_description('a.'*50000,consent=Consent.REAL_TASKS)")
        subprocess.run([sys.executable, "-c", code], timeout=2, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
