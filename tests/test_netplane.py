from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

import netplane
from netplane import hsclient, tools


class FakeContext:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.config_reads = []
        self.tools = {}
        self.hooks = {}

    def get_config(self, key, default=None):
        self.config_reads.append((key, default))
        return self.values.get(key, default)

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs

    def register_hook(self, name, callback):
        self.hooks[name] = callback


class EmptyRequest:
    pass


class CreatePreAuthKeyRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def fake_proto_modules():
    headscale = types.ModuleType("headscale")
    v1 = types.ModuleType("headscale.v1")
    node_pb2 = types.ModuleType("headscale.v1.node_pb2")
    node_pb2.ListNodesRequest = EmptyRequest
    preauthkey_pb2 = types.ModuleType("headscale.v1.preauthkey_pb2")
    preauthkey_pb2.ListPreAuthKeysRequest = EmptyRequest
    preauthkey_pb2.CreatePreAuthKeyRequest = CreatePreAuthKeyRequest
    user_pb2 = types.ModuleType("headscale.v1.user_pb2")
    user_pb2.ListUsersRequest = EmptyRequest
    v1.node_pb2 = node_pb2
    v1.preauthkey_pb2 = preauthkey_pb2
    v1.user_pb2 = user_pb2
    headscale.v1 = v1
    return {
        "headscale": headscale,
        "headscale.v1": v1,
        "headscale.v1.node_pb2": node_pb2,
        "headscale.v1.preauthkey_pb2": preauthkey_pb2,
        "headscale.v1.user_pb2": user_pb2,
    }


