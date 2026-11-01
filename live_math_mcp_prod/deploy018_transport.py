"""Private TLS/OAuth acceptance transport, never imported by the server."""
import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from normalization_regression import Tap
from native_preview008_server import MeasuredProcess

SOURCE = Path(__file__).resolve().parent


def tls(directory: Path):
    directory.mkdir(mode=0o700, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'LivingMath018 private staging')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        .sign(key, hashes.SHA256()))
    cert, secret, password = directory / 'ca.pem', directory / 'tls-key.pem', directory / 'owner-password'
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    secret.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    password.write_text(secrets.token_urlsafe(32))
    for p in (cert, secret, password):
        p.chmod(0o600)
    return cert, secret, password


def oauth(origin: str, context: ssl.SSLContext, password: Path) -> dict:
    """Full registration + PKCE + owner login + token exchange over real TLS.

    Secrets are returned in memory only. The caller logs neither this dictionary
    nor OAuth request/response bodies.
    """
    callback = 'https://chatgpt.com/connector/oauth/livingmath018qa'
    with httpx.Client(base_url=origin, verify=context, timeout=15, follow_redirects=False) as http:
        r = http.post('/register', json={'client_name': 'LM018 private QA', 'redirect_uris': [callback],
            'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
            'token_endpoint_auth_method': 'client_secret_post', 'scope': 'research'})
        r.raise_for_status()
        registration = r.json()
        verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        r = http.get('/authorize', params={'client_id': registration['client_id'], 'redirect_uri': callback,
            'response_type': 'code', 'code_challenge': challenge, 'code_challenge_method': 'S256',
            'scope': 'research', 'state': state, 'resource': origin + '/mcp'})
        assert r.status_code in (302, 303, 307)
        login = r.headers['location']
        assert login.startswith(origin + '/login?')
        assert http.get(login).status_code == 200
        request = parse_qs(urlparse(login).query)['request'][0]
        r = http.post('/login', data={'request': request, 'password': password.read_text().strip()}, headers={'Origin': origin})
        assert r.status_code == 303
        query = parse_qs(urlparse(r.headers['location']).query)
        assert query['state'] == [state]
        r = http.post('/token', data={'grant_type': 'authorization_code', 'client_id': registration['client_id'],
            'client_secret': registration['client_secret'], 'code': query['code'][0], 'code_verifier': verifier,
            'redirect_uri': callback, 'resource': origin + '/mcp'})
        r.raise_for_status()
        return {**r.json(), 'client_id': registration['client_id'], 'client_secret': registration['client_secret']}


@asynccontextmanager
async def serving(data, database, out, label, forbidden, enabled=True, port=None, fault_point=None, rate=1000, window=60):
    if not (data / 'tls').exists():
        tls(data / 'tls')
    cert, key, password = (data / 'tls' / name for name in ('ca.pem', 'tls-key.pem', 'owner-password'))
    context = ssl.create_default_context(cafile=str(cert))
    if port is None:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
    origin = 'https://localhost:' + str(port)
    args = [sys.executable, str(SOURCE / 'deploy018_http.py'), '--data', str(data), '--typed', str(database),
        '--origin', origin, '--port', str(port), '--cert', str(cert), '--key', str(key), '--password', str(password)]
    if enabled:
        args += ['--enable018', '--rate', str(rate), '--window', str(window)]
    for p in forbidden:
        args += ['--forbidden', str(p)]
    env = {**os.environ, 'LM014_NATIVE_LEDGER': str(data / 'native-I-T.jsonl')}
    for k in ('LM018_FAULT', 'LIVE_MATH_ENGINE_017'):
        env.pop(k, None)
    if fault_point:
        env['LM018_FAULT'] = fault_point
    error = (out / (label + '-stderr.txt')).open('w')
    start = time.perf_counter_ns()
    process = MeasuredProcess(args, stdout=error, stderr=error, env=env)
    try:
        async with httpx.AsyncClient(verify=context, timeout=0.5) as http:
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError('018_HTTP_SERVER_EXIT:' + str(process.returncode) + ':' + label)
                try:
                    if (await http.get(origin + '/healthz')).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)
            else:
                raise RuntimeError('018_HTTP_START_DEADLINE')
        token = await asyncio.to_thread(oauth, origin, context, password)
        yield origin, context, token, process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
        error.close()
        usage = process.child_usage
        with (out / 'http-processes.jsonl').open('a') as stream:
            stream.write(json.dumps({'label': label, 'pid': process.pid, 'exit_code': process.returncode,
                'wall_ns': time.perf_counter_ns() - start, 'CPU_ns': round((usage.ru_utime + usage.ru_stime) * 1e9),
                'peak_RSS_KiB': usage.ru_maxrss, 'enabled018': enabled}) + '\n')


@asynccontextmanager
async def client(origin, context, token, wire):
    async with httpx.AsyncClient(verify=context, headers={'Authorization': 'Bearer ' + token}, timeout=35) as http:
        async with streamable_http_client(origin + '/mcp', http_client=http) as (read, write, _):
            async with ClientSession(Tap(read, wire, 'response'), Tap(write, wire, 'request')) as session:
                yield session
