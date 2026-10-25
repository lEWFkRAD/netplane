"""Agent tools for the netplane plugin (self-hosted Headscale control plane)."""
from __future__ import annotations

import json
import os
import subprocess

from . import hsclient


def _handler(name):
    def wrap(fn):
        fn.__name__ = name
        return fn
    return wrap


@_handler("netplane_status")
def netplane_status() -> str:
    """Overall control-plane health: headscale service, serve wiring, node counts."""
    import subprocess

    out = {"checks": {}}
    try:
        st = subprocess.run(
            ["systemctl", "is-active", "headscale"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        out["checks"]["headscale_service"] = st
    except Exception as e:  # noqa: BLE001
        out["checks"]["headscale_service"] = f"error: {e}"
    try:
        r = subprocess.run(
            ["tailscale", "serve", "status"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        out["checks"]["serve"] = r.strip()[:800]
    except Exception as e:  # noqa: BLE001
        out["checks"]["serve"] = f"error: {e}"
    try:
        from headscale.v1 import node_pb2
        r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
        nodes = [hsclient.node_to_dict(n) for n in r.nodes]
        out["nodes_total"] = len(nodes)
        out["nodes_online"] = sum(1 for n in nodes if n["online"])
    except Exception as e:  # noqa: BLE001
        out["nodes_error"] = str(e)
    out["control_url"] = hsclient.CONTROL_URL
    return json.dumps(out, indent=2)


@_handler("netplane_nodes")
def netplane_nodes() -> str:
    """List every node registered on the self-hosted tailnet with online state."""
    from headscale.v1 import node_pb2

    r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
    return json.dumps([hsclient.node_to_dict(n) for n in r.nodes], indent=2)


@_handler("netplane_preauth")
def netplane_preauth(create: bool = False, user: str = "",
                     reusable: bool = True, expiry_hours: int = 24) -> str:
    """List preauth keys, or create one (join token) for a new device."""
    from headscale.v1 import preauthkey_pb2, user_pb2

    if create:
        users = hsclient.call("ListUsers", user_pb2.ListUsersRequest())
        if not user:
            user = users.users[0].name if users.users else ""
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
        return json.dumps(hsclient.preauth_to_dict(r.pre_auth_key), indent=2)

    r = hsclient.call("ListPreAuthKeys", preauthkey_pb2.ListPreAuthKeysRequest())
    return json.dumps(
        [hsclient.preauth_to_dict(k) for k in r.pre_auth_keys], indent=2)


_PROPS = {
    "netplane_preauth": {
        "create": {"type": "boolean", "description": "Create a new preauth key instead of listing"},
        "user": {"type": "string", "description": "Headscale user to create the key for"},
        "reusable": {"type": "boolean", "description": "Key can be used for multiple devices"},
        "expiry_hours": {"type": "integer", "description": "Hours until the key expires"},
    },
}


def register(ctx) -> None:
    for fn in (netplane_status, netplane_nodes, netplane_preauth):
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
