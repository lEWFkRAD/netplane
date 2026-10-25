"""NetPlane agent plugin: self-hosted Tailscale control plane (Headscale)."""

from . import hsclient, tools


def register(ctx) -> None:
    # Keep the context, not resolved values.  hsclient reads every setting and
    # the active profile's secret at call time.
    hsclient.configure(ctx)
    tools.register(ctx)
