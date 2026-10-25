"""NetPlane agent plugin: self-hosted Tailscale control plane (Headscale)."""
from . import hsclient, tools


def register(ctx) -> None:
    try:
        hsclient.apply_settings(ctx.get_config() or {})
    except Exception:  # noqa: BLE001 — settings are optional; env defaults stand
        pass
    tools.register(ctx)
