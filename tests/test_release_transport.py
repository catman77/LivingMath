"""Transport opt-out preserves the same MCP tools and research boundaries."""
import importlib.util
import json
import sys
from pathlib import Path
import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'live_math_mcp_prod'))
import http_server

spec = importlib.util.spec_from_file_location('release_transport_tested', ROOT / 'tools/release_transport.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
ORIGIN = 'https://livingmath.example'
HEADERS = {'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-11-25'}


def app(tmp_path, monkeypatch, mode):
    factory = http_server.create_server
    def create(*args, **kwargs):
        server = factory(*args, **kwargs)
        transport.configure_authentication(server, mode)
        return server
    monkeypatch.setattr(http_server, 'create_server', create)
    return http_server.create_app(ORIGIN, tmp_path, 'unit-only-local-password')


def request(client, method, params=None, **headers):
    return client.post('/mcp', headers={**HEADERS, **headers}, json={
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})


def call(client, name, args):
    response = request(client, 'tools/call', {'name': name, 'arguments': args})
    assert response.status_code == 200, response.text
    return response.json()['result']


def test_anonymous_list_calls_writes_and_unchanged_domain_boundaries(tmp_path, monkeypatch):
    with TestClient(app(tmp_path, monkeypatch, 'none'), base_url=ORIGIN) as c:
        listed = request(c, 'tools/list')
        assert listed.status_code == 200 and 'www-authenticate' not in listed.headers
        assert 'service_health' in {t['name'] for t in listed.json()['result']['tools']}
        assert not call(c, 'service_health', {}).get('isError')
        parent = call(c, 'attend', {'project': 'NOAUTH_QA', 'focus': 'test', 'reason': 'anonymous transport'})
        assert not parent.get('isError')
        ident = json.loads(parent['content'][0]['text'])['id']
        assert call(c, 'interpret', {'project': 'OTHER_QA', 'focus': 'test', 'claim': 'invalid parent', 'parent_id': ident})['isError']
        assert call(c, 'record_result', {'project': 'NOAUTH_QA', 'kind': 'proof', 'focus': 'test', 'result': 'not a proof', 'status': 'verified'})['isError']
        assert request(c, 'tools/list', Authorization='Bearer no-longer-required').status_code == 200
        for path in ['/login', '/authorize', '/token', '/register', '/revoke', '/.well-known/oauth-authorization-server', '/.well-known/oauth-protected-resource/mcp']:
            assert c.get(path).status_code == 404, path


def test_oauth_configuration_still_requires_token(tmp_path, monkeypatch):
    with TestClient(app(tmp_path, monkeypatch, 'oauth'), base_url=ORIGIN) as c:
        assert request(c, 'tools/list').status_code == 401
        assert c.get('/.well-known/oauth-authorization-server').status_code == 200


def test_public_transport_keeps_host_and_origin_checks(tmp_path, monkeypatch):
    with TestClient(app(tmp_path, monkeypatch, 'none'), base_url=ORIGIN) as c:
        assert request(c, 'tools/list', Host='attacker.example').status_code == 400
        assert request(c, 'tools/list', Origin='https://attacker.example').status_code == 403


def test_unknown_mode_fails_closed():
    with pytest.raises(ValueError, match='INVALID_TRANSPORT_AUTHENTICATION'):
        transport.configure_authentication(None, 'disabled-typo')
