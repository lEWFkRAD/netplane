# NetPlane — self-hosted Tailscale control plane for Hermes

NetPlane installs, configures and manages a self-hosted
[Headscale](https://headscale.net) control plane from Hermes. Start with a
setup plan, approve the installation, then manage control-plane health,
nodes and preauth join keys from the agent or Desktop pane.

**What it replaces:** only Tailscale's *cloud control plane* (node registry,
IP allocation, ACLs, key expiry, MagicDNS). Every device still runs the
official Tailscale client — the WireGuard mesh, DERP relays, and NAT
traversal are unchanged. Management calls go to your configured Headscale
over gRPC. New installations use Headscale's embedded DERP relay instead of
Tailscale's public relay map.

## What it registers

- Tools: `netplane_setup`, `netplane_status`, `netplane_nodes`, `netplane_preauth`
- Desktop: a `/netplane` dashboard page (nodes, online dots, preauth keys)
  with a sidebar nav row and a command-palette entry
- Backend API: `/api/plugins/netplane/*` (FastAPI, for the Desktop pane)

## Compatibility

Requires Hermes **>= 0.21.6** for profile-aware credential storage and plugin
settings writes. Management can connect to an existing server. Automatic
installation supports a fresh **Debian 12+ or Ubuntu 22.04+** system with
systemd, **amd64 or arm64**, on the same host as Hermes.

## Install and configure a new control plane

Install and enable the plugin:

```bash
hermes plugins install lEWFkRAD/netplane
hermes plugins enable netplane
```

Installing or loading the plugin does not change the host automatically.
Open **NetPlane → Install and configure Headscale**, or ask the agent to
call `netplane_setup` with:

```json
{
  "action": "plan",
  "server_url": "https://headscale.example.com",
  "tls_mode": "letsencrypt",
  "acme_email": "operator@example.com",
  "base_domain": "tailnet.internal",
  "headscale_user": "hermes"
}
```

Replace the example domain/email with yours. Point the domain's DNS at the
host and allow inbound **TCP 80/443** and **UDP 3478**. Setup does not modify
DNS records, firewall rules, routers, or existing Tailscale membership.
Review the generated configuration and repeat the call with
`"action": "install"`. Agent installation goes through Hermes's approval
hook; Desktop requires confirmation of the displayed plan.

The approved setup:

1. Downloads the official Headscale **v0.29.6** DEB and verifies its SHA-256
   against the checksum pinned in this repository.
2. Installs the package, service account and systemd unit. It masks the new
   service during package installation, writes `/etc/headscale/config.yaml`,
   and runs `headscale configtest` before starting it.
3. Configures SQLite, MagicDNS, automatic HTTPS through Let's Encrypt, and
   an embedded DERP/STUN relay. Admin gRPC and metrics listen on loopback.
4. Enables the service, creates the first Headscale user, and creates a
   **90-day API key**. The key goes directly to the active Hermes profile's
   credential store through Hermes; it is never returned to the chat or UI.
5. Saves NetPlane's connection settings through Hermes's plugin API.

Root privileges are required. Agent/Desktop setup uses `sudo -n`, so it
fails promptly when passwordless elevation is unavailable. It never asks
for a sudo password or changes sudo policy. Existing Headscale packages,
configuration, state, services or custom NetPlane connection settings are
refused; this is not an upgrade or migration tool.

