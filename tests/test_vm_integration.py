"""Pure harness checks: these never install or invoke a guest service."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

_SPEC = importlib.util.spec_from_file_location(
    "netplane_vm_harness", Path(__file__).with_name("vm_integration.py")
)
harness = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(harness)
SECRET = "hskey-api-private_1234-credential_should_never_leave_the_guest"


class VMHarnessTests(unittest.TestCase):
    def test_only_allowlisted_setup_fields_leave_guest(self):
        details = harness.setup_details(
            {
                "ok": False,
                "stage": "credential_storage",
                "installed": True,
                "configured": False,
                "credentials_saved": False,
                "credential_revocation": "revoked",
                "credential_cleanup": "manual_required",
                "error": SECRET,
                "key": SECRET,
            }
        )
        self.assertEqual(details["setup_stage"], "credential_storage")
        self.assertEqual(details["credential_revocation"], "revoked")
        self.assertTrue(details["installed"])
        self.assertNotIn(SECRET, json.dumps(details))
        self.assertNotIn("error", details)

    def test_unexpected_setup_values_are_dropped(self):
        self.assertEqual(
            harness.setup_details(
                {
                    "stage": SECRET,
                    "installation_state": SECRET,
                    "credential_revocation": SECRET,
                    "credential_cleanup": SECRET,
                    "installed": SECRET,
                }
            ),
            {},
        )
        self.assertEqual(harness.setup_details([SECRET]), {})

    def test_receipt_accepts_known_states(self):
        self.assertTrue(
            harness.safe_receipt(
                {
                    "stage": "setup_install",
                    "ok": False,
                    "error": "setup_install_failed",
                    "installed": True,
                    "setup_stage": "credential_storage",
                    "credential_revocation": "unknown",
                    "exit_status": 1,
                }
            )
        )

    def test_receipt_rejects_extra_fields_or_unknown_states(self):
        for extra in (
            {"key": SECRET},
            {"error": SECRET},
            {"credential_revocation": SECRET},
            {"installed": "true"},
            {"exit_status": True},
            {"exit_status": 1000},
        ):
            self.assertFalse(
                harness.safe_receipt(
                    {
                        "stage": "setup_install",
                        "ok": False,
                        **extra,
                    }
                )
            )

    def test_command_diagnostics_do_not_echo_output(self):
        result = subprocess.CompletedProcess(
            ["unused"], 1, SECRET, "failed to download pinned uv " + SECRET
        )
        self.assertEqual(
            harness.command_details(result),
            {
                "exit_status": 1,
                "diagnostic": "environment_bootstrap",
            },
        )

    def test_exception_diagnostics_do_not_echo_error(self):
        result = harness.exception_details(PermissionError(SECRET))
        self.assertEqual(
            result,
            {
                "error": "integration_exception",
                "exception_kind": "permission",
            },
        )
        result = harness.exception_details(
            harness.CheckFailed("setup_install_failed", setup_stage="installation")
        )
        self.assertEqual(result["setup_stage"], "installation")

    def test_clean_environment_does_not_inherit_secrets_or_activation(self):
        profile = Path("/tmp/netplane-vm-profile-unit-test")
        with mock.patch.dict(
            os.environ,
            {
                "NETPLANE_APIKEY": SECRET,
                "__HERMES_ACTIVATED": "/host/state",
                "UV_PYTHON": "/host/python",
                "PYTHONPATH": "/host/imports",
            },
        ):
            result = harness.clean_environment(profile)
        self.assertEqual(result["HERMES_HOME"], str(profile))
        self.assertEqual(result["HERMES_RUNTIME_DIR"], str(profile / "runtime"))
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn("__HERMES_ACTIVATED", result)
        self.assertNotIn("UV_PYTHON", result)
        self.assertNotIn("PYTHONPATH", result)

    def test_guard_refuses_without_explicit_vm_flag(self):
        with mock.patch.object(harness, "run_command") as run:
            with self.assertRaisesRegex(
                harness.CheckFailed, "explicit_disposable_vm_flag_required"
            ):
                harness.guest_guard(False)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
