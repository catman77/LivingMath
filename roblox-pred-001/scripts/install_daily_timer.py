"""Install the user-level daily observation requested by the prospective protocol."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python',type=Path,default=Path(sys.executable))
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    # Resolving the venv's Python symlink loses its pyvenv.cfg and installed package.
    python=args.python.expanduser().absolute()
    if not python.is_file():
        raise SystemExit('Python executable not found: '+str(python))
    unit_dir=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'systemd/user'
    service=(root/'deploy/livingmath-roblox-observation.service.in').read_text()
    service=service.replace('@PYTHON@',str(python)).replace('@PROJECT_ROOT@',str(root))
    if args.dry_run:
        print(service)
        raise SystemExit(0)
    unit_dir.mkdir(parents=True,exist_ok=True)
    for name,body in [('livingmath-roblox-observation.service',service),
        ('livingmath-roblox-observation.timer',(root/'deploy/livingmath-roblox-observation.timer').read_text())]:
        path=unit_dir/name
        if path.exists() and path.read_text()!=body and not path.read_text().startswith('# Managed by LivingMath ROBLOX-PRED-001'):
            raise SystemExit('Existing different unit preserved: '+str(path))
        path.write_text(body)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','livingmath-roblox-observation.timer'],check=True)
    subprocess.run(['systemctl','--user','list-timers','livingmath-roblox-observation.timer','--no-pager'],check=True)