If you already operate an HTTPS reverse proxy, use
`"tls_mode": "reverse_proxy"` and omit `acme_email`. Headscale then listens
on `127.0.0.1:8080`; configure your proxy to forward Headscale's WebSocket/
Upgrade traffic and DERP at your public HTTPS URL. The proxy remains your
responsibility. See the [official proxy requirements](https://headscale.net/stable/ref/integration/reverse-proxy/).

Verify the public HTTPS URL from a device before enrolling it. Installation
checks local service readiness; it does not prove that public DNS, NAT,
firewall rules or certificate issuance work from outside the host. The
initial Headscale policy permits enrolled devices to communicate with one
another. No devices are enrolled automatically.

## Connect an existing Headscale server

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
   - `grpc_tls_server_name` — certificate DNS name when a loopback gRPC
     listener uses TLS (automatic setup fills this for built-in HTTPS).
4. Install and enable the plugin as above. Set the API key through the
   plugin's **API key** secret field in Hermes settings. Management requires
   the key; setup can load before a key exists.

## Interrupted setup and credentials

On installation failure, the helper tries to stop, disable and mask its new
service. It preserves partial files and data for inspection, and refuses to
overwrite them on a retry. Inspect `systemctl status headscale` and
`journalctl -u headscale`, then repair the installation deliberately.

If the server installed successfully but saving the new key failed, setup
attempts to revoke that key and reports the revocation result. Complete
credential setup through Hermes settings after inspecting Headscale's API
keys locally. For manual recovery or renewal, run
`sudo headscale apikeys create --expiration 90d` in your terminal and save the
new value in Hermes's **API key** secret field. Treat it as a credential;
do not paste it into chat. Rotate before its 90-day expiry.

## Disclosure (rule 13)

- **Network:** management connects to the configured Headscale gRPC address
  (default loopback). Plaintext is limited to loopback; remote targets use
  TLS. Local Headscale HTTPS uses verified TLS with its certificate DNS
  name. Setup downloads the pinned package from GitHub and may contact the
  host's configured APT repositories for dependencies. Let's Encrypt mode
  sends the chosen domain and email to Let's Encrypt and obtains a public
  certificate. The installed server opens the listeners listed in the plan.
  No telemetry, public DERP-map downloads, or automatic software updates.
- **Shell commands:** `netplane_status` runs `systemctl is-active headscale`
  and `tailscale serve status` (best-effort; failures are reported in the
  output, not raised).
- **Installation commands and files:** explicit setup invokes a bundled
  Python helper through noninteractive sudo; it runs APT/dpkg, systemctl,
  runuser and the official Headscale CLI. It writes Headscale configuration,
  state, a root-owned installation record, a systemd override and Hermes
  plugin settings. The service runs persistently under its own system user.
- **Writes:** `netplane_preauth(create=true)` requires explicit approval,
  then mints a preauth key on your control plane. Treat the returned key as a
  secret join credential. Keys default to single-use and 24 hours; expiry is
  limited to 1–168 hours. The secret is returned only by the create response;
  subsequent list responses omit it.
- **Bootstrap credential:** explicit setup creates one API key and stores it
  through `hermes_cli.config.save_env_value_secure`; it does not read or
  write credential files itself. Existing profile credentials are preserved.
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

## Scope

Automatic provisioning is for the same Linux host as Hermes. Remote
provisioning, upgrades, existing-server takeover, reverse-proxy installation,
firewall/DNS changes and device migration are not included. Existing servers
can still be managed through their configured gRPC endpoint.

## Testing

Verified on **2026-10-25** in a fresh, isolated **Ubuntu 24.04 systemd VM**:
Hermes `1f91da2a277093c6909542d8c725c0c52fae4628`, NetPlane
`10b6bff5cf5bb521d39e4443d9d33ee6768fbb23`, and Headscale **0.29.6**.
The guest harness passed real Hermes plugin install/enable and tool dispatch,
setup planning and denial/approval, installation in `reverse_proxy` mode,
profile-only API-key storage with owner-only permissions, management RPCs,
denied/approved single-use join-key creation, secret-free listings, key
expiry/deletion, repeat-install refusal, and bootstrap-key revocation.

Separately configured nginx with a disposable test certificate passed local
HTTPS `/health` with certificate verification. After a guest reboot, nginx
and Headscale remained enabled/active and HTTPS health passed again. The
local suite also passed **85 tests** and **16/16 Hermes admission checks**;
the expected admission caution covers network listeners and sudo usage.

The test ran in a disposable KVM guest, with no host-directory mounts or
bridge to the production network. Test join keys and the bootstrap API key
were revoked or deleted, and the VM was shut down after verification. No
production Headscale or tailnet configuration was changed. The 85-test suite
and 16 admission checks were also rerun successfully at
`ca432caaa18cc681c967b1fee915125643ab28f4`, which adds tests, documentation
and attribution without changing the VM-tested runtime.

To reproduce the harness, first install Hermes in the guest and provide a
Git checkout of NetPlane containing `tests/vm_integration.py`. **Run as root
only inside a fresh, disposable systemd VM—not on your development or
production host.** It installs packages and leaves a persistent Headscale
service; successful runs revoke test credentials and remove the temporary
Hermes profile. Dispose of the VM afterward, especially after a failure.

```bash
/usr/bin/python3 /opt/netplane-test/tests/vm_integration.py \
  --allow-disposable-vm \
  --hermes-root /opt/hermes-agent \
  --plugin-source /opt/netplane-test \
  --ref 10b6bff5cf5bb521d39e4443d9d33ee6768fbb23
```

The harness does not configure nginx or a public endpoint. Public DNS/ACME,
real Tailscale node enrollment, peer traffic, and interactive Desktop UI
behavior have **not** been verified by these tests. The guest runs setup as root; the
noninteractive sudo path is covered by unit tests, not this VM run.

## Credits and acknowledgments

- **Jeff Watts ([lEWFkRAD](https://github.com/lEWFkRAD))** — project owner
  and maintainer.
- **Qwen 3.8** — original plugin implementation, directed by Jeff.
- **Tek ([teknium1](https://github.com/teknium1))** — security and Hermes
  integration review in [the catalog submission](https://github.com/NousResearch/hermes-agent/pull/144260).
- **OpenAI Codex** — follow-up code audit, security hardening, setup
  implementation and testing, directed by Jeff.
- **Nous Research and Hermes contributors** — the agent, plugin framework
  and Desktop integration this plugin builds on.
- **Headscale and Tailscale contributors** — the control-plane software,
  API definitions and client/networking ecosystem. The bundled Headscale
  protocol definitions come from the pinned upstream revision documented
  in `scripts/gen_proto.sh`.
- **Google APIs, gRPC and Protocol Buffers contributors** — API annotations,
  binding generation and runtime libraries. Bundled Google API source files
  retain their upstream copyright and Apache 2.0 notices.

These acknowledgments describe contributions and dependencies; they do not
imply endorsement or affiliation. Existing Git authorship and upstream
notices are preserved. Vendored-source provenance and license copies are in
[LICENSES](LICENSES/README.md); these do not license NetPlane's original code.
