"""Agent tools for the netplane plugin (self-hosted Headscale control plane)."""

from __future__ import annotations

import json
import subprocess

from . import hsclient, setup_flow


def _handler(name):
    def wrap(fn):
        fn.__name__ = name
        return fn

    return wrap


def _run_status_command(command: list[str], limit: int = 800) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"
    stdout = result.stdout.strip()
    if result.returncode == 0:
        return stdout[:limit]
    detail = (result.stderr.strip() or stdout or "no output")[:limit]
    return f"error (exit {result.returncode}): {detail}"


@_handler("netplane_status")
def netplane_status(args: dict, **_kw) -> str:
    """Overall control-plane health: headscale service, serve wiring, node counts."""
    out = {
        "checks": {
            "headscale_service": _run_status_command(
                ["systemctl", "is-active", "headscale"]
            ),
            "serve": _run_status_command(["tailscale", "serve", "status"]),
        }
    }
    try:
        hsclient.prepare_proto_path()
        from headscale.v1 import node_pb2

        r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
        nodes = [hsclient.node_to_dict(n) for n in r.nodes]
        out["nodes_total"] = len(nodes)
        out["nodes_online"] = sum(1 for n in nodes if n["online"])
    except Exception as e:  # noqa: BLE001
        out["nodes_error"] = str(e)
    out["control_url"] = hsclient.control_url()
    return json.dumps(out, indent=2)


@_handler("netplane_nodes")
def netplane_nodes(args: dict, **_kw) -> str:
    """List every node registered on the self-hosted tailnet with online state."""
    hsclient.prepare_proto_path()
    from headscale.v1 import node_pb2

    r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
    return json.dumps([hsclient.node_to_dict(n) for n in r.nodes], indent=2)


@_handler("netplane_setup")
def netplane_setup(args: dict, **_kw) -> str:
    """Preview or install/configure Headscale on this Debian/Ubuntu host.

    Start with action=plan and a public HTTPS server_url. Installation requires
    approval and root or noninteractive sudo; it refuses existing installations.
    """
    return json.dumps(setup_flow.run(args), indent=2)


@_handler("netplane_preauth")
def netplane_preauth(args: dict, **_kw) -> str:
    """List preauth keys, or create one (join token) for a new device."""
    hsclient.prepare_proto_path()
    from headscale.v1 import preauthkey_pb2, user_pb2

    create = args.get("create", False) is True
    if create:
        user = str(args.get("user", "") or "")
        reusable_arg = args.get("reusable", False)
        if not isinstance(reusable_arg, bool):
            return json.dumps({"error": "reusable must be a boolean"})
        reusable = reusable_arg
        expiry_hours = args.get("expiry_hours", 24)
        if not isinstance(expiry_hours, int) or isinstance(expiry_hours, bool):
            return json.dumps({"error": "expiry_hours must be an integer"})
        expiry_hours = max(1, min(expiry_hours, 168))
        users = hsclient.call("ListUsers", user_pb2.ListUsersRequest())
        if not user:
            user = users.users[0].name if users.users else ""
        if not user:
            return json.dumps(
                {"error": "no Headscale users exist; create a user first"}
            )
        uid = next((u.id for u in users.users if u.name == user), None)
        if uid is None:
            return json.dumps({"error": f"unknown user {user!r}"})
        req = preauthkey_pb2.CreatePreAuthKeyRequest(
            user=uid,
            reusable=reusable,
            ephemeral=False,
            expiration=hsclient.timestamp_in(expiry_hours * 3600),
        )
        r = hsclient.call("CreatePreAuthKey", req)
        return json.dumps(
            hsclient.preauth_to_dict(r.pre_auth_key, include_key=True), indent=2
        )

    r = hsclient.call("ListPreAuthKeys", preauthkey_pb2.ListPreAuthKeysRequest())
    return json.dumps([hsclient.preauth_to_dict(k) for k in r.pre_auth_keys], indent=2)


