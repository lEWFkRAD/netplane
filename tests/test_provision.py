from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from netplane import provision

OPTIONS = {
    "server_url": "https://control.example.com",
    "acme_email": "admin@example.com",
}


class OptionTests(unittest.TestCase):
    def test_invalid_input_cannot_enter_urls_commands_or_yaml(self):
        bad = [
            {"server_url": "http://control.example.com"},
            {"server_url": "https://user:pass@control.example.com"},
            {"server_url": "https://control.example.com/path"},
            {"server_url": "https://control.example.com?x=y"},
            {"server_url": "https://control.example.com#part"},
            {"server_url": "https://control.example.com:8443"},
            {"server_url": "https://127.0.0.1"},
            {"server_url": "https://host.local"},
            {"server_url": "https://control.example.com\nother"},
            {"acme_email": ""},
            {"acme_email": "hello\nconfig: value"},
            {"tls_mode": "$(id)"},
            {"headscale_user": "--help"},
            {"headscale_user": "alice; id"},
            {"base_domain": "control.example.com"},
        ]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                provision.validate_options(OPTIONS | change)

    def test_normalization_and_reverse_proxy_no_email(self):
        options = provision.validate_options(
            OPTIONS
            | {"server_url": "https://CONTROL.example.com:443/", "action": "install"}
        )
        self.assertEqual(options["server_url"], "https://control.example.com")
        self.assertNotIn("action", options)
        reverse = provision.validate_options(
            {"server_url": "https://control.example.com", "tls_mode": "reverse_proxy"}
        )
        self.assertEqual(reverse["acme_email"], "")

    def test_plan_is_non_mutating_and_exposes_security_relevant_choices(self):
        with (
            mock.patch.object(provision, "_run") as run,
            mock.patch.object(provision.platform, "system", return_value="Linux"),
        ):
            plan = provision.build_plan(OPTIONS)
        run.assert_not_called()
        self.assertEqual(json.loads(plan["config_preview"]), plan["config"])
        self.assertEqual(plan["config"]["grpc_listen_addr"], "127.0.0.1:50443")
        self.assertFalse(plan["config"]["grpc_allow_insecure"])
        self.assertEqual(plan["grpc_tls_server_name"], "control.example.com")
        self.assertEqual(plan["config"]["derp"]["urls"], [])
        self.assertTrue(plan["config"]["derp"]["server"]["enabled"])
        self.assertFalse(plan["config"]["dns"]["override_local_dns"])
        self.assertIn("allows enrolled", " ".join(plan["prerequisites"]))

    def test_reverse_proxy_has_no_remote_admin_listener(self):
        plan = provision.build_plan(OPTIONS | {"tls_mode": "reverse_proxy"})
        self.assertEqual(plan["config"]["listen_addr"], "127.0.0.1:8080")
        self.assertTrue(plan["config"]["grpc_allow_insecure"])
        self.assertEqual(plan["grpc_tls_server_name"], "")

    def test_nonlinux_plan_fails_clearly(self):
        with (
            mock.patch.object(provision.platform, "system", return_value="Windows"),
            self.assertRaisesRegex(provision.ProvisionError, "Linux only"),
        ):
            provision.build_plan(OPTIONS)


