"""NetPlane dashboard backend: /api/plugins/netplane/* routes.

Wraps the local Headscale gRPC control plane for the desktop pane.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

# hsclient lives one level up (the plugin package dir).
_PKG = str(Path(__file__).resolve().parent.parent)
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

import hsclient  # noqa: E402

router = APIRouter()



def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


@router.get("/status")
async def status():
    out = {"control_url": hsclient.CONTROL_URL, "checks": {}}
    out["checks"]["headscale_service"] = _run(
        ["systemctl", "is-active", "headscale"])
    out["checks"]["serve"] = _run(["tailscale", "serve", "status"])[:1200]
    try:
        from headscale.v1 import node_pb2
        r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
        out["nodes_total"] = len(r.nodes)
        out["nodes_online"] = sum(1 for n in r.nodes if n.online)
    except Exception as e:  # noqa: BLE001
        out["nodes_error"] = str(e)
    return out


@router.get("/nodes")
async def nodes():
    from headscale.v1 import node_pb2
    try:
        r = hsclient.call("ListNodes", node_pb2.ListNodesRequest())
        return {"nodes": [hsclient.node_to_dict(n) for n in r.nodes]}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/nodes/{node_id}/expire")
async def expire_node(node_id: int):
    from headscale.v1 import node_pb2
    try:
        r = hsclient.call(
            "ExpireNode", node_pb2.ExpireNodeRequest(node_id=node_id))
        return {"ok": True, "node": hsclient.node_to_dict(r.node)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/preauth")
async def preauth():
    from headscale.v1 import preauthkey_pb2
    try:
        r = hsclient.call(
            "ListPreAuthKeys", preauthkey_pb2.ListPreAuthKeysRequest())
        return {"keys": [hsclient.preauth_to_dict(k)
                         for k in r.pre_auth_keys]}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/preauth")
async def create_preauth(body: dict):
    from headscale.v1 import preauthkey_pb2, user_pb2

    user = str(body.get("user", ""))
    hours = int(body.get("expiry_hours", 24))
    reusable = bool(body.get("reusable", True))
    from headscale.v1 import user_pb2
    try:
        users = hsclient.call("ListUsers", user_pb2.ListUsersRequest())
        if not user:
            user = users.users[0].name if users.users else ""
        uid = next((u.id for u in users.users if u.name == user), None)
        if uid is None:
            raise HTTPException(status_code=404,
                                 detail=f"unknown user {user!r}")
        req = preauthkey_pb2.CreatePreAuthKeyRequest(
            user=uid, reusable=reusable, ephemeral=False,
            expiration=hsclient.timestamp_in(hours * 3600))
        r = hsclient.call("CreatePreAuthKey", req)
        return {"key": hsclient.preauth_to_dict(r.pre_auth_key)}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e
