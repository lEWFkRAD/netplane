#!/usr/bin/env bash
# Regenerate the Headscale v1 gRPC stubs bundled in this plugin.
# Run with the SAME protobuf runtime version the target Python env has,
# or patch ValidateProtobufRuntimeVersion in the generated *_pb2.py files
# down to that runtime's version afterwards.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HS_VERSION="${HS_VERSION:-0.29.6}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for f in headscale/v1/headscale.proto headscale/v1/node.proto headscale/v1/preauthkey.proto headscale/v1/user.proto; do
  mkdir -p "$TMP/$(dirname $f)"
  curl -fsSL "https://raw.githubusercontent.com/tailscale/headscale/v${HS_VERSION}/proto/$f" -o "$TMP/$f"
done
python3 -m grpc_tools.protoc -I"$TMP" --python_out="$HERE/proto" --grpc_python_out="$HERE/proto" \
  "$TMP"/headscale/v1/*.proto
echo "stubs regenerated into $HERE/proto (headscale v${HS_VERSION})"
