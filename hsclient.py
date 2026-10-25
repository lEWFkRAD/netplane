"""Shared Headscale gRPC client for the netplane plugin.

Configuration is resolved through Hermes for every call. Credentials come
only from the active profile's secret scope; they are never cached here or
read directly from process environment or disk.
"""

from __future__ import annotations

import datetime as _dt
import ipaddress
import os
import sys
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PROTO_DIR = os.path.join(_HERE, "proto")
_DEFAULT_GRPC_ADDR = "127.0.0.1:50443"
_ctx: Any = None

if _DEFAULT_PROTO_DIR not in sys.path:
    sys.path.insert(0, _DEFAULT_PROTO_DIR)


def configure(ctx: Any) -> None:
    """Retain the plugin context so settings can be read at invocation time."""
    global _ctx
    _ctx = ctx


def _config(key: str, default: Any) -> Any:
    if _ctx is None:
        return default
    return _ctx.get_config(key, default)


def grpc_addr() -> str:
    return str(_config("grpc_addr", _DEFAULT_GRPC_ADDR) or _DEFAULT_GRPC_ADDR)


def control_url() -> str:
    return str(_config("control_url", "") or "")


def prepare_proto_path() -> str:
    """Make this package's bundled generated stubs importable."""
    if _DEFAULT_PROTO_DIR not in sys.path:
        sys.path.insert(0, _DEFAULT_PROTO_DIR)
    return _DEFAULT_PROTO_DIR


def read_apikey() -> str:
    """Read the active Hermes profile's Headscale credential."""
    from agent.secret_scope import get_secret

    key = (get_secret("NETPLANE_APIKEY") or "").strip()
    if not key:
        raise RuntimeError(
            "NETPLANE_APIKEY is not configured in the active Hermes secret scope"
        )
    return key


def timestamp_in(seconds: int):
    """Return a protobuf Timestamp for now plus *seconds*."""
    import time

    prepare_proto_path()
    from google.protobuf import timestamp_pb2

    ts = timestamp_pb2.Timestamp()
    ts.FromJsonString(
        _dt.datetime.fromtimestamp(time.time() + seconds, _dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )
    return ts


def _is_loopback_target(target: str) -> bool:
    """Return whether a gRPC target is confined to this host."""
    value = target.strip()
    if value.startswith(("unix:", "unix-abstract:")):
        return True
    for prefix in ("dns:///", "ipv4:", "ipv6:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if value.startswith("["):
        end = value.find("]")
        host = value[1:end] if end >= 0 else value
    else:
        try:
            return ipaddress.ip_address(value.split("%", 1)[0]).is_loopback
        except ValueError:
            host = value.rsplit(":", 1)[0] if ":" in value else value
    host = host.strip("[]").split("%", 1)[0].lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _channel():
    import grpc

    target = grpc_addr()
    if _is_loopback_target(target):
        return grpc.insecure_channel(target)
    credentials = grpc.ssl_channel_credentials()
    return grpc.secure_channel(target, credentials)


def _new_stub():
    prepare_proto_path()
    from headscale.v1 import headscale_pb2_grpc

    channel = _channel()
    return channel, headscale_pb2_grpc.HeadscaleServiceStub(channel)


def call(method: str, request, timeout: float = 5.0):
    """Invoke a Headscale RPC using the current profile's API key."""
    key = read_apikey()
    channel, service = _new_stub()
    try:
        fn = getattr(service, method)
        return fn(
            request,
            metadata=[("authorization", f"Bearer {key}")],
            timeout=timeout,
        )
    finally:
        close = getattr(channel, "close", None)
        if callable(close):
            close()


def node_to_dict(n) -> dict:
    return {
        "id": n.id,
        "hostname": n.name,
        "given_name": n.given_name,
        "user": n.user.name if n.HasField("user") else "",
        "ips": list(n.ip_addresses),
        "online": n.online,
        "expiry": n.expiry.ToJsonString() if n.HasField("expiry") else "",
        "tags": list(n.tags),
        "last_seen": n.last_seen.ToJsonString() if n.HasField("last_seen") else "",
        "created": n.created_at.ToJsonString() if n.HasField("created_at") else "",
    }


def preauth_to_dict(k, *, include_key: bool = False) -> dict:
    """Serialize a preauth key, hiding the join secret unless just created."""
    result = {
        "id": k.id,
        "user": k.user.name if k.HasField("user") else "",
        "reusable": k.reusable,
        "ephemeral": k.ephemeral,
        "expiration": k.expiration.ToJsonString() if k.HasField("expiration") else "",
        "created": k.created_at.ToJsonString() if k.HasField("created_at") else "",
        "last_used": "",
        "used": k.used,
    }
    if include_key:
        result["key"] = k.key
    return result
