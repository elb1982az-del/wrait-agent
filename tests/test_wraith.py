import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "src", "main", "python"))

from wraith import audit, cve, history, playbooks, scope, tools, validator
from wraith.core import extract_commands
from wraith.opencode_client import OpenCodeClient


class ScopeTests(unittest.TestCase):
    def test_parse_scope(self):
        networks, errors = scope.parse_scope("# note\nallowed:\n  - 192.168.1.0/24\n  - 10.0.0.5\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(networks), 2)
        self.assertTrue(scope.is_allowed("192.168.1.20", networks))
        self.assertTrue(scope.is_allowed("10.0.0.5", networks))
        self.assertFalse(scope.is_allowed("8.8.8.8", networks))

    def test_bad_entry(self):
        networks, errors = scope.parse_scope("allowed:\n  - not-an-ip\n")
        self.assertEqual(networks, [])
        self.assertEqual(len(errors), 1)

    def test_plain_ipv4(self):
        networks, errors = scope.parse_scope("45.33.32.156\n")
        self.assertEqual(errors, [])
        self.assertEqual([str(n) for n in networks], ["45.33.32.156/32"])
        self.assertTrue(scope.is_allowed("45.33.32.156", networks))
        self.assertEqual(scope.target_from_scope(networks), "45.33.32.156")

    def test_plain_ip_list_and_inline_yaml(self):
        networks, errors = scope.parse_scope("45.33.32.156, 45.33.32.157\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(networks), 2)
        networks, errors = scope.parse_scope("allowed: [45.33.32.156, 10.0.0.0/24]\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(networks), 2)


class ValidatorTests(unittest.TestCase):
    networks, _ = scope.parse_scope("allowed:\n  - 192.168.1.0/24\n")

    def check(self, command):
        with mock.patch.object(validator, "shutil_which_missing", return_value=False):
            return validator.validate(command, self.networks)

    def test_allowed(self):
        ok, reason, argv, targets = self.check("nmap -sV -T4 192.168.1.10")
        self.assertTrue(ok, reason)
        self.assertEqual(argv[0], "nmap")
        self.assertEqual(targets, ["192.168.1.10"])

    def test_out_of_scope(self):
        ok, reason, _, _ = self.check("nmap -sV 8.8.8.8")
        self.assertFalse(ok)
        self.assertIn("outside scope", reason)

    def test_plain_ip_scope(self):
        networks, errors = scope.parse_scope("45.33.32.156")
        self.assertEqual(errors, [])
        with mock.patch.object(validator, "shutil_which_missing", return_value=False):
            ok, reason, _, targets = validator.validate("nmap -sV 45.33.32.156", networks)
        self.assertTrue(ok, reason)
        self.assertEqual(targets, ["45.33.32.156"])

    def test_destructive(self):
        for command in ("nmap rm -rf 192.168.1.1", "mkfs 192.168.1.1", "dd if=x 192.168.1.1"):
            ok, reason, _, _ = self.check(command)
            self.assertFalse(ok, command)
            self.assertIn("blocked pattern", reason)

    def test_tool_not_allowlisted(self):
        ok, reason, _, _ = self.check("sqlmap -u 192.168.1.1")
        self.assertFalse(ok)
        self.assertIn("tool not allowlisted", reason)

    def test_shell_operators(self):
        ok, reason, _, _ = self.check("nmap 192.168.1.1; id")
        self.assertFalse(ok)
        self.assertIn("blocked pattern", reason)


class HelperTests(unittest.TestCase):
    def test_playbook(self):
        name, steps = playbooks.match("quick web scan")
        self.assertEqual(name, "quick_web")
        self.assertEqual(len(steps), 2)

    def test_cve(self):
        hits = cve.match("Apache/2.4.49 server at port 80")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["cve"], "CVE-2021-41773")

    def test_tools_prune(self):
        names = [item["name"] for item in tools.prune("scan")]
        self.assertIn("nmap", names)
        self.assertNotIn("hydra", names)
        names = [item["name"] for item in tools.prune("test login", "80/tcp open", 2)]
        self.assertIn("nikto", names)
        self.assertIn("hydra", names)

    def test_history_compress(self):
        compressed = history.compress(["a", "b", "c", "d", "e", "f"], keep=2)
        self.assertIn("SUMMARY OF EARLIER STEPS", compressed)
        self.assertIn("RECENT STEPS", compressed)

    def test_extract_commands(self):
        reply = "1. nmap -sV 192.168.1.1\n2. `nikto -h 192.168.1.1`\nSome prose"
        self.assertEqual(extract_commands(reply), ["nmap -sV 192.168.1.1", "nikto -h 192.168.1.1"])


class AuditTests(unittest.TestCase):
    def test_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.db")
            with mock.patch.object(audit, "db_path", return_value=path):
                audit.log({"level": "info", "command": "nmap -sV 192.168.1.1", "allowed": True})
                rows = audit.recent(10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["command"], "nmap -sV 192.168.1.1")


class OpenCodeClientTests(unittest.TestCase):
    def test_relay_fallback(self):
        with tempfile.TemporaryDirectory() as base:
            request_path = os.path.join(base, "model_request.json")
            response_path = os.path.join(base, "model_response.json")

            def respond():
                rid = None
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        with open(request_path, "r", encoding="utf-8") as handle:
                            rid = json.load(handle)["id"]
                        break
                    except Exception:
                        time.sleep(0.02)
                with open(response_path, "w", encoding="utf-8") as handle:
                    json.dump({"id": rid, "ok": True, "data": {"data": {"id": "ses_test"}}}, handle)

            thread = threading.Thread(target=respond, daemon=True)
            thread.start()
            client = OpenCodeClient(relay_dir=base)
            with mock.patch.object(urllib.request, "urlopen", side_effect=OSError("refused")):
                session_id = client.create_session("test")
            thread.join(timeout=5)
            self.assertEqual(session_id, "ses_test")


if __name__ == "__main__":
    unittest.main()
