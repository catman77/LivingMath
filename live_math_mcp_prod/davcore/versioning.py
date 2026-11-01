"""Pin evaluator semantics separately from adapter/source semantics."""
from pathlib import Path
import hashlib

from .ast import digest


def backend_binding() -> str:
    root = Path(__file__).parent
    return digest({name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                   for name in ['ast.py', 'models.py', 'finite.py', 'smt.py', 'versioning.py']})
