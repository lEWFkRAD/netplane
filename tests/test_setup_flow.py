from __future__ import annotations

import json
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from netplane import setup_flow

SECRET = "test-secret-never-return-this-value"
OPTIONS = {
    "server_url": "https://headscale.example.test",
    "tls_mode": "reverse_proxy",
    "acme_email": "",
    "base_domain": "mesh.example.test",
    "headscale_user": "owner",
}
INSTALLED = {
    "installed": True,
    "version": "0.29.6",
    "grpc_addr": "127.0.0.1:50443",
    "control_url": OPTIONS["server_url"],
    "grpc_tls_server_name": "",
}


class Context:
    def __init__(self):
        self.values = {}
        self.reads = []
        self.writes = []

    def get_config(self, key, default=None):
        self.reads.append(key)
        return self.values.get(key, default)

    def set_config(self, key, value):
        self.values[key] = value
        self.writes.append((key, value))


class SetupFlowTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Context()
        setup_flow.configure(self.ctx)
        self.secrets = {}
        self.save = mock.Mock(side_effect=self.store)
        self.writable = mock.Mock()
        self.provision = types.ModuleType("netplane.provision")
        self.provision.validate_options = mock.Mock(return_value=dict(OPTIONS))
        self.provision.build_plan = mock.Mock(
            return_value={"actions": ["install"], "options": dict(OPTIONS)}
        )
        self.modules = mock.patch.dict(
            sys.modules, {"netplane.provision": self.provision}
        )
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.api = mock.patch.object(
            setup_flow,
            "_secret_api",
            return_value=(self.secrets.get, self.save, self.writable),
        )
        self.api.start()
        self.addCleanup(self.api.stop)

    def store(self, name, value):
        self.secrets[name] = value
        return {"success": True, "stored_as": name, "validated": False}

    def responses(self, action, payload):
        if action == "install":
            return dict(INSTALLED)
        if action == "bootstrap-key":
            return {"key": SECRET, "prefix": "new-prefix"}
        if action == "revoke-key":
            return {"revoked": True}
        raise AssertionError(action)

    def install(self):
        return setup_flow.run({"action": "install", **OPTIONS})

    def assert_secret_absent(self, result):
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn("new-prefix", json.dumps(result))

    def test_default_plan_never_reads_credentials_or_mutates(self):
        with (
            mock.patch.object(setup_flow, "_helper") as helper,
            mock.patch.object(setup_flow, "_secret_api") as api,
        ):
            result = setup_flow.run(dict(OPTIONS))
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "plan")
        helper.assert_not_called()
        api.assert_not_called()
        self.assertEqual(self.ctx.reads, [])
        self.assertEqual(self.ctx.writes, [])

    def test_install_stores_secret_without_returning_it(self):
        with mock.patch.object(
            setup_flow, "_helper", side_effect=self.responses
        ) as helper:
            result = self.install()
        self.assertTrue(result["ok"])
        self.assertTrue(result["credentials_saved"])
        self.save.assert_called_once_with("NETPLANE_APIKEY", SECRET)
        self.assertEqual(
            [call.args[0] for call in helper.call_args_list],
            ["install", "bootstrap-key"],
        )
        self.assertEqual(self.ctx.values["control_url"], OPTIONS["server_url"])
        self.assert_secret_absent(result)

    def test_letsencrypt_persists_exact_tls_hostname(self):
        self.provision.validate_options.return_value = {
            **OPTIONS,
            "tls_mode": "letsencrypt",
            "acme_email": "owner@example.com",
        }

        def response(action, payload):
            if action == "install":
                return {**INSTALLED, "grpc_tls_server_name": "headscale.example.test"}
            return self.responses(action, payload)

        with mock.patch.object(setup_flow, "_helper", side_effect=response):
            result = self.install()
        self.assertTrue(result["ok"])
        self.assertEqual(
            self.ctx.values["grpc_tls_server_name"], "headscale.example.test"
        )
        self.assertFalse(result["public_endpoint_verified"])

    def test_profile_settings_are_read_when_call_runs(self):
        self.ctx.values["grpc_addr"] = "other-profile.example:50443"
        with mock.patch.object(setup_flow, "_helper") as helper:
            result = self.install()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "preflight")
        self.assertIn("grpc_addr", self.ctx.reads)
        helper.assert_not_called()

    def test_existing_secret_is_never_overwritten(self):
        self.secrets["NETPLANE_APIKEY"] = "previous-key"
        with mock.patch.object(setup_flow, "_helper") as helper:
            result = self.install()
        self.assertFalse(result["ok"])
        helper.assert_not_called()
        self.save.assert_not_called()
        self.assertEqual(self.secrets["NETPLANE_APIKEY"], "previous-key")

    def test_denied_storage_aborts_before_installation(self):
        self.writable.side_effect = ValueError(SECRET)
        with mock.patch.object(setup_flow, "_helper") as helper:
            result = self.install()
        self.assertFalse(result["ok"])
        helper.assert_not_called()
        self.assert_secret_absent(result)

    def test_missing_storage_api_aborts_before_installation(self):
        with (
            mock.patch.object(
                setup_flow, "_secret_api", side_effect=ImportError(SECRET)
            ),
            mock.patch.object(setup_flow, "_helper") as helper,
        ):
            result = self.install()
        self.assertFalse(result["ok"])
        helper.assert_not_called()
        self.assert_secret_absent(result)

    def test_storage_failure_revokes_new_key_and_redacts_error(self):
        self.save.side_effect = RuntimeError(SECRET)
        with mock.patch.object(
            setup_flow, "_helper", side_effect=self.responses
        ) as helper:
            result = self.install()
        self.assertFalse(result["ok"])
        self.assertTrue(result["installed"])
        self.assertEqual(result["credential_revocation"], "revoked")
        self.assertEqual(
            helper.call_args, mock.call("revoke-key", {"prefix": "new-prefix"})
        )
        self.assert_secret_absent(result)

    def test_late_storage_failure_retains_uncertain_copy_for_manual_cleanup(self):
        def persist_then_raise(name, key):
            self.secrets[name] = key
            raise RuntimeError(SECRET)

        self.save.side_effect = persist_then_raise
        with mock.patch.object(setup_flow, "_helper", side_effect=self.responses):
            result = self.install()
        self.assertFalse(result["ok"])
        self.assertEqual(self.secrets["NETPLANE_APIKEY"], SECRET)
        self.assertEqual(result["credential_cleanup"], "manual_required")
        self.assert_secret_absent(result)

    def test_failed_revocation_reported_without_leaking_secret(self):
        self.save.side_effect = RuntimeError(SECRET)

        def failure(action, payload):
            if action == "revoke-key":
                raise subprocess.TimeoutExpired("command", 30, output=SECRET)
            return self.responses(action, payload)

        with mock.patch.object(setup_flow, "_helper", side_effect=failure):
            result = self.install()
        self.assertEqual(result["credential_revocation"], "failed")
        self.assert_secret_absent(result)

    def test_credential_creation_timeout_reports_unknown_revocation(self):
        def response(action, payload):
            if action == "bootstrap-key":
                raise subprocess.TimeoutExpired("command", 30, output=SECRET)
            return self.responses(action, payload)

        with mock.patch.object(setup_flow, "_helper", side_effect=response):
            result = self.install()
        self.assertFalse(result["ok"])
        self.assertEqual(result["credential_revocation"], "unknown")
        self.assert_secret_absent(result)

    def test_concurrent_credential_replacement_survives_failed_save(self):
        def replaced_then_raise(name, key):
            self.secrets[name] = "another-session-value"
            raise RuntimeError(SECRET)

        self.save.side_effect = replaced_then_raise
        with mock.patch.object(setup_flow, "_helper", side_effect=self.responses):
            result = self.install()
        self.assertEqual(self.secrets["NETPLANE_APIKEY"], "another-session-value")
        self.assertEqual(result["credential_cleanup"], "not_needed")
        self.assert_secret_absent(result)

    def test_settings_failure_does_not_mint_key(self):
        self.ctx.set_config = mock.Mock(side_effect=PermissionError(SECRET))
        with mock.patch.object(
            setup_flow, "_helper", side_effect=self.responses
        ) as helper:
            result = self.install()
        self.assertFalse(result["ok"])
        self.assertTrue(result["installed"])
        self.assertEqual(helper.call_count, 1)
        self.assert_secret_absent(result)

    def test_profile_changed_during_install_is_preserved(self):
        def changed(action, payload):
            self.ctx.values["control_url"] = "https://other.example.test"
            return dict(INSTALLED)

        with mock.patch.object(setup_flow, "_helper", side_effect=changed):
            result = self.install()
        self.assertFalse(result["ok"])
        self.assertTrue(result["installed"])
        self.assertEqual(self.ctx.writes, [])
        self.save.assert_not_called()

    def test_plan_reports_unsupported_host_without_traceback(self):
        self.provision.build_plan.side_effect = RuntimeError("unsupported architecture")
        result = setup_flow.plan(OPTIONS)
        self.assertFalse(result["ok"])
        self.assertIn("supported Debian/Ubuntu", result["error"])

    def test_unexpected_tls_override_is_refused_before_config_or_key_creation(self):
        with mock.patch.object(
            setup_flow,
            "_helper",
            return_value={**INSTALLED, "grpc_tls_server_name": "unapproved.example"},
        ) as helper:
            result = self.install()
        self.assertFalse(result["ok"])
        self.assertTrue(result["installed"])
        self.assertEqual(helper.call_count, 1)
        self.assertEqual(self.ctx.writes, [])
        self.save.assert_not_called()

    def test_helper_runs_noninteractively_with_fixed_sanitized_environment(self):
        completed = types.SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")
        with (
            mock.patch.object(setup_flow.os, "geteuid", return_value=1000),
            mock.patch.dict(
                os.environ, {"NETPLANE_APIKEY": SECRET, "LD_PRELOAD": SECRET}
            ),
            mock.patch.object(
                setup_flow.subprocess, "run", return_value=completed
            ) as command,
        ):
            setup_flow._helper("install", OPTIONS)
        argv = command.call_args.args[0]
        self.assertEqual(argv[:4], ["/usr/bin/sudo", "-n", "--", "/usr/bin/timeout"])
        self.assertEqual(argv[4:7], ["--signal=TERM", "--kill-after=15s", "330s"])
        self.assertEqual(argv[7:9], ["/usr/bin/python3", "-I"])
        self.assertEqual(argv[-2:], ["--action", "install"])
        kwargs = command.call_args.kwargs
        self.assertFalse(kwargs["shell"])
        self.assertGreater(kwargs["timeout"], 345)
        self.assertLess(kwargs["timeout"], 380)
        self.assertNotIn("NETPLANE_APIKEY", kwargs["env"])
        self.assertNotIn("LD_PRELOAD", kwargs["env"])
        self.assertNotIn(SECRET, json.dumps(kwargs))
        self.assertEqual(json.loads(kwargs["input"]), OPTIONS)

    def test_helper_errors_do_not_embed_output(self):
        completed = types.SimpleNamespace(returncode=1, stdout=SECRET, stderr=SECRET)
        with (
            mock.patch.object(setup_flow.subprocess, "run", return_value=completed),
            self.assertRaises(RuntimeError) as raised,
        ):
            setup_flow._helper("bootstrap-key", {})
        self.assertNotIn(SECRET, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
