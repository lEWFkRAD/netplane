"""Shared Headscale gRPC client for the netplane plugin.

Talks to the local Headscale control plane over its gRPC endpoint
(127.0.0.1:50443, grpc_allow_insecure). Generated protobuf stubs are
bundled in this package under proto/ (regenerate with scripts/gen_proto.sh).

Settings arrive via apply_settings() at register() time (plugin
config_schema keys grpc_addr / apikey_file / apikey / control_url /
proto_dir). Environment variables are a fallback for standalone use.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

PROTO_DIR = os.path.join(_HERE, "proto")
APIKEY_FILE = os.path.join(_HERE, "api.key")
APIKEY = ""
GRPC_ADDR = "127.0.0.1:50443"
CONTROL_URL = ""

if PROTO_DIR not in sys.path:
    sys.path.insert(0, PROTO_DIR)


def apply_settings(settings: dict) -> None:
    """Apply this plugin's config_schema settings (over env fallbacks)."""
    global PROTO_DIR, APIKEY_FILE, APIKEY, GRPC_ADDR, CONTROL_URL
    env = os.environ
    GRPC_ADDR = str(settings.get("grpc_addr") or env.get("NETPLANE_GRPC_ADDR")
                    or "127.0.0.1:50443")
    APIKEY = str(settings.get("apikey") or env.get("NETPLANE_APIKEY") or "")
    file = settings.get("apikey_file") or env.get("NETPLANE_APIKEY_FILE")
    APIKEY_FILE = os.path.expanduser(str(file)) if file else os.path.join(
        _HERE, "api.key")
    CONTROL_URL = str(settings.get("control_url")
                      or env.get("NETPLANE_CONTROL_URL") or "")
    proto = settings.get("proto_dir") or env.get("NETPLANE_PROTO_DIR")
    if proto:
        PROTO_DIR = os.path.expanduser(str(proto))
        if PROTO_DIR not in sys.path:
            sys.path.insert(0, PROTO_DIR)


def read_apikey() -> str:
    if APIKEY:
        return APIKEY
    with open(APIKEY_FILE, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def timestamp_in(seconds: int):
    """protobuf Timestamp for now + seconds."""
    import time

    from google.protobuf import timestamp_pb2

    ts = timestamp_pb2.Timestamp()
    ts.FromJsonString(_dt.datetime.fromtimestamp(
        time.time() + seconds, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return ts


def stub():
    import grpc

    from headscale.v1 import headscale_pb2_grpc

    channel = grpc.insecure_channel(GRPC_ADDR)
    return headscale_pb2_grpc.HeadscaleServiceStub(channel)


def call(method: str, request, timeout: float = 5.0):
    """Invoke a stub method with the Bearer apikey metadata."""
    import grpc

    key = read_apikey()
    stub_ = stub()
    fn = getattr(stub_, method)
    return fn(request, metadata=[("authorization", f"Bearer {key}")],
              timeout=timeout)


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


def preauth_to_dict(k) -> dict:
    return {
        "id": k.id,
        "key": k.key,
        "user": k.user.name if k.HasField("user") else "",
        "reusable": k.reusable,
        "ephemeral": k.ephemeral,
        "expiration": k.expiration.ToJsonString() if k.HasField("expiration") else "",
        "created": k.created_at.ToJsonString() if k.HasField("created_at") else "",
        "last_used": "",
        "used": k.used,
    }