class ToolDispatchTests(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeContext()
        netplane.register(self.ctx)

    def test_every_registered_handler_accepts_hermes_args_dict(self):
        methods = []

        def call(method, request):
            methods.append(method)
            if method == "ListNodes":
                return types.SimpleNamespace(nodes=[object()])
            if method == "ListPreAuthKeys":
                return types.SimpleNamespace(pre_auth_keys=[object()])
            raise AssertionError(method)

        completed = types.SimpleNamespace(stdout="active\n", stderr="", returncode=0)
        with (
            mock.patch.dict(sys.modules, fake_proto_modules()),
            mock.patch.object(tools.subprocess, "run", return_value=completed),
            mock.patch.object(tools.hsclient, "call", side_effect=call),
            mock.patch.object(
                tools.hsclient,
                "node_to_dict",
                return_value={"hostname": "node", "online": True},
            ),
            mock.patch.object(
                tools.hsclient,
                "preauth_to_dict",
                return_value={"id": 1, "reusable": False},
            ),
        ):
            status = self.ctx.tools["netplane_status"]["handler"](
                {}, session_id="session"
            )
            nodes = self.ctx.tools["netplane_nodes"]["handler"]({}, task_id="task")
            keys = self.ctx.tools["netplane_preauth"]["handler"](
                {"create": False}, task_id="task"
            )

        self.assertEqual(json.loads(status)["nodes_total"], 1)
        self.assertEqual(json.loads(nodes)[0]["hostname"], "node")
        self.assertFalse(json.loads(keys)[0]["reusable"])
        self.assertEqual(methods, ["ListNodes", "ListNodes", "ListPreAuthKeys"])

    def test_false_create_dispatch_only_lists_keys(self):
        calls = []

        def call(method, request):
            calls.append(method)
            return types.SimpleNamespace(pre_auth_keys=[])

        with (
            mock.patch.dict(sys.modules, fake_proto_modules()),
            mock.patch.object(tools.hsclient, "call", side_effect=call),
        ):
            result = self.ctx.tools["netplane_preauth"]["handler"](
                {
                    "create": False,
                    "reusable": "not-a-boolean",
                    "expiry_hours": True,
                }
            )

        self.assertEqual(json.loads(result), [])
        self.assertEqual(calls, ["ListPreAuthKeys"])

    def test_key_creation_defaults_single_use_and_caps_expiry(self):
        user = types.SimpleNamespace(id=7, name="alice")
        requests = []

        def call(method, request):
            if method == "ListUsers":
                return types.SimpleNamespace(users=[user])
            if method == "CreatePreAuthKey":
                requests.append(request)
                return types.SimpleNamespace(pre_auth_key=object())
            raise AssertionError(method)

        with (
            mock.patch.dict(sys.modules, fake_proto_modules()),
            mock.patch.object(tools.hsclient, "call", side_effect=call),
            mock.patch.object(tools.hsclient, "timestamp_in", side_effect=lambda n: n),
            mock.patch.object(
                tools.hsclient, "preauth_to_dict", return_value={"key": "secret"}
            ) as serialize,
        ):
            handler = self.ctx.tools["netplane_preauth"]["handler"]
            handler({"create": True, "expiry_hours": 999})
            handler({"create": True, "expiry_hours": 0})

        self.assertEqual([r.expiration for r in requests], [168 * 3600, 3600])
        self.assertEqual([r.reusable for r in requests], [False, False])
        self.assertEqual([r.user for r in requests], [7, 7])
        self.assertEqual(
            serialize.call_args_list,
            [
                mock.call(mock.ANY, include_key=True),
                mock.call(mock.ANY, include_key=True),
            ],
        )

    def test_key_creation_rejects_wrong_scalar_types(self):
        with (
            mock.patch.dict(sys.modules, fake_proto_modules()),
            mock.patch.object(tools.hsclient, "call") as call,
        ):
            handler = self.ctx.tools["netplane_preauth"]["handler"]
            reusable = json.loads(handler({"create": True, "reusable": "false"}))
            expiry = json.loads(handler({"create": True, "expiry_hours": True}))

        self.assertEqual(reusable["error"], "reusable must be a boolean")
        self.assertEqual(expiry["error"], "expiry_hours must be an integer")
        call.assert_not_called()

    def test_key_listing_omits_join_secrets(self):
        timestamp = types.SimpleNamespace(ToJsonString=lambda: "2026-01-01T00:00:00Z")
        key = types.SimpleNamespace(
            id=4,
            key="join-secret",
            user=types.SimpleNamespace(name="alice"),
            reusable=False,
            ephemeral=False,
            expiration=timestamp,
            created_at=timestamp,
            used=False,
            HasField=lambda field: field == "user",
        )
        with (
            mock.patch.dict(sys.modules, fake_proto_modules()),
            mock.patch.object(
                tools.hsclient,
                "call",
                return_value=types.SimpleNamespace(pre_auth_keys=[key]),
            ),
        ):
            result = json.loads(self.ctx.tools["netplane_preauth"]["handler"]({}))

        self.assertEqual(result[0]["id"], 4)
        self.assertNotIn("key", result[0])
        self.assertNotIn("join-secret", json.dumps(result))

    def test_key_creation_requires_approval_only_for_literal_true(self):
        hook = self.ctx.hooks["pre_tool_call"]
        self.assertIsNone(hook(tool_name="netplane_preauth", args={"create": False}))
        self.assertIsNone(hook(tool_name="netplane_preauth", args={"create": "true"}))
        self.assertIsNone(hook(tool_name="netplane_nodes", args={"create": True}))
        directive = hook(
            tool_name="netplane_preauth",
            args={"create": True, "expiry_hours": 999},
        )
        self.assertEqual(directive["action"], "approve")
        self.assertIn("168 hours", directive["message"])
        namespaced = hook(tool_name="netplane.netplane_preauth", args={"create": True})
        self.assertEqual(namespaced["action"], "approve")

    def test_key_creation_approval_sanitizes_the_display_user(self):
        hook = self.ctx.hooks["pre_tool_call"]
        directive = hook(
            tool_name="netplane_preauth",
            args={"create": True, "user": "alice\n\x1b[31m" + "x" * 200},
        )

        message = directive["message"]
        self.assertNotIn("\n", message)
        self.assertNotIn("\x1b", message)
        self.assertIn("alice [31m", message)
        self.assertNotIn("x" * 100, message)

    def test_setup_dispatch_and_approval_distinguish_plan_from_install(self):
        handler = self.ctx.tools["netplane_setup"]["handler"]
        with mock.patch.object(
            tools.setup_flow, "run", return_value={"ok": True}
        ) as run:
            result = json.loads(
                handler({"server_url": "https://hs.example.com"}, session_id="test")
            )
        self.assertTrue(result["ok"])
        run.assert_called_once_with({"server_url": "https://hs.example.com"})
        hook = self.ctx.hooks["pre_tool_call"]
        self.assertIsNone(hook(tool_name="netplane_setup", args={}))
        self.assertIsNone(hook(tool_name="netplane_setup", args={"action": "plan"}))
        directive = hook(
            tool_name="netplane.netplane_setup", args={"action": "install"}
        )
        self.assertEqual(directive["action"], "approve")
        self.assertIn("root privileges", directive["message"])
        self.assertIn("active Hermes profile", directive["message"])


class ClientTests(unittest.TestCase):
    def test_settings_are_read_per_key_at_call_time(self):
        ctx = FakeContext(
            {
                "grpc_addr": "127.0.0.2:50443",
                "control_url": "https://one.example",
            }
        )
        hsclient.configure(ctx)
        self.assertEqual(hsclient.grpc_addr(), "127.0.0.2:50443")
        self.assertEqual(hsclient.control_url(), "https://one.example")
        ctx.values["grpc_addr"] = "127.0.0.3:50443"
        self.assertEqual(hsclient.grpc_addr(), "127.0.0.3:50443")
        self.assertEqual(
            ctx.config_reads,
            [
                ("grpc_addr", "127.0.0.1:50443"),
                ("control_url", ""),
                ("grpc_addr", "127.0.0.1:50443"),
            ],
        )

    def test_proto_path_is_bundled_not_profile_configurable(self):
        ctx = FakeContext({"proto_dir": "/tmp/untrusted-protos"})
        hsclient.configure(ctx)
        path = hsclient.prepare_proto_path()
        self.assertEqual(Path(path), REPO_ROOT / "proto")
        self.assertEqual(ctx.config_reads, [])

    def test_secret_scope_is_read_each_time_and_env_is_not_read_directly(self):
        hsclient.configure(FakeContext())
        secret_scope = types.ModuleType("agent.secret_scope")
        secret_scope.get_secret = mock.Mock(side_effect=[" first ", "second", ""])
        agent = types.ModuleType("agent")
        agent.secret_scope = secret_scope
        with (
            mock.patch.dict(
                sys.modules,
                {"agent": agent, "agent.secret_scope": secret_scope},
            ),
            mock.patch.dict(
                os.environ,
                {
                    "NETPLANE_APIKEY": "wrong-profile-key",
                    "NETPLANE_GRPC_ADDR": "remote.example:50443",
                },
            ),
        ):
            self.assertEqual(hsclient.read_apikey(), "first")
            self.assertEqual(hsclient.read_apikey(), "second")
            self.assertEqual(hsclient.grpc_addr(), "127.0.0.1:50443")
            with self.assertRaisesRegex(RuntimeError, "active Hermes secret scope"):
                hsclient.read_apikey()
        self.assertEqual(secret_scope.get_secret.call_count, 3)

    def test_call_fetches_a_fresh_key_and_closes_channel(self):
        metadata = []

        class Channel:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class Service:
            pass

        channels = [Channel(), Channel()]
        services = [Service(), Service()]

        # Record metadata without relying on generated gRPC stubs.
        for service in services:

            def ping(request, *, metadata: list, timeout: float, _log=metadata):
                _log.append((metadata, timeout))
                return request

            service.Ping = ping

        with (
            mock.patch.object(hsclient, "read_apikey", side_effect=["one", "two"]),
            mock.patch.object(
                hsclient,
                "_new_stub",
                side_effect=list(zip(channels, services)),
            ),
        ):
            self.assertEqual(hsclient.call("Ping", "a"), "a")
            self.assertEqual(hsclient.call("Ping", "b", timeout=9), "b")

        self.assertEqual(metadata[0], ([("authorization", "Bearer one")], 5.0))
        self.assertEqual(metadata[1], ([("authorization", "Bearer two")], 9))
        self.assertTrue(all(channel.closed for channel in channels))

    def test_remote_grpc_uses_tls_while_loopback_may_be_insecure(self):
        calls = []
        grpc = types.ModuleType("grpc")
        grpc.insecure_channel = lambda target: (
            calls.append(("insecure", target)) or object()
        )
        grpc.ssl_channel_credentials = lambda: "credentials"
        grpc.secure_channel = lambda target, creds: (
            calls.append(("secure", target, creds)) or object()
        )
        ctx = FakeContext({"grpc_addr": "127.0.0.1:50443"})
        hsclient.configure(ctx)
        with mock.patch.dict(sys.modules, {"grpc": grpc}):
            hsclient._channel()
            ctx.values["grpc_addr"] = "headscale.example:50443"
            hsclient._channel()

        self.assertEqual(
            calls,
            [
                ("insecure", "127.0.0.1:50443"),
                ("secure", "headscale.example:50443", "credentials"),
            ],
        )

    def test_loopback_target_detection(self):
        for target in (
            "127.0.0.1:50443",
            "127.1.2.3:50443",
            "localhost:50443",
            "[::1]:50443",
            "dns:///localhost:50443",
            "unix:///run/headscale.sock",
        ):
            with self.subTest(target=target):
                self.assertTrue(hsclient._is_loopback_target(target))
        self.assertFalse(hsclient._is_loopback_target("10.0.0.2:50443"))
        self.assertFalse(hsclient._is_loopback_target("headscale.example:50443"))

    def test_local_acme_grpc_verifies_the_certificate_dns_name(self):
        grpc = types.ModuleType("grpc")
        grpc.ssl_channel_credentials = mock.Mock(return_value="system-trust")
        grpc.secure_channel = mock.Mock(return_value="tls-channel")
        grpc.insecure_channel = mock.Mock()
        hsclient.configure(FakeContext({"grpc_tls_server_name": "hs.example.com"}))
        with mock.patch.dict(sys.modules, {"grpc": grpc}):
            self.assertEqual(hsclient._channel(), "tls-channel")
        grpc.secure_channel.assert_called_once_with(
            "127.0.0.1:50443",
            "system-trust",
            options=(
                ("grpc.ssl_target_name_override", "hs.example.com"),
                ("grpc.default_authority", "hs.example.com"),
            ),
        )
        grpc.insecure_channel.assert_not_called()

    def test_tls_name_override_is_rejected_for_remote_targets(self):
        grpc = types.ModuleType("grpc")
        hsclient.configure(
            FakeContext(
                {
                    "grpc_addr": "other.example.com:50443",
                    "grpc_tls_server_name": "hs.example.com",
                }
            )
        )
        with (
            mock.patch.dict(sys.modules, {"grpc": grpc}),
            self.assertRaisesRegex(ValueError, "loopback"),
        ):
            hsclient._channel()

    def test_preauth_serializer_only_includes_secret_when_requested(self):
        timestamp = types.SimpleNamespace(ToJsonString=lambda: "2026-01-01T00:00:00Z")
        key = types.SimpleNamespace(
            id=4,
            key="join-secret",
            user=types.SimpleNamespace(name="alice"),
            reusable=False,
            ephemeral=False,
            expiration=timestamp,
            created_at=timestamp,
            used=False,
            HasField=lambda field: field == "user",
        )
        listed = hsclient.preauth_to_dict(key)
        created = hsclient.preauth_to_dict(key, include_key=True)
        self.assertNotIn("key", listed)
        self.assertEqual(created["key"], "join-secret")


class StatusCommandTests(unittest.TestCase):
    def test_nonzero_status_command_reports_stderr(self):
        completed = types.SimpleNamespace(
            stdout="", stderr="permission denied\n", returncode=1
        )
        with mock.patch.object(tools.subprocess, "run", return_value=completed) as run:
            result = tools._run_status_command(["example"])
        self.assertEqual(result, "error (exit 1): permission denied")
        run.assert_called_once_with(
            ["example"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )


class ManifestTests(unittest.TestCase):
    def test_generated_stub_dependency_floors(self):
        manifest = (REPO_ROOT / "plugin.yaml").read_text(encoding="utf-8")
        self.assertIn("grpcio>=1.81.1,<2", manifest)
        self.assertIn("protobuf>=6.33.5,<7", manifest)
        self.assertIn("provides_hooks:\n  - pre_tool_call", manifest)
        self.assertNotIn("proto_dir", manifest)

        generated = REPO_ROOT / "proto"
        protobuf_stubs = sorted(generated.rglob("*_pb2.py"))
        grpc_stubs = sorted(generated.rglob("*_pb2_grpc.py"))
        self.assertTrue(protobuf_stubs)
        self.assertTrue(grpc_stubs)
        for path in protobuf_stubs:
            self.assertIn(
                "# Protobuf Python Version: 6.33.5",
                path.read_text(encoding="utf-8"),
                path,
            )
        for path in grpc_stubs:
            self.assertIn(
                "GRPC_GENERATED_VERSION = '1.81.1'",
                path.read_text(encoding="utf-8"),
                path,
            )

    def test_proto_regeneration_script_is_complete_and_valid_bash(self):
        script_path = REPO_ROOT / "scripts" / "gen_proto.sh"
        script = script_path.read_text(encoding="utf-8")
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is not available")
        subprocess.run([bash, "-n", script_path], check=True)
        self.assertIn("juanfont/headscale", script)
        self.assertIn("a2b1d7863926834e94479dcdd91ab344a9356bd0", script)
        self.assertIn("dff1cd0c7ff8c26ff4c9f7a87cbe175fb5124d4e", script)
        for filename in (
            "apikey.proto",
            "auth.proto",
            "device.proto",
            "headscale.proto",
            "node.proto",
            "policy.proto",
            "preauthkey.proto",
            "user.proto",
            "annotations.proto",
            "http.proto",
        ):
            self.assertIn(filename, script)
        self.assertIn('--pyi_out="$OUT"', script)
        self.assertIn('parent / "_proto"', script)
        self.assertIn('EXPECTED_GRPCIO_TOOLS="1.81.1"', script)
        self.assertIn('EXPECTED_PROTOBUF="6.33.5"', script)
        self.assertIn("sha256sum --check --status", script)

    def test_desktop_does_not_render_listed_join_secrets(self):
        desktop = (REPO_ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
        self.assertNotIn("user: 'onyx'", desktop)
        self.assertNotIn("k.key.slice", desktop)
        self.assertIn("reusable: false", desktop)
        self.assertIn("fmtExpiry(k.expiration)", desktop)
        self.assertIn("Expire node ${name}?", desktop)
        self.assertIn("expire failed:", desktop)


class HermesContractTests(unittest.TestCase):
    def test_real_hermes_hook_dispatcher_when_available(self):
        try:
            from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        except ImportError:
            self.skipTest("Hermes is not importable in this standalone checkout")

        manager = PluginManager()
        context = PluginContext(
            manager=manager,
            manifest=PluginManifest(name="netplane", source="user"),
        )
        context.register_hook("pre_tool_call", tools._approve_key_creation)
        results = manager.invoke_hook(
            "pre_tool_call",
            tool_name="netplane_preauth",
            args={"create": True},
            task_id="task",
        )
        self.assertEqual(results[0]["action"], "approve")


if __name__ == "__main__":
    unittest.main()
