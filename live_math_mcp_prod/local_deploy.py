"""Supervise local HTTP + free HTTPS ingress; credentials never leave private files."""
import argparse
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile


HOME_DIR = Path.home()
CONFIG = HOME_DIR / '.config/livingmath'
STATE = HOME_DIR / '.local/state/livingmath'
DATA = HOME_DIR / '.local/share/livingmath'
APP_DIR = Path(__file__).resolve().parent
REPOSITORY = APP_DIR.parent
BINARY = HOME_DIR / '.local/opt/livingmath/bin/cloudflared'
UNITS = HOME_DIR / '.config/systemd/user'
MARKER = '# Managed by LivingMath local_deploy.py\n'


def private_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def systemctl(*args):
    subprocess.run(['systemctl', '--user', *args], check=True)


def systemd_argument(value):
    value = str(value)
    if '\n' in value or '\r' in value:
        raise ValueError('Service paths must not contain newlines.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def install():
    if not BINARY.is_file():
        raise SystemExit('Install the official cloudflared binary at ' + str(BINARY))
    for directory in (CONFIG, STATE, DATA):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    password = CONFIG / 'login-password'
    if not password.exists():
        private_write(password, secrets.token_urlsafe(32) + '\n')
    python = REPOSITORY / '.venv/bin/python'
    if not python.is_file():
        raise SystemExit('Create the repository .venv before installing services.')
    common = '''\n[Service]
Type=simple
Restart=on-failure
RestartSec=10
TimeoutStopSec=15
KillMode=control-group
UMask=0077
NoNewPrivileges=true
Environment=PYTHONUNBUFFERED=1
'''
    http = (MARKER + '[Unit]\nDescription=LivingMath authenticated local MCP HTTP server\n'
            + 'ConditionPathExists=%h/.config/livingmath/server.env\n'
            + common
            + 'EnvironmentFile=%h/.config/livingmath/server.env\n'
            + 'WorkingDirectory=' + str(APP_DIR).replace('%', '%%') + '\n'
            + 'ExecStart=' + systemd_argument(python) + ' ' + systemd_argument(APP_DIR / 'http_server.py')
            + '\n\n[Install]\nWantedBy=default.target\n')
    tunnel = (MARKER + '[Unit]\nDescription=LivingMath free HTTPS tunnel\n'
              + 'Wants=network-online.target\nAfter=network-online.target\n'
              + common
              + 'Restart=always\n'
              + 'WorkingDirectory=' + str(APP_DIR).replace('%', '%%') + '\n'
              + 'ExecStart=' + systemd_argument(python) + ' ' + systemd_argument(Path(__file__).resolve()) + ' tunnel'
              + '\n\n[Install]\nWantedBy=default.target\n')
    paths = []
    UNITS.mkdir(parents=True, exist_ok=True)
    for name, text in (('livingmath-http.service', http), ('livingmath-https.service', tunnel)):
        path = UNITS / name
        if path.exists() and not path.read_text().startswith(MARKER):
            raise SystemExit('Refusing to replace an unmanaged service: ' + str(path))
        private_write(path, text)
        paths.append(str(path))
    subprocess.run(['systemd-analyze', '--user', 'verify', *paths], check=True)
    systemctl('daemon-reload')
    systemctl('enable', 'livingmath-http.service', 'livingmath-https.service')
    systemctl('start', 'livingmath-https.service')
    print('Services installed. Retrieve the current URL with:')
    print(str(python) + ' ' + str(Path(__file__).resolve()) + ' status')
    print('Owner password file: ' + str(password))


def configure_origin(origin):
    environment = {
        'LIVE_MATH_PUBLIC_URL': origin,
        'LIVE_MATH_DATA_DIR': str(DATA),
        'LIVE_MATH_PASSWORD_FILE': str(CONFIG / 'login-password'),
        'LIVE_MATH_PORT': '18765',
    }
    # systemd EnvironmentFile uses quoted values; none contain credentials.
    content = '\n'.join(key + '=' + systemd_argument(value) for key, value in environment.items()) + '\n'
    private_write(CONFIG / 'server.env', content)
    private_write(STATE / 'mcp-url', origin + '/mcp\n')
    systemctl('restart', 'livingmath-http.service')
    print('MCP endpoint: ' + origin + '/mcp', flush=True)


def tunnel():
    command = [str(BINARY), 'tunnel', '--config', '/dev/null', '--no-autoupdate',
               '--loglevel', 'info', '--protocol', 'http2', '--edge-ip-version', '4',
               '--metrics', '127.0.0.1:18766', '--url', 'http://127.0.0.1:18765']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, bufsize=1)

    def stop(signum, frame):
        process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    origin = None
    try:
        for line in process.stdout:
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match and match.group() != origin:
                origin = match.group()
                configure_origin(origin)
            print(line.rstrip(), flush=True)
        result = process.wait()
        if result:
            raise SystemExit(result)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        systemctl('stop', 'livingmath-http.service')
        (STATE / 'mcp-url').unlink(missing_ok=True)


def status():
    subprocess.run(['systemctl', '--user', 'show', 'livingmath-http.service',
                    'livingmath-https.service', '-p', 'Id', '-p', 'ActiveState', '-p', 'SubState'])
    url = STATE / 'mcp-url'
    print('MCP URL: ' + (url.read_text().strip() if url.exists() else 'not available yet'))
    print('Owner password file: ' + str(CONFIG / 'login-password'))


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'tunnel', 'status', 'stop'])
    args = parser.parse_args()
    if args.command == 'install':
        install()
    elif args.command == 'tunnel':
        tunnel()
    elif args.command == 'status':
        status()
    else:
        systemctl('stop', 'livingmath-https.service', 'livingmath-http.service')
