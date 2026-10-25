# NetPlane — self-hosted Tailscale control plane for Hermes

NetPlane wraps a self-hosted [Headscale](https://headscale.net) control plane
so Hermes can see and manage your own tailnet: control-plane health, node
inventory with live online state, and preauth join-keys — plus a Desktop
dashboard pane.

**What it replaces:** only Tailscale's *cloud control plane* (node registry,
IP allocation, ACLs, key expiry, MagicDNS). Every device still runs the
official Tailscale client — the WireGuard mesh, DERP relays, and NAT
traversal are unchanged. Nothing in this plugin talks to Tailscale Inc.;
all calls go to your configured Headscale over gRPC.

## What it registers

- Tools: `netplane_status`, `netplane_nodes`, `netplane_preauth`
- Desktop: a `/netplane` dashboard page (nodes, online dots, preauth keys)
  with a sidebar nav row and a command-palette entry
- Backend API: `/api/plugins/netplane/*` (FastAPI, for the Desktop pane)

## Compatibility

Requires Hermes **>= 0.19** (plugin `config_schema`, secret-scope reads, and
the Desktop plugin SDK surfaces this plugin uses).

## Setup

1. **Headscale** reachable with gRPC enabled
   (`grpc_listen_addr: 127.0.0.1:50443`, `grpc_allow_insecure: true` for a
   loopback-only setup).
2. **API key**: create one (`headscale apikeys create`) and save it as the
   Hermes secret `NETPLANE_APIKEY`. NetPlane reads it from the active
   profile's secret scope for each call; it does not read credentials from
   process environment or files itself.
3. **Settings** (all optional, with sensible defaults):
   - `grpc_addr` — default `127.0.0.1:50443`
   - `control_url` — the URL shown in status output
4. Install and enable:
   ```bash
   hermes plugins install <owner>/netplane
   hermes plugins enable netplane
   ```

## Disclosure (rule 13)

- **Network:** connects only to the configured Headscale gRPC address
  (default loopback). Loopback may use plaintext gRPC; non-loopback targets
  use a TLS channel. No third-party services, no telemetry.
- **Shell commands:** `netplane_status` runs `systemctl is-active headscale`
  and `tailscale serve status` (best-effort; failures are reported in the
  output, not raised).
- **Writes:** `netplane_preauth(create=true)` requires explicit approval,
  then mints a preauth key on your control plane. Treat the returned key as a
  secret join credential. Keys default to single-use and 24 hours; expiry is
  limited to 1–168 hours. The secret is returned only by the create response;
  subsequent list responses omit it.
- **Credentials:** the Headscale API key comes only from the active Hermes
  secret scope (`NETPLANE_APIKEY`) and is read when a call runs. The plugin
  never sends it anywhere except the configured gRPC endpoint.
- **Desktop backend deps:** the Desktop pane's Python backend needs
  `grpcio` + `protobuf` in the Desktop serve venv; the installer resolves
  `python_dependencies` declared in `plugin.yaml`.

## Protobuf stubs

The gRPC stubs under `proto/` are generated from Headscale v0.29.6 protos.
If your Python env's `protobuf` runtime disagrees with the stub gencode
version, upgrade the runtime to the floors declared in `plugin.yaml` or
regenerate with `scripts/gen_proto.sh`. Regeneration requires
`grpcio-tools==1.81.1` and `protobuf==6.33.5`; the script downloads immutable
Headscale and Google API proto revisions from GitHub and verifies every source
file's SHA-256 checksum before compiling it.

## Not included

NetPlane does not install or configure Headscale itself, and it does not
migrate devices between tailnets — it manages a control plane you already
run.
