"""NetPlane agent plugin: self-hosted Tailscale control plane (Headscale)."""
from . import hsclient, tools


def _config_with_secret(ctx) -> dict:
    settings = dict(ctx.get_config() or {})
    if not settings.get("apikey"):
        try:
            from agent.secret_scope import get_secret
            settings["apikey"] = get_secret("NETPLANE_APIKEY", "") or ""
        except Exception:  # noqa: BLE001 — no scope installed; file fallback stands
            pass
    return settings


def register(ctx) -> None:
    try:
        hsclient.apply_settings(_config_with_secret(ctx))
    except Exception:  # noqa: BLE001 — settings are optional; defaults stand
        pass
    tools.register(ctx)
