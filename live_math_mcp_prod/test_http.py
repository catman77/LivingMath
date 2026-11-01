import base64
import hashlib
import json
import secrets
import time
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from http_server import create_app


PUBLIC_URL = 'https://livingmath.example'
CALLBACK = 'https://chatgpt.com/connector/oauth/test-connection'
PASSWORD = 'a-long-local-test-password'


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(PUBLIC_URL, tmp_path, PASSWORD), base_url=PUBLIC_URL) as session:
        yield session


def register(client, callback=CALLBACK):
    response = client.post('/register', json={
        'client_name': 'ChatGPT',
        'redirect_uris': [callback],
        'grant_types': ['authorization_code', 'refresh_token'],
        'response_types': ['code'],
        'token_endpoint_auth_method': 'client_secret_post',
        'scope': 'research',
    })
    assert response.status_code == 201, response.text
    return response.json()


def authorize(client, registration, resource=PUBLIC_URL + '/mcp'):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    response = client.get('/authorize', params={
        'client_id': registration['client_id'],
        'redirect_uri': CALLBACK,
        'response_type': 'code',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'scope': 'research',
        'state': 'preserve-this-state',
        'resource': resource,
    }, follow_redirects=False)
    return response, verifier


def approve(client, registration):
    response, verifier = authorize(client, registration)
    assert response.status_code in (302, 303, 307), response.text
    login_url = response.headers['location']
    assert urlparse(login_url).path == '/login'
    page = client.get(login_url)
    assert page.status_code == 200
    assert PASSWORD not in page.text
    # HTML form navigations send Origin: null under no-referrer (Fetch spec).
    form_origin = 'null' if page.headers.get('referrer-policy') == 'no-referrer' else PUBLIC_URL
    request_id = parse_qs(urlparse(login_url).query)['request'][0]
    response = client.post('/login', data={'request': request_id, 'password': PASSWORD},
                           headers={'Origin': form_origin}, follow_redirects=False)
    assert response.status_code == 303, response.text
    query = parse_qs(urlparse(response.headers['location']).query)
    assert query['state'] == ['preserve-this-state']
    return query['code'][0], verifier


def exchange(client, registration, code, verifier, resource=PUBLIC_URL + '/mcp'):
    return client.post('/token', data={
        'grant_type': 'authorization_code',
        'client_id': registration['client_id'],
        'client_secret': registration['client_secret'],
        'code': code,
        'code_verifier': verifier,
        'redirect_uri': CALLBACK,
        'resource': resource,
    })


def test_discovery_and_anonymous_access(client):
    response = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    assert response.status_code == 401
    assert 'oauth-protected-resource/mcp' in response.headers['www-authenticate']
    resource = client.get('/.well-known/oauth-protected-resource/mcp').json()
    assert resource['resource'] == PUBLIC_URL + '/mcp'
    metadata = client.get('/.well-known/oauth-authorization-server').json()
    assert metadata['code_challenge_methods_supported'] == ['S256']
    assert metadata['registration_endpoint'] == PUBLIC_URL + '/register'


@pytest.mark.parametrize('callback', [
    'https://attacker.example/callback',
    'http://chatgpt.com/connector/oauth/test',
    'https://chatgpt.com.attacker.example/connector/oauth/test',
    'https://attacker@chatgpt.com/connector/oauth/test',
    'https://chatgpt.com/unrelated',
])
def test_registration_rejects_untrusted_redirects(client, callback):
    response = client.post('/register', json={
        'redirect_uris': [callback],
        'grant_types': ['authorization_code', 'refresh_token'],
    })
    assert response.status_code == 400


def test_login_rejects_password_and_cross_origin_requests(client):
    registration = register(client)
    response, _ = authorize(client, registration)
    login_url = response.headers['location']
    client.get(login_url)
    request_id = parse_qs(urlparse(login_url).query)['request'][0]
    response = client.post('/login', data={'request': request_id, 'password': 'wrong'},
                           headers={'Origin': PUBLIC_URL})
    assert response.status_code == 401
    response = client.post('/login', data={'request': request_id, 'password': PASSWORD},
                           headers={'Origin': 'https://attacker.example'})
    assert response.status_code == 403


@pytest.mark.parametrize('origin', [None, 'null', 'https://chatgpt.com', 'https://attacker.example'])
def test_login_rejects_missing_opaque_or_foreign_origins_even_with_cookie(client, origin):
    registration = register(client)
    response, _ = authorize(client, registration)
    login_url = response.headers['location']
    client.get(login_url)
    request_id = parse_qs(urlparse(login_url).query)['request'][0]
    headers = {} if origin is None else {'Origin': origin}
    response = client.post('/login', data={'request': request_id, 'password': PASSWORD},
                           headers=headers, follow_redirects=False)
    assert response.status_code == 403


