#!/usr/bin/env bash
# Regenerate the checked-in Headscale v1 gRPC stubs reproducibly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/proto"
HEADSCALE_VERSION="v0.29.6"
HEADSCALE_REF="a2b1d7863926834e94479dcdd91ab344a9356bd0"
GOOGLEAPIS_REF="dff1cd0c7ff8c26ff4c9f7a87cbe175fb5124d4e"
EXPECTED_GRPCIO_TOOLS="1.81.1"
EXPECTED_PROTOBUF="6.33.5"

HEADSCALE_PROTOS=(
  "headscale/v1/apikey.proto:21661d5f22361dacf543d3a9ecc17abae69d0b2c63b28717a8a041d43f77ae08"
  "headscale/v1/auth.proto:66a9346e948b6e292079ef0a0dad68f61b54e4c2c8dce5d737eb9ffab90c2b4a"
  "headscale/v1/device.proto:9415060e9677f7229ba85c3dd85a38ceaa3f1c1af6ebff5bd7e105d99c549238"
  "headscale/v1/headscale.proto:5778c50ed2957be5ef7530abd05873bed7f50df4cadada69aa8bf3b16d9d4e1a"
  "headscale/v1/node.proto:9f6ef1e4d0afceea4ca3ae42961be1d782961b06c472dfe808a6aee1f5eae9a3"
  "headscale/v1/policy.proto:507a69b517d9392febe6d79536dff09c85dadf64fde5d28345bad887063a0278"
  "headscale/v1/preauthkey.proto:ea502df05fcb61af218b7209f7f3d386ea4caec012fe6ea2497750b2380c7e5e"
  "headscale/v1/user.proto:5a4d7b39dd0c2f6768fd8434803c1ccef04c3f8b3a5d5f589e64c4aaf354231b"
)
GOOGLE_API_PROTOS=(
  "google/api/annotations.proto:e79ea741cb605a65e78ca322174764a4af9fde1962c1631e12b84c4934ba9a6c"
  "google/api/http.proto:ead99129aa15dd5f6233942030c72eec33bc0d7b1c7c260dc143293ef66c5b78"
)

versions="$(python3 -c 'from importlib.metadata import version; print(version("grpcio-tools"), version("protobuf"))')" || {
  echo "grpcio-tools and protobuf are required to regenerate stubs" >&2
  exit 1
}
read -r grpcio_tools_version protobuf_version <<<"$versions"
if [[ "$grpcio_tools_version" != "$EXPECTED_GRPCIO_TOOLS" || "$protobuf_version" != "$EXPECTED_PROTOBUF" ]]; then
  echo "expected grpcio-tools==$EXPECTED_GRPCIO_TOOLS and protobuf==$EXPECTED_PROTOBUF; found grpcio-tools==$grpcio_tools_version and protobuf==$protobuf_version" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PROTO_INPUTS=()

fetch_proto() {
  local base_url="$1"
  local spec="$2"
  local path="${spec%%:*}"
  local expected_sha="${spec##*:}"
  local destination="$TMP/$path"
  mkdir -p "$(dirname "$destination")"
  curl -fsSL "$base_url/$path" -o "$destination"
  if ! printf '%s  %s\n' "$expected_sha" "$destination" | sha256sum --check --status; then
    echo "checksum mismatch for $path" >&2
    exit 1
  fi
  PROTO_INPUTS+=("$destination")
}

headscale_base="https://raw.githubusercontent.com/juanfont/headscale/$HEADSCALE_REF/proto"
for spec in "${HEADSCALE_PROTOS[@]}"; do
  fetch_proto "$headscale_base" "$spec"
done

googleapis_base="https://raw.githubusercontent.com/googleapis/googleapis/$GOOGLEAPIS_REF"
for spec in "${GOOGLE_API_PROTOS[@]}"; do
  fetch_proto "$googleapis_base" "$spec"
done

grpc_include="$(python3 -c 'from pathlib import Path; import grpc_tools; print(Path(grpc_tools.__file__).resolve().parent / "_proto")')"
mkdir -p "$OUT"
python3 -m grpc_tools.protoc \
  -I"$TMP" \
  -I"$grpc_include" \
  --python_out="$OUT" \
  --pyi_out="$OUT" \
  --grpc_python_out="$OUT" \
  "${PROTO_INPUTS[@]}"

for source in "${PROTO_INPUTS[@]}"; do
  relative="${source#"$TMP/"}"
  install -Dm0644 "$source" "$OUT/$relative"
done

echo "stubs regenerated into $OUT (Headscale $HEADSCALE_VERSION)"
