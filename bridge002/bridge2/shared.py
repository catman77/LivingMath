"""Reuse current workspace helpers, or the captured helpers in a standalone ZIP."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY = ROOT.parent / 'bridge001'
if not DEPENDENCY.is_dir():
    DEPENDENCY = ROOT / 'vendor/bridge001'
CURRENT_DEPENDENCY_HASHES = {
    name: hashlib.sha256((DEPENDENCY / name).read_bytes()).hexdigest()
    for name in json.loads((ROOT / 'bridge001-dependency.json').read_text())['files']}
sys.path.insert(0, str(DEPENDENCY))
from bridge.canonical import Refusal, bytes_hash, canonical_bytes, canonical_hash, read_json, statuses
from bridge.intake import check_signature

__all__ = ['ROOT', 'DEPENDENCY', 'Refusal', 'bytes_hash', 'canonical_bytes', 'canonical_hash',
           'read_json', 'statuses', 'check_signature']