def test_oauth_pkce_resource_replay_and_authenticated_mcp(client):
    registration = register(client)
    response, _ = authorize(client, registration, 'https://attacker.example/mcp')
    assert response.status_code == 400 or 'error=' in response.headers.get('location', '')
    code, verifier = approve(client, registration)
    assert exchange(client, registration, code, 'wrong-verifier').status_code == 400
    assert exchange(client, registration, code, verifier, 'https://attacker.example/mcp').status_code == 400
    response = exchange(client, registration, code, verifier)
    assert response.status_code == 200, response.text
    assert exchange(client, registration, code, verifier).status_code == 400
    token = response.json()['access_token']
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream',
               'MCP-Protocol-Version': '2025-11-25'}
    initialized = client.post('/mcp', headers=headers, json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-11-25', 'capabilities': {},
                   'clientInfo': {'name': 'integration-test', 'version': '1'}},
    })
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()['result']['serverInfo']['version'] == '0.4.2'
    response = client.post('/mcp', headers=headers, json={
        'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list',
    })
    assert response.status_code == 200, response.text
    assert len(response.json()['result']['tools']) == 18
    response = client.post('/mcp', headers=headers, json={
        'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
        'params': {'name': 'service_health', 'arguments': {}},
    })
    result = response.json()['result']
    assert not result.get('isError'), result
    health = result.get('structuredContent') or json.loads(result['content'][0]['text'])
    assert health['version'] == '0.4.2'
    assert health['audit']['ok'], result


def test_refresh_rotation_revocation_and_restart(tmp_path):
    with TestClient(create_app(PUBLIC_URL, tmp_path, PASSWORD), base_url=PUBLIC_URL) as client:
        registration = register(client)
        code, verifier = approve(client, registration)
        tokens = exchange(client, registration, code, verifier).json()
    with TestClient(create_app(PUBLIC_URL, tmp_path, PASSWORD), base_url=PUBLIC_URL) as client:
        form = {'grant_type': 'refresh_token', 'client_id': registration['client_id'],
                'client_secret': registration['client_secret'], 'refresh_token': tokens['refresh_token'],
                'resource': PUBLIC_URL + '/mcp'}
        response = client.post('/token', data=form)
        assert response.status_code == 200, response.text
        rotated = response.json()
        assert rotated['refresh_token'] != tokens['refresh_token']
        assert client.post('/token', data=form).status_code == 400
        revoked = client.post('/revoke', data={
            'client_id': registration['client_id'], 'client_secret': registration['client_secret'],
            'token': rotated['refresh_token'],
        })
        assert revoked.status_code == 200
        response = client.post('/mcp', headers={'Authorization': 'Bearer ' + rotated['access_token']},
                               json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert response.status_code == 401
        raw_database = (tmp_path / 'oauth.sqlite3').read_bytes()
        assert rotated['access_token'].encode() not in raw_database
        assert rotated['refresh_token'].encode() not in raw_database


def test_http_requires_https_and_rejects_unknown_hosts(tmp_path, client):
    with pytest.raises(ValueError):
        create_app('http://public.example', tmp_path / 'bad', PASSWORD)
    assert client.get('/healthz', headers={'Host': 'attacker.example'}).status_code == 400


def test_credentials_are_bound_to_the_registered_client(client):
    owner = register(client)
    other = register(client)
    code, verifier = approve(client, owner)
    assert exchange(client, other, code, verifier).status_code == 400
    tokens = exchange(client, owner, code, verifier).json()
    response = client.post('/token', data={
        'grant_type': 'refresh_token', 'client_id': other['client_id'],
        'client_secret': other['client_secret'], 'refresh_token': tokens['refresh_token'],
        'resource': PUBLIC_URL + '/mcp',
    })
    assert response.status_code == 400


def test_login_requires_csrf_cookie_and_request_is_single_use(client):
    registration = register(client)
    response, _ = authorize(client, registration)
    login_url = response.headers['location']
    client.get(login_url)
    request_id = parse_qs(urlparse(login_url).query)['request'][0]
    client.cookies.clear()
    form = {'request': request_id, 'password': PASSWORD}
    assert client.post('/login', data=form, headers={'Origin': PUBLIC_URL}).status_code == 400
    client.get(login_url)
    assert client.post('/login', data=form, headers={'Origin': PUBLIC_URL}, follow_redirects=False).status_code == 303
    assert client.get(login_url).status_code == 400


def test_expired_authorization_codes_and_access_tokens_are_rejected(client, monkeypatch):
    registration = register(client)
    code, verifier = approve(client, registration)
    tokens = exchange(client, registration, code, verifier).json()
    unused_code, unused_verifier = approve(client, registration)
    later = time.time() + 4000
    monkeypatch.setattr('http_auth.time.time', lambda: later)
    assert exchange(client, registration, unused_code, unused_verifier).status_code == 400
    response = client.post('/mcp', headers={'Authorization': 'Bearer ' + tokens['access_token']},
                           json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    assert response.status_code == 401


def test_changed_public_origin_does_not_accept_old_tokens(tmp_path):
    with TestClient(create_app(PUBLIC_URL, tmp_path, PASSWORD), base_url=PUBLIC_URL) as client:
        registration = register(client)
        code, verifier = approve(client, registration)
        tokens = exchange(client, registration, code, verifier).json()
    changed_url = 'https://new-livingmath.example'
    with TestClient(create_app(changed_url, tmp_path, PASSWORD), base_url=changed_url) as client:
        response = client.post('/mcp', headers={'Authorization': 'Bearer ' + tokens['access_token']},
                               json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert response.status_code == 401


def test_authenticated_writes_preserve_project_and_review_boundaries(client):
    registration = register(client)
    code, verifier = approve(client, registration)
    token = exchange(client, registration, code, verifier).json()['access_token']
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream',
               'MCP-Protocol-Version': '2025-11-25'}

    def call(name, arguments):
        response = client.post('/mcp', headers=headers, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments},
        })
        assert response.status_code == 200
        return response.json()['result']

    first = call('attend', {'project': 'HTTP_TEST', 'focus': 'example', 'reason': 'protocol test'})
    assert not first.get('isError')
    parent = json.loads(first['content'][0]['text'])
    child = call('interpret', {'project': 'HTTP_TEST', 'focus': 'example',
                               'claim': 'unverified', 'parent_id': parent['id']})
    assert not child.get('isError')
    assert call('interpret', {'project': 'OTHER', 'focus': 'example',
                              'claim': 'invalid link', 'parent_id': parent['id']})['isError']
    assert call('record_result', {'project': 'HTTP_TEST', 'kind': 'proof', 'focus': 'example',
                                  'result': 'invalid status', 'status': 'verified'})['isError']
    context = call('research_context', {'project': 'HTTP_TEST'})
    events = json.loads(context['content'][0]['text'])['events']
    assert len(events) == 2 and events[1]['status'] == 'hypothesis'