def _approve_key_creation(
    tool_name: str = "", args: dict | None = None, **_kw
) -> dict | None:
    """Require explicit human approval before minting a join credential."""
    leaf_name = tool_name.rsplit(":", 1)[-1].rsplit("/", 1)[-1].rsplit(".", 1)[-1]
    if leaf_name == "netplane_setup" and isinstance(args, dict):
        if args.get("action", "plan") != "install":
            return None
        preview = setup_flow.plan(args)
        options = preview.get("options", {}) if preview.get("ok") else {}
        target = options.get("server_url", "the requested HTTPS endpoint")
        mode = options.get("tls_mode", "the requested TLS mode")
        owner = options.get("headscale_user", "the initial user")
        certificate = (
            f"Let's Encrypt will receive the domain and contact email {options['acme_email']}. "
            if mode == "letsencrypt" and options.get("acme_email")
            else "The existing HTTPS reverse proxy must be configured separately. "
        )
        return {
            "action": "approve",
            "message": (
                f"Install and configure Headscale for {target} ({mode}) "
                f"with initial user {owner} on the host running Hermes? "
                "This downloads the pinned official package, uses root privileges, "
                "writes /etc/headscale, enables and starts its system service, "
                "creates the first user, and saves a new API key and connection "
                f"settings in the active Hermes profile. {certificate}Review the setup plan "
                "for the domain, TLS mode and network listeners before approving."
            ),
        }
    if leaf_name != "netplane_preauth" or not isinstance(args, dict):
        return None
    if args.get("create", False) is not True:
        return None
    raw_user = str(args.get("user", "") or "")
    user = " ".join(
        "".join(char if char.isprintable() else " " for char in raw_user).split()
    )
    if not user:
        user = "the default Headscale user"
    elif len(user) > 80:
        user = f"{user[:79]}…"
    reusable = args.get("reusable", False) is True
    expiry_arg = args.get("expiry_hours", 24)
    if isinstance(expiry_arg, int) and not isinstance(expiry_arg, bool):
        expiry_hours = max(1, min(expiry_arg, 168))
    else:
        expiry_hours = 24
    use = "multiple devices" if reusable else "one device"
    return {
        "action": "approve",
        "message": (
            f"Create a Headscale preauth join key for {user}? "
            f"It will authorize {use} and expire in {expiry_hours} hours."
        ),
    }


_PROPS = {
    "netplane_setup": {
        "action": {
            "type": "string",
            "enum": ["plan", "install"],
            "default": "plan",
            "description": "Preview first; install applies the approved setup",
        },
        "server_url": {
            "type": "string",
            "description": "Public HTTPS URL devices use to reach Headscale",
        },
        "tls_mode": {
            "type": "string",
            "enum": ["letsencrypt", "reverse_proxy"],
            "default": "letsencrypt",
            "description": "Automatic TLS, or an existing HTTPS reverse proxy",
        },
        "acme_email": {
            "type": "string",
            "description": "Email for Let's Encrypt; required with letsencrypt",
        },
        "base_domain": {
            "type": "string",
            "default": "tailnet.internal",
            "description": "MagicDNS base domain, different from the server hostname",
        },
        "headscale_user": {
            "type": "string",
            "default": "hermes",
            "description": "Initial Headscale user to create",
        },
    },
    "netplane_preauth": {
        "create": {
            "type": "boolean",
            "description": "Create a new preauth key instead of listing",
        },
        "user": {
            "type": "string",
            "description": "Headscale user to create the key for",
        },
        "reusable": {
            "type": "boolean",
            "default": False,
            "description": "Key can be used for multiple devices",
        },
        "expiry_hours": {
            "type": "integer",
            "default": 24,
            "minimum": 1,
            "maximum": 168,
            "description": "Hours until the key expires (1-168)",
        },
    },
}


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _approve_key_creation)
    for fn in (netplane_setup, netplane_status, netplane_nodes, netplane_preauth):
        ctx.register_tool(
            name=fn.__name__,
            toolset="netplane",
            description=fn.__doc__ or fn.__name__,
            handler=fn,
            schema={
                "type": "object",
                "properties": _PROPS.get(fn.__name__, {}),
            },
        )
