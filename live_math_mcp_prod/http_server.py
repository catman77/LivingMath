"""Loopback Streamable HTTP with owner-approved OAuth; no OpenAI API calls."""
import html
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import RequestBodyLimitMiddleware, TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn

from http_auth import OwnerOAuthProvider
from mcp_server import create_server
from research_store import ResearchStore


def create_app(public_url: str, data_dir: Path, password: str):
    public_url = public_url.rstrip('/')
    parsed = urlparse(public_url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError('LIVE_MATH_PUBLIC_URL must be an HTTPS origin, without a path or credentials.')
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    data_dir.chmod(0o700)
    provider = OwnerOAuthProvider(data_dir / 'oauth.sqlite3', public_url, password)
    store = ResearchStore(data_dir / 'research.sqlite3')
    store.path.chmod(0o600)
    mcp = create_server(
        store, auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(public_url), resource_server_url=AnyHttpUrl(public_url + '/mcp'),
            validate_token_resource=True, required_scopes=['research'],
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=['research'], default_scopes=['research']),
            revocation_options=RevocationOptions(enabled=True),
        ),
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[parsed.netloc, '127.0.0.1:*', 'localhost:*'],
            allowed_origins=[public_url, 'https://chatgpt.com'],
        ),
    )

    @mcp.custom_route('/healthz', methods=['GET'])
    async def health(request):
        return JSONResponse({'status': 'ok'})

    @mcp.custom_route('/login', methods=['GET', 'POST'])
    async def login(request):
        if request.method == 'GET':
            request_id = request.query_params.get('request', '')
            pending = provider.login_request(request_id)
            if pending is None:
                return HTMLResponse('Authorization request expired. Reconnect from ChatGPT.', status_code=400)
            body = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect LivingMath</title><body>
<h1>Connect LivingMath to ChatGPT</h1>
<p>Allow this ChatGPT connection to read and write your research ledger.</p>
<p>Operator policy approval and independent reviews remain local-only.</p>
<form method="post" action="/login">
<input type="hidden" name="request" value="{html.escape(request_id, quote=True)}">
<label>LivingMath password <input type="password" name="password"
autocomplete="current-password" required autofocus></label>
<button type="submit">Authorize ChatGPT</button></form></body></html>'''
            response = HTMLResponse(body)
            response.set_cookie('livingmath_csrf', pending['csrf'], secure=True,
                                httponly=True, samesite='lax', max_age=600, path='/login')
            return response
        if request.headers.get('origin') != public_url:
            return HTMLResponse('Invalid request origin.', status_code=403)
        form = await request.form(max_fields=3, max_files=0, max_part_size=8192)
        try:
            redirect = provider.approve(str(form.get('request', '')), str(form.get('password', '')),
                                        request.cookies.get('livingmath_csrf', ''))
        except ValueError:
            return HTMLResponse('Invalid or expired authorization request.', status_code=400)
        except PermissionError:
            return HTMLResponse('Incorrect password or too many attempts. Retry from ChatGPT.', status_code=401)
        response = RedirectResponse(redirect, status_code=303)
        response.delete_cookie('livingmath_csrf', path='/login', secure=True, httponly=True, samesite='lax')
        return response

    app = mcp.streamable_http_app()
    async def protect_requests(request, call_next):
        if request.url.path == '/token' and request.method == 'POST':
            body = await request.body()
            if len(body) > 16384:
                return JSONResponse({'error': 'invalid_request'}, status_code=413)
            resource = parse_qs(body.decode('utf-8', errors='replace')).get('resource', [])
            if resource and resource != [public_url + '/mcp']:
                return JSONResponse({'error': 'invalid_target'}, status_code=400)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        # no-referrer makes HTML form navigations send Origin: null. Keep the
        # real HTTPS origin while omitting login paths and query parameters.
        response.headers['Referrer-Policy'] = 'strict-origin'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; form-action 'self'; frame-ancestors 'none'"
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=protect_requests)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[parsed.hostname, '127.0.0.1', 'localhost'])
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=256 * 1024)
    return app


if __name__ == '__main__':
    os.umask(0o077)
    public_url = os.environ['LIVE_MATH_PUBLIC_URL']
    data_dir = Path(os.environ.get('LIVE_MATH_DATA_DIR', '~/.local/share/livingmath')).expanduser()
    password_file = Path(os.environ.get('LIVE_MATH_PASSWORD_FILE', '~/.config/livingmath/login-password')).expanduser()
    app = create_app(public_url, data_dir, password_file.read_text().strip())
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('LIVE_MATH_PORT', '18765')),
                access_log=False, proxy_headers=False)