class SafetyTests(unittest.TestCase):
    def test_existing_service_account_refuses_before_package_install(self):
        with (
            mock.patch.object(provision.platform, "system", return_value="Linux"),
            mock.patch.object(provision, "_architecture", return_value="amd64"),
            mock.patch.object(
                Path, "read_text", return_value='ID=ubuntu\nVERSION_ID="24.04"\n'
            ),
            mock.patch.object(Path, "is_dir", return_value=True),
            mock.patch.object(provision.os.path, "lexists", return_value=False),
            mock.patch("pwd.getpwnam", return_value=object()),
            mock.patch.object(
                provision, "_run", return_value=types.SimpleNamespace(stdout="amd64\n")
            ) as run,
            self.assertRaisesRegex(provision.ProvisionError, "system account"),
        ):
            provision._preflight(provision.validate_options(OPTIONS))
        self.assertEqual(run.call_count, 1)

    def test_parallel_setup_is_rejected_by_real_file_lock(self):
        actual_fstat = os.fstat

        def owned(fd):
            info = actual_fstat(fd)
            return types.SimpleNamespace(
                st_mode=info.st_mode, st_uid=0, st_nlink=info.st_nlink
            )

        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(provision, "LOCK", Path(folder) / "setup.lock"),
            mock.patch.object(provision.os, "fstat", side_effect=owned),
            provision._lock(),
            self.assertRaisesRegex(provision.ProvisionError, "Another NetPlane setup"),
            provision._lock(),
        ):
            self.fail("second lock should fail")

    def test_tampered_managed_configuration_is_rejected(self):
        info = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0)
        marker = {
            "version": provision.VERSION,
            "config_sha256": "unchanged-config-hash",
        }
        with (
            mock.patch.object(provision, "_trusted_directory"),
            mock.patch.object(Path, "lstat", return_value=info),
            mock.patch.object(Path, "read_text", return_value=json.dumps(marker)),
            mock.patch.object(
                Path, "read_bytes", return_value=b"changed configuration"
            ),
            self.assertRaisesRegex(provision.ProvisionError, "differs"),
        ):
            provision._managed_installation()

    def test_existing_configuration_refuses_before_mutation(self):
        with (
            mock.patch.object(provision.platform, "system", return_value="Linux"),
            mock.patch.object(provision, "_architecture", return_value="amd64"),
            mock.patch.object(
                Path, "read_text", return_value='ID=ubuntu\nVERSION_ID="24.04"\n'
            ),
            mock.patch.object(Path, "is_dir", return_value=True),
            mock.patch.object(
                provision.os.path,
                "lexists",
                side_effect=lambda path: path == provision.CONFIG.parent,
            ),
            mock.patch.object(
                provision, "_run", return_value=types.SimpleNamespace(stdout="amd64\n")
            ) as run,
            self.assertRaisesRegex(
                provision.ProvisionError, "Existing Headscale resource"
            ),
        ):
            provision._preflight(provision.validate_options(OPTIONS))
        self.assertEqual(
            run.call_args_list, [mock.call(["/usr/bin/dpkg", "--print-architecture"])]
        )

    def test_download_checksum_mismatch_never_runs_a_package(self):
        response = io.BytesIO(b"corrupted or substituted package")
        opener = mock.Mock()
        opener.open.return_value = response
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(
                provision.urllib.request, "build_opener", return_value=opener
            ),
            mock.patch.object(provision, "_run") as run,
            self.assertRaisesRegex(provision.ProvisionError, "SHA-256"),
        ):
            provision._download_package(Path(folder) / "package.deb", "amd64")
        run.assert_not_called()

    def test_plaintext_download_redirect_rejected(self):
        redirects = provision._HTTPSRedirects()
        with self.assertRaisesRegex(provision.ProvisionError, "non-HTTPS"):
            redirects.redirect_request(
                None, None, 302, "", {}, "http://example.com/package"
            )

    def test_root_required_before_system_probes(self):
        with (
            mock.patch.object(provision.os, "geteuid", return_value=1000),
            mock.patch.object(provision, "_preflight") as preflight,
            self.assertRaisesRegex(provision.ProvisionError, "root"),
        ):
            provision.install(OPTIONS)
        preflight.assert_not_called()

    def test_new_file_refuses_symlink_and_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "config"
            destination.symlink_to(Path(folder) / "elsewhere")
            with self.assertRaises(FileExistsError):
                provision._write_new(destination, "text")
            self.assertFalse((Path(folder) / "elsewhere").exists())

    def test_subprocess_failure_does_not_echo_secrets(self):
        process = mock.Mock(pid=123, returncode=1)
        process.communicate.return_value = ("secret-in-stdout", "secret-in-stderr")
        process.poll.return_value = 1
        with (
            mock.patch.object(
                provision.subprocess, "Popen", return_value=process
            ) as popen,
            self.assertRaises(provision.ProvisionError) as failure,
        ):
            provision._run(["/usr/bin/headscale", "apikeys", "create"])
        self.assertNotIn("secret", str(failure.exception))
        self.assertNotIn("HOME", popen.call_args.kwargs["env"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_timeout_terminates_subprocess_group(self):
        process = mock.Mock(pid=123, returncode=None)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("headscale", 1),
            ("", ""),
        ]
        process.poll.return_value = None
        with (
            mock.patch.object(provision.subprocess, "Popen", return_value=process),
            mock.patch.object(provision.os, "killpg") as kill,
            self.assertRaisesRegex(provision.ProvisionError, "timed out"),
        ):
            provision._run(["/usr/bin/headscale"], timeout=1)
        kill.assert_called_once_with(123, provision.signal.SIGTERM)


class InstallTests(unittest.TestCase):
    def _patch_install(self, folder, commands, fail_configtest=False):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(provision, "_require_root"))
        stack.enter_context(
            mock.patch.object(provision, "_lock", return_value=contextlib.nullcontext())
        )
        stack.enter_context(
            mock.patch.object(provision, "_preflight", return_value="amd64")
        )
        stack.enter_context(mock.patch.object(provision, "_download_package"))
        stack.enter_context(
            mock.patch.object(
                provision.tempfile,
                "TemporaryDirectory",
                return_value=contextlib.nullcontext(folder),
            )
        )
        stack.enter_context(mock.patch.object(provision, "_replace_owned"))
        stack.enter_context(mock.patch.object(provision, "_write_new"))
        stack.enter_context(mock.patch.object(provision, "_service_ready"))
        stack.enter_context(mock.patch.object(provision.os, "chown"))
        stack.enter_context(mock.patch.object(provision.os, "chmod"))
        stack.enter_context(
            mock.patch.object(
                Path,
                "lstat",
                return_value=types.SimpleNamespace(
                    st_mode=stat.S_IFDIR | 0o755, st_uid=0
                ),
            )
        )
        stack.enter_context(
            mock.patch(
                "pwd.getpwnam",
                return_value=types.SimpleNamespace(pw_uid=123, pw_gid=123),
            )
        )
        override = Path(folder) / "headscale.service.d" / "netplane.conf"
        stack.enter_context(mock.patch.object(provision, "OVERRIDE", override))

        def run(argv, **kwargs):
            commands.append(argv)
            if fail_configtest and "configtest" in argv:
                raise provision.ProvisionError("invalid config")
            return types.SimpleNamespace(
                stdout=provision.VERSION if argv[0] == "/usr/bin/dpkg-query" else "",
                returncode=0,
            )

        stack.enter_context(mock.patch.object(provision, "_run", side_effect=run))

    def test_install_masks_before_apt_and_validates_as_service_user_before_start(self):
        commands = []
        with tempfile.TemporaryDirectory() as folder:
            self._patch_install(folder, commands)
            result = provision.install(OPTIONS)
        masked = commands.index([provision.SYSTEMCTL, "mask", "headscale.service"])
        apt = next(
            index
            for index, argv in enumerate(commands)
            if argv[0] == "/usr/bin/apt-get"
        )
        configtest = next(
            index for index, argv in enumerate(commands) if "configtest" in argv
        )
        unmask = commands.index([provision.SYSTEMCTL, "unmask", "headscale.service"])
        self.assertLess(masked, apt)
        self.assertLess(apt, configtest)
        self.assertLess(configtest, unmask)
        self.assertEqual(
            commands[configtest][:4], ["/usr/sbin/runuser", "-u", "headscale", "--"]
        )
        self.assertTrue(result["installed"])
        self.assertFalse(result["public_endpoint_verified"])

    def test_bad_configuration_leaves_service_stopped_masked_and_reports_stage(self):
        commands = []
        with tempfile.TemporaryDirectory() as folder:
            self._patch_install(folder, commands, fail_configtest=True)
            with self.assertRaises(provision.ProvisionError) as error:
                provision.install(OPTIONS)
        self.assertEqual(error.exception.stage, "configtest")
        self.assertIn("retained", error.exception.recovery)
        self.assertNotIn([provision.SYSTEMCTL, "unmask", "headscale.service"], commands)
        self.assertIn([provision.SYSTEMCTL, "stop", "headscale.service"], commands)
        self.assertEqual(
            commands[-1], [provision.SYSTEMCTL, "mask", "headscale.service"]
        )


