"""Approved Headscale bootstrap with credentials stored only through Hermes."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.parse
from pathlib import Path
from typing import Any

_ctx: Any = None
_SETUP_LOCK = threading.Lock()
_HELPER = Path(__file__).resolve().with_name("provision.py")
_SECRET_NAME = "NETPLANE_APIKEY"
_DEFAULT_SETTINGS = {
    "grpc_addr": "127.0.0.1:50443",
    "control_url": "",
    "grpc_tls_server_name": "",
}
_CHILD_ENV = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}


def configure(ctx: Any) -> None:
    """Retain the context, without inspecting or changing a profile at load time."""
    global _ctx
    _ctx = ctx


def plan(args: dict) -> dict:
    """Describe installation without invoking a subprocess or touching credentials."""
    try:
        from .provision import build_plan

        return {**build_plan(args), "ok": True, "action": "plan"}
    except (ImportError, TypeError, ValueError, RuntimeError):
        return {
            "ok": False,
            "action": "plan",
            "error": "Setup needs a supported Debian/Ubuntu Linux host, an HTTPS server_url and valid TLS settings.",
        }


def _secret_api():
    from agent.secret_scope import get_secret
    from hermes_cli.config import (
        require_env_writable,
        save_env_value_secure,
    )

    functions = (
        get_secret,
        save_env_value_secure,
        require_env_writable,
    )
    if not all(callable(fn) for fn in functions):
        raise RuntimeError("Hermes credential storage is unavailable")
    return functions


def _settings() -> dict:
    return {
        key: _ctx.get_config(key, default) or default
        for key, default in _DEFAULT_SETTINGS.items()
    }


def _helper(action: str, payload: dict) -> dict:
    """Run a fixed helper, with no ambient secrets and no terminal prompt."""
    if action not in {"install", "bootstrap-key", "revoke-key"}:
        raise ValueError("Unknown setup action")
    budget, grace, outer_timeout = (
        (330, 15, 355) if action == "install" else (30, 5, 40)
    )
    # The privileged supervisor owns its helper's process group. It first sends
    # TERM so the helper can stop children and retain recoverable setup state;
    # the outer timeout is longer than its TERM + KILL deadline.
    command = [
        "/usr/bin/timeout",
        "--signal=TERM",
        f"--kill-after={grace}s",
        f"{budget}s",
        "/usr/bin/python3",
        "-I",
        str(_HELPER),
        "--action",
        action,
    ]
    if os.geteuid() != 0:
        command = ["/usr/bin/sudo", "-n", "--", *command]
    completed = subprocess.run(
        command,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=outer_timeout,
        check=False,
        shell=False,
        env=dict(_CHILD_ENV),
        cwd="/",
    )
    # Never propagate stdout, stderr, a CalledProcessError or its input: the
    # bootstrap response contains the only copy of the newly minted API key.
    if completed.returncode:
        raise RuntimeError("Headscale setup helper failed")
    try:
        result = json.loads(completed.stdout)
    except (TypeError, ValueError):
        raise RuntimeError(
            "Headscale setup helper returned an invalid response"
        ) from None
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError("Headscale setup helper failed")
    return result


def _failure(stage: str, message: str, *, installed: bool = False, **extra) -> dict:
    return {
        "ok": False,
        "action": "install",
        "stage": stage,
        "installed": installed,
        "error": message,
        **extra,
    }


def _discard_key(prefix: str, key: str, get_secret) -> dict:
    """Revoke the exact server key; never race another writer to the Hermes store."""
    try:
        _helper("revoke-key", {"prefix": prefix})
        revoked = True
    except Exception:  # noqa: BLE001 - credential-bearing exception details stay private
        revoked = False
    try:
        # Hermes exposes no compare-and-delete API. A scope read may be a
        # snapshot, so deleting here could erase a concurrent replacement.
        cleanup = "manual_required" if get_secret(_SECRET_NAME) == key else "not_needed"
    except Exception:  # noqa: BLE001 - credential-bearing exception details stay private
        cleanup = "manual_required"
    return {
        "credential_revocation": "revoked" if revoked else "failed",
        "credential_cleanup": cleanup,
    }


def run(args: dict) -> dict:
    """Plan by default; install only after the caller's Hermes approval hook."""
    if not isinstance(args, dict):
        return _failure("validation", "Setup arguments must be an object.")
    action = args.get("action", "plan")
    if action == "plan":
        return plan(args)
    if action != "install":
        return _failure("validation", "Setup action must be plan or install.")
    if not _SETUP_LOCK.acquire(blocking=False):
        return _failure(
            "preflight", "Another NetPlane installation is already running."
        )
    try:
        return _install(args)
    finally:
        _SETUP_LOCK.release()


