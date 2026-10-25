"""Shared Headscale gRPC client for the netplane plugin.

Talks to the local Headscale control plane over its gRPC endpoint
(127.0.0.1:50443, grpc_allow_insecure). Generated protobuf stubs are
bundled in this package under proto/ (regenerate with scripts/gen_proto.sh).
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# Defaults: env vars first, overridable at register() time via plugin
# settings (config_schema keys grpc_addr / apikey_file / control_url /
# proto_dir). apply_settings() rewrites these module globals.
PROTO_DIR = os.environ.get(
    "NETPLANE_PROTO_DIR",
    os.path.join(_HERE, "proto"),
)
APIKEY_FILE = os.environ.get(
    "NETPLANE_APIKEY_FILE",
    os.path.join(_HERE, "api.key"),
)
GRPC_ADDR = os.environ.get("NETPLANE_GRPC_ADDR", "127.0.0.1:50443")
CONTROL_URL = os.environ.get(
    "NETPLANE_CONTROL_URL", "https://onyx-linux.tail3bf242.ts.net:8443")

if PROTO_DIR not in sys.path:
    sys.path.insert(0, PROTO_DIR)


def apply_settings(settings: dict) -> None:
    """Apply this plugin's config_schema settings over the env defaults."""
    global PROTO_DIR, APIKEY_FILE, GRPC_ADDR, CONTROL_URL
    if settings.get("grpc_addr"):
        GRPC_ADDR = str(settings["grpc_addr"])
    if settings.get("apikey_file"):
        APIKEY_FILE = os.path.expanduser(str(settings["apikey_file"]))
    if settings.get("control_url"):
        CONTROL_URL = str(settings["control_url"])
    if settings.get("proto_dir"):
        PROTO_DIR = os.path.expanduser(str(settings["proto_dir"]))
        if PROTO_DIR not in sys.path:
            sys.path.insert(0, PROTO_DIR)


def read_apikey() -> str:
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
