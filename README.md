# NetPlane — self-hosted Tailscale control plane for Hermes

NetPlane wraps a self-hosted [Headscale](https://headscale.net) control plane
so Hermes can see and manage your own tailnet: control-plane health, node
inventory with live online state, and preauth join-keys — plus a Desktop
dashboard pane.

**What it replaces:** only Tailscale's *cloud control plane* (node registry,
IP allocation, ACLs, key expiry, MagicDNS). Every device still runs the
official Tailscale client — the WireGuard mesh, DERP relays, and NAT
traversal are unchanged. Nothing in this plugin talks to Tailscale Inc.;
all calls go to your own Headscale over local gRPC.

## What it registers

- Tools: `netplane_status`, `netplane_nodes`, `netplane_preauth`
- Desktop: a `/netplane` dashboard page (nodes, online dots, preauth keys)
  with a sidebar nav row and a command-palette entry
- Backend API: `/api/plugins/netplane/*` (FastAPI, for the Desktop pane)

## Setup

1. **Headscale** running locally with gRPC enabled
   (`grpc_listen_addr: 127.0.0.1:50443`, `grpc_allow_insecure: true` for a
   loopback-only setup).
2. **API key**: create one (`headscale apikeys create`) and put it in
   `api.key` next to `hsclient.py`, or point `NETPLANE_APIKEY_FILE` at it.
   The file is read at call time; keep it mode 600.
3. **Env** (all optional, sensible defaults):
   - `NETPLANE_GRPC_ADDR` — default `127.0.0.1:50443`
   - `NETPLANE_APIKEY_FILE` — default `api.key` in the plugin dir
   - `NETPLANE_CONTROL_URL` — the URL shown in status output
   - `NETPLANE_PROTO_DIR` — default `proto/` in the plugin dir
4. Install and enable:
   ```bash
   hermes plugins install <owner>/netplane
   hermes plugins enable netplane
   ```

## Disclosure (rule 13)

- **Network:** connects only to the configured Headscale gRPC address
  (default loopback). No third-party services, no telemetry.
- **Shell commands:** `netplane_status` runs `systemctl is-active headscale`
  and `tailscale serve status` (best-effort; failures are reported in the
  output, not raised).
- **Writes:** `netplane_preauth(create=true)` mints a preauth key on your
  control plane — treat the returned key as a secret join credential.
- **Credentials:** the Headscale API key is read from the file named by
  `NETPLANE_APIKEY_FILE`; the plugin never sends it anywhere except the
  configured gRPC endpoint.
- **Desktop backend deps:** the Desktop pane's Python backend needs
  `grpcio` + `protobuf` in the Desktop serve venv; the installer resolves
  `python_dependencies` declared in `plugin.yaml`.

## Protobuf stubs

The gRPC stubs under `proto/` are generated from Headscale v0.29.6 protos.
If your Python env's `protobuf` runtime disagrees with the stub gencode
version, regenerate with `scripts/gen_proto.sh` (needs `grpcio-tools`) or
patch `ValidateProtobufRuntimeVersion` in the generated files down to the
runtime's version.

## Not included

NetPlane does not install or configure Headscale itself, and it does not
migrate devices between tailnets — it manages a control plane you already
run.
