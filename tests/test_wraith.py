import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "src", "main", "python"))

from wraith import audit, cve, history, playbooks, scope, tools, validator
from wraith.core import extract_commands


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


if __name__ == "__main__":
    unittest.main()
