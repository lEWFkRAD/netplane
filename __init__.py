"""NetPlane agent plugin: self-hosted Tailscale control plane (Headscale)."""

from . import hsclient, setup_flow, tools


def register(ctx) -> None:
    # Keep the context, not resolved values.  hsclient reads every setting and
    # the active profile's secret at call time.
    hsclient.configure(ctx)
    setup_flow.configure(ctx)
    tools.register(ctx)