def test_oversized_token_requests_are_rejected(client):
    response = client.post('/token', content=b'x' * 300000,
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert response.status_code == 413


def test_v04_frontier_tools_and_distinct_audits_over_authenticated_http(tmp_path):
    from test_frontier import historical_database, BLUEPRINT
    from regression_v04 import regression_requests
    from research_store import ResearchStore
    historical_database(tmp_path / 'research.sqlite3')
    store = ResearchStore(tmp_path / 'research.sqlite3')
    store.frontier.import_history(BLUEPRINT, 'authenticated regression replay')
    with TestClient(create_app(PUBLIC_URL, tmp_path, PASSWORD), base_url=PUBLIC_URL) as client:
        registration = register(client)
        code, verifier = approve(client, registration)
        token = exchange(client, registration, code, verifier).json()['access_token']
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': '2025-11-25'}

        def call(name, arguments):
            response = client.post('/mcp', headers=headers, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                'params': {'name': name, 'arguments': arguments},
            })
            assert response.status_code == 200
            result = response.json()['result']
            assert not result.get('isError'), result
            return result.get('structuredContent') or json.loads(result['content'][0]['text'])

        frontier = call('research_frontier', {'project': 'RH', 'include_closed': True})
        for label, expected, request in regression_requests(frontier):
            result = call('audit_research_shift', {'project': 'RH', 'proposal': label, **request})
            assert result['classification'] == expected
            assert result['proof_status'] == 'unverified'
        obligation = call('research_obligation_create', {
            'project': 'RH', 'statement': 'A protocol check', 'scope': 'temporary test', 'source_event_ids': [15]})
        updated = call('research_obligation_update', {
            'project': 'RH', 'obligation_id': obligation['id'], 'expected_version': 1,
            'changes': {'status': 'TESTING'}})
        assert updated['version'] == 2
        contract = call('record_transformation_contract', {
            'project': 'RH', 'source': 'original', 'operation': {'mechanism': 'test'}, 'result': 'candidate',
            'source_event_ids': [13], 'preservation': {prop: {'statement': 'Check ' + prop}
                for prop in ('point_value', 'analytic_function', 'observables', 'source_provenance', 'rule_applicability')}})
        assert len(contract['obligation_ids']) == 5