class BootstrapTests(unittest.TestCase):
    def _patch(self, marker):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(provision, "_require_root"))
        stack.enter_context(
            mock.patch.object(provision, "_lock", return_value=contextlib.nullcontext())
        )
        stack.enter_context(
            mock.patch.object(provision, "_managed_installation", return_value=marker)
        )

    def test_new_key_prefix_parsing_and_no_secret_written_to_marker(self):
        marker = {"api_key_prefix": ""}
        self._patch(marker)
        prefix = "abcd-efgh_12"
        key = "hskey-api-" + prefix + "-" + "a" * 64
        with (
            mock.patch.object(
                provision,
                "_run",
                return_value=types.SimpleNamespace(stdout=json.dumps(key)),
            ) as run,
            mock.patch.object(provision, "_replace_owned") as write,
        ):
            result = provision.bootstrap_key({})
        self.assertEqual(result, {"key": key, "prefix": prefix})
        self.assertNotIn(key, write.call_args.args[1])
        self.assertIn("90d", run.call_args.args[0])

    def test_repeated_bootstrap_does_not_create_a_key(self):
        self._patch({"api_key_prefix": "abcd-efgh_12"})
        with (
            mock.patch.object(provision, "_run") as run,
            self.assertRaisesRegex(provision.ProvisionError, "already bootstrapped"),
        ):
            provision.bootstrap_key({})
        run.assert_not_called()

    def test_marker_storage_failure_expires_new_key(self):
        self._patch({"api_key_prefix": ""})
        key = "hskey-api-" + "b" * 12 + "-" + "c" * 64
        with (
            mock.patch.object(
                provision,
                "_run",
                return_value=types.SimpleNamespace(stdout=json.dumps(key)),
            ) as run,
            mock.patch.object(
                provision, "_replace_owned", side_effect=[None, OSError("failure")]
            ),
            self.assertRaisesRegex(
                provision.ProvisionError, "expiration was attempted"
            ),
        ):
            provision.bootstrap_key({})
        self.assertIn("expire", run.call_args.args[0])
        self.assertEqual(run.call_args.args[0][-1], "b" * 12)

    def test_unknown_creation_outcome_blocks_retries_without_exposing_output(self):
        marker = {"api_key_prefix": "", "bootstrap_state": "ready"}
        self._patch(marker)
        with (
            mock.patch.object(
                provision,
                "_run",
                return_value=types.SimpleNamespace(stdout="secret-but-not-valid-json"),
            ) as run,
            mock.patch.object(provision, "_replace_owned"),
        ):
            with self.assertRaisesRegex(
                provision.ProvisionError, "outcome is uncertain"
            ) as failure:
                provision.bootstrap_key({})
            self.assertNotIn("secret", str(failure.exception))
            with self.assertRaisesRegex(
                provision.ProvisionError, "already bootstrapped"
            ):
                provision.bootstrap_key({})
        self.assertEqual(run.call_count, 1)
        self.assertEqual(marker["bootstrap_state"], "creating")

    def test_revocation_cannot_target_other_keys(self):
        self._patch({"api_key_prefix": "owned-prefix"})
        with (
            mock.patch.object(provision, "_run") as run,
            self.assertRaisesRegex(provision.ProvisionError, "does not match"),
        ):
            provision.revoke_key({"prefix": "differentkey"})
        run.assert_not_called()


