"""NetPlane dashboard backend: /api/plugins/netplane/* routes.

Wraps the configured Headscale gRPC control plane for the desktop pane.
"""

from __future__ import annotations

import subprocess

from fastapi import APIRouter, HTTPException

# Dashboard APIs load as top-level modules, so import the agent package's
# client explicitly to share its live Hermes context and secret scope.
from hermes_plugins.netplane import hsclient

router = APIRouter()


def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"error: {exc}"
    stdout = result.stdout.strip()
    if result.returncode == 0:
        return stdout
    detail = result.stderr.strip() or stdout or "no output"
    return f"error (exit {result.returncode}): {detail}"


@router.get("/status")
def status():
    out = {"control_url": hsclient.control_url(), "checks": {}}
    out["checks"]["headscale_service"] = _run(["systemctl", "is-active", "headscale"])
    out["checks"]["serve"] = _run(["tailscale", "serve", "status"])[:1200]
    try:
        hsclient.prepare_proto_path()
        from headscale.v1 import node_pb2

        r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
        out["nodes_total"] = len(r.nodes)
        out["nodes_online"] = sum(1 for n in r.nodes if n.online)
    except Exception as exc:  # noqa: BLE001 - status reports degraded health
        out["nodes_error"] = str(exc)
    return out


@router.get("/nodes")
def nodes():
    hsclient.prepare_proto_path()
    from headscale.v1 import node_pb2

    try:
        r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
        return {"nodes": [hsclient.node_to_dict(n) for n in r.nodes]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/nodes/{node_id}/expire")
def expire_node(node_id: int):
    if node_id < 1:
        raise HTTPException(status_code=422, detail="node_id must be positive")
    hsclient.prepare_proto_path()
    from headscale.v1 import node_pb2

    try:
        r = hsclient.call("ExpireNode", node_pb2.ExpireNodeRequest(node_id=node_id))
        return {"ok": True, "node": hsclient.node_to_dict(r.node)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/preauth")
def preauth():
    hsclient.prepare_proto_path()
    from headscale.v1 import preauthkey_pb2

    try:
        r = hsclient.call("ListPreAuthKeys", preauthkey_pb2.ListPreAuthKeysRequest())
        return {"keys": [hsclient.preauth_to_dict(k) for k in r.pre_auth_keys]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/preauth")
def create_preauth(body: dict):
    hsclient.prepare_proto_path()
    from headscale.v1 import preauthkey_pb2, user_pb2

    user = str(body.get("user") or "")
    raw_hours = body.get("expiry_hours", 24)
    if isinstance(raw_hours, bool) or not isinstance(raw_hours, int):
        raise HTTPException(status_code=422, detail="expiry_hours must be an integer")
    hours = max(1, min(raw_hours, 168))
    reusable = body.get("reusable", False)
    if not isinstance(reusable, bool):
        raise HTTPException(status_code=422, detail="reusable must be a boolean")
    try:
        users = hsclient.call("ListUsers", user_pb2.ListUsersRequest())
        if not user:
            user = users.users[0].name if users.users else ""
        if not user:
            raise HTTPException(
                status_code=404,
                detail="no Headscale users exist; create a user first",
            )
        uid = next((u.id for u in users.users if u.name == user), None)
        if uid is None:
            raise HTTPException(status_code=404, detail=f"unknown user {user!r}")
        req = preauthkey_pb2.CreatePreAuthKeyRequest(
            user=uid,
            reusable=reusable,
            ephemeral=False,
            expiration=hsclient.timestamp_in(hours * 3600),
        )
        r = hsclient.call("CreatePreAuthKey", req)
        return {"key": hsclient.preauth_to_dict(r.pre_auth_key, include_key=True)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
