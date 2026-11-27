"""In-process execution-loop harness for developers.

The bypass below applies ONLY while this test module is running. It does not
change the APK, the app config, or wraith/validator.py on disk. No command is
executed: Agent._run is replaced with a simulator, so the loop can be exercised
with normally-rejected commands without touching the device.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "src", "main", "python"))

from wraith import audit, scope, validator  # noqa: E402
from wraith.core import Agent  # noqa: E402


# Test-process-only switch. This is NOT read by the app or the APK.
DEV_BYPASS = True


def _bypass_validate(command, networks):
    """Accept anything inside this harness; real validation stays intact."""
    return True, "bypass", command.split(), []


class DevLoopHarnessTests(unittest.TestCase):
    def test_execution_loop_with_bypass(self):
        networks, errors = scope.parse_scope("192.168.0.11")
        self.assertEqual(errors, [])

        client = mock.Mock()
        client.create_session.return_value = "dev-loop"
        client.prompt.side_effect = [
            "nmap -sV 8.8.8.8",
            "responder-ng -I usb0 -i 8.8.8.8 -A -v",
            "DONE",
        ]

        lines = []
        with tempfile.TemporaryDirectory() as base:
            with mock.patch.object(validator, "validate", _bypass_validate), \
                    mock.patch.object(Agent, "_run",
                                      lambda self, argv, line_callback=None: "simulated output"), \
                    mock.patch.object(audit, "init_db", lambda: None), \
                    mock.patch.object(audit, "log", lambda *a, **k: None):
                agent = Agent(
                    "developer execution loop check",
                    networks,
                    base,
                    dry_run=False,
                    log=lines.append,
                    client=client,
                )
                agent.run()

        self.assertTrue(DEV_BYPASS)
        self.assertTrue(any("[RUN] step" in line for line in lines))
        self.assertTrue(any("[SUCCESS] step" in line for line in lines))
        self.assertTrue(any("objective complete" in line for line in lines))
        self.assertFalse(any("[BLOCKED]" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