@unittest.skipUnless(
    os.environ.get("NETPLANE_TEST_HEADSCALE"),
    "set NETPLANE_TEST_HEADSCALE to an extracted official binary",
)
class RealConfigTests(unittest.TestCase):
    def test_generated_configuration_passes_pinned_binary_without_host_changes(self):
        binary = os.environ["NETPLANE_TEST_HEADSCALE"]
        for mode in ("letsencrypt", "reverse_proxy"):
            with (
                self.subTest(mode=mode),
                tempfile.TemporaryDirectory(prefix="netplane-configtest-") as folder,
            ):
                config = provision.build_plan(OPTIONS | {"tls_mode": mode})["config"]
                # configtest creates keys/database; keep all generated state
                # within this isolated temporary fixture.
                config["noise"]["private_key_path"] = folder + "/noise.key"
                config["derp"]["server"]["private_key_path"] = folder + "/derp.key"
                config["database"]["sqlite"]["path"] = folder + "/db.sqlite"
                config["tls_letsencrypt_cache_dir"] = folder + "/cache"
                config["unix_socket"] = folder + "/headscale.sock"
                path = Path(folder) / "config.yaml"
                path.write_text(provision._json(config))
                result = subprocess.run(
                    [binary, "--config", str(path), "configtest"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=provision.SAFE_ENV,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
