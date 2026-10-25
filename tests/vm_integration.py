"""Destructive integration test for a fresh, disposable systemd VM only.

Run inside the guest, never on the development host::

    python3 tests/vm_integration.py --allow-disposable-vm \
        --hermes-root /opt/hermes-agent --plugin-source /opt/netplane

Hermes must already be installed. Its supported environment runner resolves the
plugin dependencies. The source must be a Git checkout; the test installs its
HEAD (or --ref), not uncommitted changes. No model/provider credential is needed.
The test installs a real Headscale service and leaves it for VM inspection.
Test join keys and the bootstrap API key are revoked; dispose of the VM afterward.
Only fixed stage names, safe status fields and the tested commit are printed,
never keys, tool responses, subprocess output, exception messages or captured logs.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


class CheckFailed(RuntimeError):
    def __init__(self, code: str, **details):
        super().__init__(code)
        self.details = details


def require(condition, code: str, **details) -> None:
    if not condition:
        raise CheckFailed(code, **details)


_STATUS_VALUES = {
    "setup_stage": {
        "validation",
        "preflight",
        "installation",
        "configuration",
        "credential",
        "credential_storage",
    },
    "installation_state": {"unknown"},
    "credential_revocation": {"revoked", "failed", "unknown"},
    "credential_cleanup": {"manual_required", "not_needed"},
    "diagnostic": {
        "environment_bootstrap",
        "dependency_resolution",
        "network_download",
        "plugin_scan",
        "permission",
        "unclassified",
        "timeout",
    },
    "exception_kind": {
        "timeout",
        "missing_file",
        "permission",
        "invalid_json",
        "unexpected",
    },
}
_BOOL_FIELDS = {"installed", "configured", "credentials_saved"}


def setup_details(outcome) -> dict:
    """Only known states leave the guest; arbitrary response text never does."""
    if not isinstance(outcome, dict):
        return {}
    result = {}
    for field in (
        "stage",
        "installation_state",
        "credential_revocation",
        "credential_cleanup",
    ):
        target = "setup_stage" if field == "stage" else field
        value = outcome.get(field)
        if isinstance(value, str) and value in _STATUS_VALUES[target]:
            result[target] = value
    for field in _BOOL_FIELDS:
        if isinstance(outcome.get(field), bool):
            result[field] = outcome[field]
    return result


def safe_receipt(item) -> bool:
    """Reject unexpected child output, including secret-shaped status values."""
    fields = (
        {"stage", "ok", "error", "cleanup", "exit_status"}
        | set(_STATUS_VALUES)
        | _BOOL_FIELDS
    )
    if not isinstance(item, dict) or not set(item) <= fields:
        return False
    if not isinstance(item.get("ok"), bool) or "stage" not in item:
        return False
    for field in ("stage", "error", "cleanup"):
        if field in item and not (
            isinstance(item[field], str) and re.fullmatch(r"[a-z0-9_]+", item[field])
        ):
            return False
    for field, allowed in _STATUS_VALUES.items():
        if field in item and (
            not isinstance(item[field], str) or item[field] not in allowed
        ):
            return False
    if any(
        field in item and not isinstance(item[field], bool) for field in _BOOL_FIELDS
    ):
        return False
    return "exit_status" not in item or (
        type(item["exit_status"]) is int and -128 <= item["exit_status"] <= 255
    )


def command_details(result) -> dict:
    """Classify captured CLI output without reproducing any of it."""
    captured = (result.stdout + "\n" + result.stderr).lower()
    diagnostic = "unclassified"
    for markers, category in (
        (("permission denied", "operation not permitted"), "permission"),
        (
            (
                "no bootstrap python",
                "failed to download pinned uv",
                "uv download digest",
                "sha256 mismatch for uv",
            ),
            "environment_bootstrap",
        ),
        (
            ("failed to download", "could not resolve host", "connection timed out"),
            "network_download",
        ),
        (
            ("no solution found", "failed to resolve", "dependency resolution"),
            "dependency_resolution",
        ),
        (("scan blocked", "security scan", "scan failed"), "plugin_scan"),
    ):
        if any(marker in captured for marker in markers):
            diagnostic = category
            break
    return {"exit_status": result.returncode, "diagnostic": diagnostic}


def exception_details(exc: Exception) -> dict:
    if isinstance(exc, CheckFailed):
        return {"error": str(exc), **exc.details}
    category = "unexpected"
    for kind, value in (
        (subprocess.TimeoutExpired, "timeout"),
        (FileNotFoundError, "missing_file"),
        (PermissionError, "permission"),
        (json.JSONDecodeError, "invalid_json"),
    ):
        if isinstance(exc, kind):
            category = value
            break
    return {"error": "integration_exception", "exception_kind": category}


def report(stage: str, ok: bool = True, **fields) -> None:
    print(
        json.dumps({"stage": stage, "ok": ok, **fields}),
        flush=True,
        file=sys.__stdout__,
    )


def run_command(command: list[str], *, cwd: Path | None = None, env=None, timeout=60):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def guest_guard(allowed: bool) -> None:
    require(allowed, "explicit_disposable_vm_flag_required")
    require(hasattr(os, "geteuid") and os.geteuid() == 0, "guest_root_required")
    require(Path("/run/systemd/system").is_dir(), "systemd_guest_required")
    virtual = run_command(["/usr/bin/systemd-detect-virt", "--vm"], timeout=10)
    require(
        virtual.returncode == 0 and bool(virtual.stdout.strip()),
        "virtual_machine_required",
    )


def clean_environment(profile: Path) -> dict:
    # run-in-hermes-env bootstraps pinned uv/Python by absolute paths into this
    # fresh store. Neither an ambient uv nor an activated host profile is used.
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(Path.home()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HERMES_HOME": str(profile),
        "HERMES_RUNTIME_DIR": str(profile / "runtime"),
    }


def install_and_exercise(args) -> None:
    root, source = args.hermes_root.resolve(), args.plugin_source.resolve()
    runner = root / "scripts/run-in-hermes-env"
    require(runner.is_file(), "hermes_environment_runner_missing")
    require((source / "plugin.yaml").is_file(), "plugin_source_missing")
    revision = run_command(["git", "-C", str(source), "rev-parse", args.ref or "HEAD"])
    require(revision.returncode == 0, "plugin_git_revision_missing")
    commit = revision.stdout.strip()
    require(
        bool(re.fullmatch(r"[a-f0-9]{40}", commit)),
        "immutable_plugin_revision_required",
    )
    require(not Path("/etc/headscale").exists(), "fresh_guest_required")
    command = ["/usr/bin/bash", str(runner), "python3", "-m", "hermes_cli.main"]
    with tempfile.TemporaryDirectory(prefix="netplane-vm-profile-") as temp:
        profile = Path(temp)
        env = clean_environment(profile)
        commands = [
            (
                "plugin_install",
                [
                    "plugins",
                    "install",
                    source.as_uri(),
                    "--ref",
                    commit,
                    "--force",
                    "--yes-deps",
                    "--no-enable",
                ],
            ),
            ("plugin_enable", ["plugins", "enable", "netplane"]),
            ("manual_approval_profile", ["config", "set", "approvals.mode", "manual"]),
        ]
        for stage, suffix in commands:
            report(stage + "_started")
            try:
                result = run_command(command + suffix, cwd=root, env=env, timeout=1800)
            except subprocess.TimeoutExpired:
                raise CheckFailed(stage + "_failed", diagnostic="timeout") from None
            require(
                result.returncode == 0, stage + "_failed", **command_details(result)
            )
            report(stage)
        exercise = [
            "/usr/bin/bash",
            str(runner),
            "python3",
            str(Path(__file__).resolve()),
            "--allow-disposable-vm",
            "--phase",
            "exercise",
            "--profile",
            str(profile),
            "--hermes-root",
            str(root),
            "--plugin-source",
            str(source),
        ]
        report("guest_exercise_started", commit=commit)
        result = run_command(exercise, cwd=root, env=env, timeout=900)
        # The exercise prints only this harness's JSON receipts. Refuse any
        # unexpected output rather than forwarding diagnostics or credentials.
        receipts = []
        for line in result.stdout.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if safe_receipt(item):
                receipts.append(item)
        for item in receipts:
            print(json.dumps(item), flush=True, file=sys.__stdout__)
        require(
            result.returncode == 0, "guest_exercise_failed", **command_details(result)
        )
        require(
            any(
                item.get("stage") == "complete" and item.get("ok") is True
                for item in receipts
            ),
            "guest_completion_receipt_missing",
        )
        report("vm_integration_complete", commit=commit)


def exercise(args) -> None:
    profile = args.profile.resolve()
    require(
        profile == Path(os.environ.get("HERMES_HOME", "")).resolve(), "profile_mismatch"
    )
    require(
        profile.name.startswith("netplane-vm-profile-"), "fresh_test_profile_required"
    )
    installed = profile / "plugins/netplane"
    require((installed / "plugin.yaml").is_file(), "plugin_install_not_found")
    require(not Path("/etc/headscale").exists(), "fresh_guest_required")
    # Capture any third-party output in memory. No logging handlers or exception
    # tracebacks may accidentally print the credential returned by a create call.
    logging.disable(logging.CRITICAL)
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        _exercise_tools(profile, installed)


def _exercise_tools(profile: Path, installed: Path) -> None:
    from agent.secret_scope import (
        build_profile_secret_scope,
        get_secret,
        reset_secret_scope,
        set_secret_scope,
    )
    from hermes_cli.config import get_env_path, load_config_readonly, remove_env_value
    from hermes_cli.plugins import discover_plugins, get_pre_tool_call_directive
    from model_tools import handle_function_call
    from tools.approval_context import (
        reset_hermes_interactive_context,
        set_hermes_interactive_context,
    )
    from tools.registry import registry
    from tools.terminal_tool import set_approval_callback

    require(
        load_config_readonly().get("approvals", {}).get("mode") == "manual",
        "manual_approval_not_active",
    )
    scope_token = set_secret_scope(
        build_profile_secret_scope(profile), profile_home=str(profile)
    )
    interactive_token = set_hermes_interactive_context(True)
    expected_approval = {"tool": None, "choice": "deny", "calls": 0}
    api_key = ""
    join_id = None
    channel = None
    rpc = None
    uncertain_credentials = False
    stage = "plugin_discovery"

    def answer(command, _description, **_kwargs):
        tool = expected_approval["tool"]
        require(tool and command.startswith(f"<{tool}>"), "unexpected_approval_request")
        expected_approval["calls"] += 1
        return expected_approval["choice"]

    def call(name, values, *, choice=None):
        expected_approval.update(
            tool=name if choice else None, choice=choice or "deny", calls=0
        )
        result = handle_function_call(
            name,
            values,
            task_id="netplane-vm-integration",
            session_id="netplane-vm-integration",
            enabled_tools=[
                "netplane_setup",
                "netplane_status",
                "netplane_nodes",
                "netplane_preauth",
            ],
        )
        require(
            expected_approval["calls"] == (1 if choice else 0),
            "approval_dispatch_contract_failed",
        )
        require(isinstance(result, str), "tool_result_not_text")
        return json.loads(result)

    set_approval_callback(answer)
    try:
        discover_plugins(force=True)
        for name in (
            "netplane_setup",
            "netplane_status",
            "netplane_nodes",
            "netplane_preauth",
        ):
            require(registry.get_entry(name) is not None, "registered_tool_missing")
        require(not get_secret("NETPLANE_APIKEY"), "fresh_profile_has_api_key")
        report(stage)
        options = {
            "server_url": "https://headscale.vm.example.com",
            "tls_mode": "reverse_proxy",
            "base_domain": "vm.tailnet.internal",
            "headscale_user": "vmtest",
        }
        stage = "setup_plan"
        plan = call("netplane_setup", options)
        require(
            plan.get("ok") is True and plan.get("action") == "plan", "setup_plan_failed"
        )
        require(not Path("/etc/headscale").exists(), "plan_mutated_host")
        report(stage)
        stage = "setup_approval_denied"
        directive, _message = get_pre_tool_call_directive(
            "netplane_setup", {**options, "action": "install"}
        )
        require(directive == "approve", "setup_approval_hook_missing")
        refused = call(
            "netplane_setup", {**options, "action": "install"}, choice="deny"
        )
        require(
            "error" in refused and not Path("/etc/headscale").exists(),
            "denied_setup_mutated_host",
        )
        report(stage)
        stage = "setup_install"
        uncertain_credentials = True
        outcome = call(
            "netplane_setup", {**options, "action": "install"}, choice="once"
        )
        require(
            outcome.get("ok") is True and outcome.get("credentials_saved") is True,
            "setup_install_failed",
            **setup_details(outcome),
        )
        # A separate plugin host may have saved the key; reload this caller's
        # profile through Hermes before inspecting persistence or making probes.
        reset_secret_scope(scope_token)
        scope_token = set_secret_scope(
            build_profile_secret_scope(profile), profile_home=str(profile)
        )
        api_key = get_secret("NETPLANE_APIKEY") or ""
        require(
            bool(
                re.fullmatch(r"hskey-api-[A-Za-z0-9_-]{12}-[A-Za-z0-9_-]{64}", api_key)
            ),
            "bootstrap_key_not_persisted",
        )
        require(api_key not in json.dumps(outcome), "setup_returned_api_key")
        require(
            get_env_path().stat().st_mode & 0o077 == 0,
            "credential_file_permissions_too_open",
        )
        require(
            outcome.get("public_endpoint_verified") is False,
            "unverified_public_endpoint_claim",
        )
        report(stage)

        sys.path.insert(0, str(installed / "proto"))
        import grpc
        from headscale.v1 import (
            apikey_pb2,
            headscale_pb2_grpc,
            node_pb2,
            preauthkey_pb2,
        )

        channel = grpc.insecure_channel("127.0.0.1:50443")
        client = headscale_pb2_grpc.HeadscaleServiceStub(channel)

        def rpc(method, request):
            return getattr(client, method)(
                request, metadata=[("authorization", "Bearer " + api_key)], timeout=10
            )

        stage = "management_calls"
        status = call("netplane_status", {})
        require(
            status.get("checks", {}).get("headscale_service") == "active",
            "service_not_active",
        )
        require(
            status.get("nodes_total") == 0 and "nodes_error" not in status,
            "grpc_health_failed",
        )
        require(call("netplane_nodes", {}) == [], "fresh_node_inventory_not_empty")
        require(
            call("netplane_preauth", {"create": False}) == [],
            "fresh_join_key_inventory_not_empty",
        )
        report(stage)
        stage = "join_key_lifecycle"
        denied = call(
            "netplane_preauth", {"create": True, "expiry_hours": 1}, choice="deny"
        )
        require(
            "error" in denied and call("netplane_preauth", {}) == [],
            "denied_key_creation_mutated_server",
        )
        created = call(
            "netplane_preauth", {"create": True, "expiry_hours": 1}, choice="once"
        )
        join_id = created.get("id")
        require(
            isinstance(join_id, int)
            and bool(created.get("key"))
            and created.get("reusable") is False,
            "join_key_creation_contract_failed",
        )
        listed = call("netplane_preauth", {})
        require(
            len(listed) == 1
            and "key" not in listed[0]
            and created["key"] not in json.dumps(listed),
            "join_key_listing_exposes_secret",
        )
        rpc("ExpirePreAuthKey", preauthkey_pb2.ExpirePreAuthKeyRequest(id=join_id))
        rpc("DeletePreAuthKey", preauthkey_pb2.DeletePreAuthKeyRequest(id=join_id))
        join_id = None
        require(call("netplane_preauth", {}) == [], "join_key_cleanup_failed")
        report(stage)
        stage = "second_install_refused"
        existing_keys = rpc("ListApiKeys", apikey_pb2.ListApiKeysRequest())
        refused = call(
            "netplane_setup", {**options, "action": "install"}, choice="once"
        )
        require(
            refused.get("ok") is False and refused.get("stage") == "preflight",
            "existing_setup_not_refused",
        )
        require(
            len(rpc("ListApiKeys", apikey_pb2.ListApiKeysRequest()).api_keys)
            == len(existing_keys.api_keys),
            "second_install_minted_key",
        )
        report(stage)
        stage = "bootstrap_key_revoked"
        prefix = api_key[len("hskey-api-") : len("hskey-api-") + 12]
        rpc("ExpireApiKey", apikey_pb2.ExpireApiKeyRequest(prefix=prefix))
        try:
            rpc("ListNodes", node_pb2.ListNodesRequest())
        except grpc.RpcError as exc:
            require(
                exc.code() == grpc.StatusCode.UNAUTHENTICATED,
                "expired_api_key_wrong_failure",
            )
        else:
            raise CheckFailed("expired_api_key_still_accepted")
        remove_env_value("NETPLANE_APIKEY")
        require(not get_secret("NETPLANE_APIKEY"), "profile_key_cleanup_failed")
        api_key = ""
        uncertain_credentials = False
        report(stage)
        report("complete")
    except Exception as exc:  # noqa: BLE001 - never print credential-bearing exception details
        report(stage, False, **exception_details(exc))
        raise CheckFailed("guest_tool_exercise_failed") from None
    finally:
        cleanup = not uncertain_credentials
        if rpc is not None and api_key:
            try:
                if join_id is not None:
                    rpc(
                        "DeletePreAuthKey",
                        preauthkey_pb2.DeletePreAuthKeyRequest(id=join_id),
                    )
                rpc(
                    "ExpireApiKey",
                    apikey_pb2.ExpireApiKeyRequest(prefix=api_key[10:22]),
                )
                remove_env_value("NETPLANE_APIKEY")
                cleanup = True
            except Exception:  # noqa: BLE001 - cleanup errors may contain bearer metadata
                cleanup = False
        if channel is not None:
            channel.close()
        set_approval_callback(None)
        reset_hermes_interactive_context(interactive_token)
        reset_secret_scope(scope_token)
        report(
            "fixture_cleanup", cleanup, cleanup="complete" if cleanup else "dispose_vm"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-disposable-vm", action="store_true")
    parser.add_argument("--hermes-root", type=Path, required=True)
    parser.add_argument("--plugin-source", type=Path, required=True)
    parser.add_argument("--ref", default="")
    parser.add_argument(
        "--phase", choices=("all", "exercise"), default="all", help=argparse.SUPPRESS
    )
    parser.add_argument("--profile", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        guest_guard(args.allow_disposable_vm)
        if args.phase == "exercise":
            require(args.profile is not None, "profile_argument_required")
            exercise(args)
        else:
            install_and_exercise(args)
        return 0
    except Exception as exc:  # noqa: BLE001 - only stable harness failure codes leave the guest
        report("harness", False, **exception_details(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
