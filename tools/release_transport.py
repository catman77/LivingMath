"""Explicit transport authentication policy for the pinned MCP SDK."""


def configure_authentication(server, mode: str) -> None:
    if mode not in ('oauth', 'none'):
        raise ValueError('INVALID_TRANSPORT_AUTHENTICATION')
    if mode == 'oauth':
        return
    # The accepted legacy factory creates FastMCP before the release mounts its
    # tools. Disable SDK authentication before it builds the ASGI application.
    server.settings.auth = None
    server._auth_server_provider = None
    server._token_verifier = None
    original = server.streamable_http_app

    def public_app(*args, **kwargs):
        app = original(*args, **kwargs)
        # Login is a legacy custom route, separate from SDK OAuth discovery.
        app.router.routes[:] = [r for r in app.routes if getattr(r, 'path', None) != '/login']
        return app

    server.streamable_http_app = public_app