def _install(args: dict) -> dict:
    try:
        from .provision import validate_options

        options = validate_options(args)
    except (ImportError, TypeError, ValueError, RuntimeError):
        return _failure(
            "validation", "Invalid setup options; review the installation plan first."
        )
    if _ctx is None or not callable(getattr(_ctx, "set_config", None)):
        return _failure(
            "preflight", "Hermes plugin settings storage is unavailable; update Hermes."
        )
    try:
        get_secret, save_secret, require_writable = _secret_api()
        if get_secret(_SECRET_NAME):
            return _failure(
                "preflight",
                "This Hermes profile already has a Headscale API key; setup will not replace it.",
            )
        initial_settings = _settings()
        if initial_settings != _DEFAULT_SETTINGS:
            return _failure(
                "preflight",
                "This Hermes profile already has custom NetPlane connection settings; setup will not replace them.",
            )
        require_writable(_SECRET_NAME, "set")
    except Exception:  # noqa: BLE001 - credential-bearing exception details stay private
        return _failure(
            "preflight",
            "Hermes credential storage is unavailable or managed by an administrator; no installation was attempted.",
        )

    try:
        result = _helper("install", options)
    except Exception:  # noqa: BLE001 - helper output must never reach the chat
        return _failure(
            "installation",
            "Headscale installation did not complete. Review the host service and setup prerequisites before retrying; existing installation files are preserved.",
            installation_state="unknown",
        )
    expected = {
        "grpc_addr": result.get("grpc_addr"),
        "control_url": result.get("control_url"),
        "grpc_tls_server_name": result.get("grpc_tls_server_name", ""),
    }
    tls_name = (
        urllib.parse.urlsplit(options["server_url"]).hostname
        if options["tls_mode"] == "letsencrypt"
        else ""
    )
    if (
        result.get("installed") is not True
        or expected["grpc_addr"] != _DEFAULT_SETTINGS["grpc_addr"]
        or expected["control_url"] != options["server_url"]
        or expected["grpc_tls_server_name"] != tls_name
    ):
        return _failure(
            "configuration",
            "The helper returned unexpected connection settings; inspect the installed service before continuing.",
            installed=True,
        )
    try:
        if get_secret(_SECRET_NAME) or _settings() != initial_settings:
            return _failure(
                "configuration",
                "The active profile changed during installation; existing profile settings and credentials were preserved.",
                installed=True,
            )
        for key, value in expected.items():
            _ctx.set_config(key, value)
    except Exception:  # noqa: BLE001 - do not disclose context/storage internals
        return _failure(
            "configuration",
            "Headscale is installed, but Hermes connection settings could not be saved. Complete profile configuration before creating an API key.",
            installed=True,
        )

    try:
        if get_secret(_SECRET_NAME):
            return _failure(
                "credential",
                "A Headscale API key was added to this profile during setup; it was preserved.",
                installed=True,
            )
        credential = _helper("bootstrap-key", {})
    except Exception:  # noqa: BLE001 - helper output may contain a minted credential
        return _failure(
            "credential",
            "Headscale is installed and configured, but API-key creation was not confirmed. A key may have been minted; inspect Headscale API keys locally before completing credential setup through Hermes.",
            installed=True,
            credential_revocation="unknown",
        )
    key, prefix = credential.get("key"), credential.get("prefix")
    if not isinstance(key, str) or not key or not isinstance(prefix, str) or not prefix:
        # A malformed helper response may have minted an unidentifiable key.
        # Do not claim cleanup succeeded or expose that response to the model.
        return _failure(
            "credential",
            "Headscale is installed, but the new API key could not be identified. Review Headscale API keys locally before retrying credential setup.",
            installed=True,
            credential_revocation="unknown",
        )
    try:
        if get_secret(_SECRET_NAME):
            raise RuntimeError("A credential was added while setup was running")
        saved = save_secret(_SECRET_NAME, key)
        if not isinstance(saved, dict) or saved.get("success") is not True:
            raise RuntimeError("Credential storage did not confirm success")
        if get_secret(_SECRET_NAME) != key:
            raise RuntimeError("Credential storage did not update the active profile")
    except Exception:  # noqa: BLE001 - always revoke after any credential-storage failure
        cleanup = _discard_key(prefix, key, get_secret)
        return _failure(
            "credential_storage",
            "Headscale is installed and configured, but Hermes could not confirm its API key was saved. Review the revocation result; if local cleanup is required, remove or replace NETPLANE_APIKEY through Hermes before continuing.",
            installed=True,
            **cleanup,
        )
    return {
        "ok": True,
        "action": "install",
        "installed": True,
        "configured": True,
        "credentials_saved": True,
        "api_key_expiry_days": 90,
        "control_url": expected["control_url"],
        "grpc_addr": expected["grpc_addr"],
        "grpc_tls_server_name": expected["grpc_tls_server_name"],
        "public_endpoint_verified": False,
    }
