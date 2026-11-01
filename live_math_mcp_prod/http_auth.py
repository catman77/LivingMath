"""Single-owner OAuth state; protocol validation and PKCE use the MCP SDK."""
from collections import deque
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    OAuthAuthorizationServerProvider, RefreshToken, RegistrationError, TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


def chatgpt_callback(uri: str) -> bool:
    parsed = urlparse(uri)
    return (parsed.scheme == 'https' and parsed.netloc == 'chatgpt.com'
            and not parsed.query and not parsed.fragment
            and (parsed.path == '/connector_platform_oauth_redirect'
                 or re.fullmatch(r'/connector/oauth/[A-Za-z0-9_-]+', parsed.path) is not None))


class OwnerOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, path: Path, public_url: str, password: str):
        self.path = Path(path)
        self.public_url = public_url
        self.resource = public_url + '/mcp'
        if len(password) < 20:
            raise ValueError('The owner password must contain at least 20 characters.')
        self.password_digest = hashlib.sha256(password.encode()).digest()
        self.failures = deque(maxlen=10)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS auth_records(
                key TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL,
                expires REAL NOT NULL, family TEXT)''')
        self.path.chmod(0o600)

    @staticmethod
    def _key(kind: str, secret: str) -> str:
        return kind + ':' + hashlib.sha256(secret.encode()).hexdigest()

    def _save(self, kind, secret, body, expires, family=None):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DELETE FROM auth_records WHERE expires <= ?', (time.time(),))
            connection.execute('INSERT INTO auth_records VALUES (?,?,?,?,?)',
                               (self._key(kind, secret), kind, json.dumps(body), expires, family))

    def _read(self, kind, secret):
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute('SELECT body, family FROM auth_records WHERE key=? AND expires>?',
                                     (self._key(kind, secret), time.time())).fetchone()
        return (json.loads(row[0]), row[1]) if row else None

    def _consume(self, kind, secret, client_id=None):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT body, family FROM auth_records WHERE key=? AND expires>?',
                                     (self._key(kind, secret), time.time())).fetchone()
            if row is None:
                return None
            body = json.loads(row[0])
            if client_id is not None and body.get('client_id') != client_id:
                return None
            connection.execute('DELETE FROM auth_records WHERE key=?', (self._key(kind, secret),))
            return body, row[1]

    async def get_client(self, client_id):
        row = self._read('client', client_id)
        return OAuthClientInformationFull.model_validate(row[0]) if row else None

    async def register_client(self, client_info):
        if not client_info.redirect_uris or not all(chatgpt_callback(str(uri)) for uri in client_info.redirect_uris):
            raise RegistrationError('invalid_redirect_uri', 'Only ChatGPT HTTPS callbacks are allowed.')
        body = client_info.model_dump(mode='json')
        if len(json.dumps(body)) > 8192:
            raise RegistrationError('invalid_client_metadata', 'Client metadata is too large.')
        with closing(sqlite3.connect(self.path)) as connection:
            count = connection.execute('SELECT count(*) FROM auth_records WHERE kind=? AND expires>?',
                                       ('client', time.time())).fetchone()[0]
        if count >= 32:
            raise RegistrationError('invalid_client_metadata', 'Client registration limit reached.')
        self._save('client', client_info.client_id, body, time.time() + 90 * 86400)

    async def authorize(self, client, params: AuthorizationParams):
        if params.resource != self.resource:
            raise AuthorizeError('invalid_request', 'The resource must match this MCP endpoint.')
        if set(params.scopes or ['research']) != {'research'}:
            raise AuthorizeError('invalid_scope', 'Only the research scope is supported.')
        request_id = secrets.token_urlsafe(32)
        self._save('pending', request_id, {
            'client_id': client.client_id, 'params': params.model_dump(mode='json'),
            'csrf': secrets.token_urlsafe(32),
        }, time.time() + 600)
        return self.public_url + '/login?' + urlencode({'request': request_id})

    def login_request(self, request_id):
        row = self._read('pending', request_id)
        return row[0] if row else None

    def approve(self, request_id, password, csrf):
        pending = self.login_request(request_id)
        if pending is None or not hmac.compare_digest(pending['csrf'], csrf):
            raise ValueError('Expired or invalid authorization request.')
        now = time.time()
        if len(self.failures) == 10 and self.failures[0] > now - 60:
            raise PermissionError('Too many attempts. Wait one minute.')
        if not hmac.compare_digest(hashlib.sha256(password.encode()).digest(), self.password_digest):
            self.failures.append(now)
            raise PermissionError('Incorrect password.')
        consumed = self._consume('pending', request_id)
        if consumed is None:
            raise ValueError('Authorization request already used.')
        params = AuthorizationParams.model_validate(consumed[0]['params'])
        code = secrets.token_urlsafe(32)
        authorization = AuthorizationCode(
            code=code, client_id=pending['client_id'], scopes=params.scopes or ['research'],
            expires_at=now + 120, code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self.resource, subject='owner',
        )
        self._save('code', code, authorization.model_dump(mode='json', exclude={'code'}), now + 120)
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client, authorization_code):
        row = self._read('code', authorization_code)
        if row is None or row[0]['client_id'] != client.client_id or row[0]['resource'] != self.resource:
            return None
        return AuthorizationCode(code=authorization_code, **row[0])

    def _issue(self, client_id, scopes, family=None):
        now = int(time.time())
        family = family or secrets.token_hex(16)
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(48)
        common = {'client_id': client_id, 'scopes': scopes, 'resource': self.resource, 'subject': 'owner'}
        self._save('access', access, {**common, 'expires_at': now + 3600}, now + 3600, family)
        self._save('refresh', refresh, {**common, 'expires_at': now + 30 * 86400}, now + 30 * 86400, family)
        return OAuthToken(access_token=access, token_type='Bearer', expires_in=3600,
                          refresh_token=refresh, scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        row = self._consume('code', authorization_code.code, client.client_id)
        if row is None or row[0]['resource'] != self.resource:
            raise TokenError('invalid_grant', 'Authorization code is expired or already used.')
        return self._issue(client.client_id, row[0]['scopes'])

    async def load_refresh_token(self, client, refresh_token):
        row = self._read('refresh', refresh_token)
        if row is None or row[0]['client_id'] != client.client_id or row[0]['resource'] != self.resource:
            return None
        return RefreshToken(token=refresh_token, **row[0])

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if not set(scopes).issubset(refresh_token.scopes):
            raise TokenError('invalid_scope', 'Refresh cannot expand the original scopes.')
        row = self._consume('refresh', refresh_token.token, client.client_id)
        if row is None or row[0]['resource'] != self.resource:
            raise TokenError('invalid_grant', 'Refresh token is expired or already used.')
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DELETE FROM auth_records WHERE family=?', (row[1],))
        return self._issue(client.client_id, scopes, row[1])

    async def load_access_token(self, token):
        row = self._read('access', token)
        if row is None or row[0]['resource'] != self.resource:
            return None
        return AccessToken(token=token, **row[0])

    async def revoke_token(self, token):
        kind = 'refresh' if isinstance(token, RefreshToken) else 'access'
        row = self._read(kind, token.token)
        if row:
            with closing(sqlite3.connect(self.path)) as connection, connection:
                connection.execute('DELETE FROM auth_records WHERE family=?', (row[1],))
