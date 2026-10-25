from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeRouter:
    def get(self, *_args, **_kwargs):
        return lambda fn: fn

    def post(self, *_args, **_kwargs):
        return lambda fn: fn


class _FakeHTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _EmptyRequest:
    pass


class _CreatePreAuthKeyRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _fake_proto_modules():
    headscale = types.ModuleType("headscale")
    v1 = types.ModuleType("headscale.v1")
    node_pb2 = types.ModuleType("headscale.v1.node_pb2")
    node_pb2.ListNodesRequest = _EmptyRequest
    node_pb2.ExpireNodeRequest = _CreatePreAuthKeyRequest
    preauthkey_pb2 = types.ModuleType("headscale.v1.preauthkey_pb2")
    preauthkey_pb2.CreatePreAuthKeyRequest = _CreatePreAuthKeyRequest
    preauthkey_pb2.ListPreAuthKeysRequest = _EmptyRequest
    user_pb2 = types.ModuleType("headscale.v1.user_pb2")
    user_pb2.ListUsersRequest = _EmptyRequest
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


def _install_fastapi_stub_if_needed() -> bool:
    try:
        importlib.import_module("fastapi")
        return False
    except ModuleNotFoundError:
        fastapi = types.ModuleType("fastapi")
        fastapi.APIRouter = _FakeRouter
        fastapi.HTTPException = _FakeHTTPException
        sys.modules["fastapi"] = fastapi
        return True


def _load_package_and_dashboard():
    namespace = sys.modules.get("hermes_plugins")
    if namespace is None:
        namespace = types.ModuleType("hermes_plugins")
        namespace.__path__ = []
        sys.modules["hermes_plugins"] = namespace

    package_name = "hermes_plugins.netplane"
    package_spec = importlib.util.spec_from_file_location(
        package_name,
        REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)],
    )
    if package_spec is None or package_spec.loader is None:
        raise ImportError("could not build the netplane package spec")
    package = importlib.util.module_from_spec(package_spec)
    sys.modules[package_name] = package
    namespace.netplane = package
    package_spec.loader.exec_module(package)

    dashboard_name = "hermes_dashboard_plugin_netplane"
    dashboard_spec = importlib.util.spec_from_file_location(
        dashboard_name, REPO_ROOT / "dashboard" / "plugin_api.py"
    )
    if dashboard_spec is None or dashboard_spec.loader is None:
        raise ImportError("could not build the dashboard module spec")
    dashboard = importlib.util.module_from_spec(dashboard_spec)
    sys.modules[dashboard_name] = dashboard
    dashboard_spec.loader.exec_module(dashboard)
    return package, dashboard


class DashboardPluginApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._installed_fastapi_stub = _install_fastapi_stub_if_needed()
        cls.package, cls.api = _load_package_and_dashboard()

    @classmethod
    def tearDownClass(cls):
        if cls._installed_fastapi_stub:
            sys.modules.pop("fastapi", None)

    def test_dashboard_uses_the_agent_packages_hsclient_instance(self):
        self.assertIs(self.api.hsclient, self.package.hsclient)
        self.assertIs(
            self.api.hsclient,
            sys.modules["hermes_plugins.netplane.hsclient"],
        )
        self.assertNotIn("hsclient", sys.modules)

    def test_status_reads_control_url_through_the_live_client_accessor(self):
        with (
            mock.patch.dict(sys.modules, _fake_proto_modules()),
            mock.patch.object(self.api, "_run", return_value="active"),
            mock.patch.object(
                self.api.hsclient, "control_url", return_value="https://live.example"
            ) as control_url,
            mock.patch.object(
                self.api.hsclient,
                "call",
                return_value=types.SimpleNamespace(nodes=[]),
            ),
        ):
            result = self.api.status()

        self.assertEqual(result["control_url"], "https://live.example")
        control_url.assert_called_once_with()

    def test_create_defaults_single_use_and_caps_expiry(self):
        requests = []
        user = types.SimpleNamespace(id=7, name="alice")

        def call(method, request):
            if method == "ListUsers":
                return types.SimpleNamespace(users=[user])
            if method == "CreatePreAuthKey":
                requests.append(request)
                return types.SimpleNamespace(pre_auth_key=object())
            raise AssertionError(method)

        with (
            mock.patch.dict(sys.modules, _fake_proto_modules()),
            mock.patch.object(self.api.hsclient, "call", side_effect=call),
            mock.patch.object(
                self.api.hsclient, "timestamp_in", side_effect=lambda seconds: seconds
            ),
            mock.patch.object(
                self.api.hsclient,
                "preauth_to_dict",
                return_value={"key": "redacted"},
            ),
        ):
            self.api.create_preauth({})
            self.api.create_preauth({"expiry_hours": 999})
            self.api.create_preauth({"expiry_hours": 0})
            self.api.create_preauth({"reusable": True})

        self.assertEqual(
            [request.expiration for request in requests],
            [24 * 3600, 168 * 3600, 3600, 24 * 3600],
        )
        self.assertEqual(
            [request.reusable for request in requests],
            [False, False, False, True],
        )
        self.assertEqual([request.user for request in requests], [7, 7, 7, 7])

    def test_create_rejects_non_integer_expiry(self):
        with mock.patch.dict(sys.modules, _fake_proto_modules()):
            for value in (True, False, None, "24", 3.5):
                with self.subTest(value=value):
                    with self.assertRaises(self.api.HTTPException) as raised:
                        self.api.create_preauth({"expiry_hours": value})
                    self.assertEqual(raised.exception.status_code, 422)

    def test_create_rejects_non_boolean_reusable(self):
        with mock.patch.dict(sys.modules, _fake_proto_modules()):
            for value in (None, 0, 1, "false", "true"):
                with self.subTest(value=value):
                    with self.assertRaises(self.api.HTTPException) as raised:
                        self.api.create_preauth({"reusable": value})
                    self.assertEqual(raised.exception.status_code, 422)

    def test_routes_are_sync_so_blocking_io_runs_in_fastapi_threadpool(self):
        for route in (
            self.api.setup_plan,
            self.api.setup_install,
            self.api.status,
            self.api.nodes,
            self.api.expire_node,
            self.api.preauth,
            self.api.create_preauth,
        ):
            with self.subTest(route=route.__name__):
                self.assertFalse(inspect.iscoroutinefunction(route))

    def test_setup_plan_cannot_be_used_to_install(self):
        with mock.patch.object(
            self.api.setup_flow, "run", return_value={"ok": True}
        ) as run:
            self.api.setup_plan(
                {"action": "install", "server_url": "https://hs.example.com"}
            )
        self.assertEqual(run.call_args.args[0]["action"], "plan")

    def test_install_requires_literal_confirmation_before_dispatch(self):
        with mock.patch.object(
            self.api.setup_flow, "run", return_value={"ok": True}
        ) as run:
            for value in (None, False, 1, "true"):
                with (
                    self.subTest(value=value),
                    self.assertRaises(self.api.HTTPException),
                ):
                    self.api.setup_install({"confirmed": value})
            run.assert_not_called()
            self.api.setup_install({"confirmed": True, "action": "plan"})
            self.assertEqual(run.call_args.args[0]["action"], "install")

    def test_install_failure_preserves_recovery_state_for_the_desktop(self):
        failure = {
            "ok": False,
            "error": "Credential storage failed.",
            "installed": True,
            "stage": "credential_storage",
            "credential_revocation": "failed",
        }
        with (
            mock.patch.object(self.api.setup_flow, "run", return_value=failure),
            self.assertRaises(self.api.HTTPException) as raised,
        ):
            self.api.setup_install({"confirmed": True})
        self.assertIn("installed: True", raised.exception.detail)
        self.assertIn("credential revocation: failed", raised.exception.detail)

    def test_every_rpc_route_prepares_the_bundled_proto_path(self):
        user = types.SimpleNamespace(id=7, name="alice")

        def call(method, request):
            if method == "ListNodes":
                return types.SimpleNamespace(nodes=[])
            if method == "ExpireNode":
                return types.SimpleNamespace(node=object())
            if method == "ListPreAuthKeys":
                return types.SimpleNamespace(pre_auth_keys=[])
            if method == "ListUsers":
                return types.SimpleNamespace(users=[user])
            if method == "CreatePreAuthKey":
                return types.SimpleNamespace(pre_auth_key=object())
            raise AssertionError(method)

        with (
            mock.patch.dict(sys.modules, _fake_proto_modules()),
            mock.patch.object(self.api, "_run", return_value="active"),
            mock.patch.object(self.api.hsclient, "prepare_proto_path") as prepare,
            mock.patch.object(self.api.hsclient, "call", side_effect=call),
            mock.patch.object(self.api.hsclient, "node_to_dict", return_value={}),
            mock.patch.object(self.api.hsclient, "preauth_to_dict", return_value={}),
            mock.patch.object(self.api.hsclient, "timestamp_in", return_value=object()),
        ):
            self.api.status()
            self.api.nodes()
            self.api.expire_node(1)
            self.api.preauth()
            self.api.create_preauth({})

        self.assertEqual(prepare.call_count, 5)

    def test_create_normalizes_null_user_and_returns_new_secret(self):
        user = types.SimpleNamespace(id=7, name="alice")

        def call(method, request):
            if method == "ListUsers":
                return types.SimpleNamespace(users=[user])
            if method == "CreatePreAuthKey":
                return types.SimpleNamespace(pre_auth_key="new-key")
            raise AssertionError(method)

        with (
            mock.patch.dict(sys.modules, _fake_proto_modules()),
            mock.patch.object(self.api.hsclient, "call", side_effect=call),
            mock.patch.object(self.api.hsclient, "timestamp_in", return_value=object()),
            mock.patch.object(
                self.api.hsclient,
                "preauth_to_dict",
                return_value={"key": "join-secret"},
            ) as serialize,
        ):
            result = self.api.create_preauth({"user": None})

        self.assertEqual(result["key"]["key"], "join-secret")
        serialize.assert_called_once_with("new-key", include_key=True)

    def test_no_users_has_a_clear_error(self):
        with (
            mock.patch.dict(sys.modules, _fake_proto_modules()),
            mock.patch.object(
                self.api.hsclient,
                "call",
                return_value=types.SimpleNamespace(users=[]),
            ),
            self.assertRaises(self.api.HTTPException) as raised,
        ):
            self.api.create_preauth({})
        self.assertEqual(raised.exception.status_code, 404)
        self.assertIn("no Headscale users", raised.exception.detail)

    def test_expire_rejects_nonpositive_node_id_before_rpc(self):
        with mock.patch.object(self.api.hsclient, "call") as call:
            for node_id in (0, -1):
                with self.subTest(node_id=node_id):
                    with self.assertRaises(self.api.HTTPException) as raised:
                        self.api.expire_node(node_id)
                    self.assertEqual(raised.exception.status_code, 422)
        call.assert_not_called()

    def test_subprocess_nonzero_reports_stderr(self):
        completed = types.SimpleNamespace(
            stdout="", stderr="permission denied\n", returncode=1
        )
        with mock.patch.object(
            self.api.subprocess, "run", return_value=completed
        ) as run:
            result = self.api._run(["example"])
        self.assertEqual(result, "error (exit 1): permission denied")
        run.assert_called_once_with(
            ["example"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
