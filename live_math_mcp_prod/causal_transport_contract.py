"""Verify a cleanup-only change without relaxing the frozen generation contract."""
import ast
import copy
import hashlib
import json
from pathlib import Path


class NormalizeCleanup(ast.NodeTransformer):
    def visit_ExceptHandler(self, node):
        name = ast.unparse(node.type) if node.type else ''
        if name in {'asyncio.TimeoutError', 'asyncio.CancelledError'}:
            # Keep the deadline marker: a late result must never become a success.
            assignments = [child for child in node.body if isinstance(child, ast.Raise) or (isinstance(child, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'timeout' for t in child.targets))]
            node.body = assignments + [ast.Pass()]
            return node
        return self.generic_visit(node)


def scientific_contract(path):
    tree = ast.parse(Path(path).read_text())
    parts = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
            {'MODEL', 'INPUT_TOKENS', 'TIMEOUT', 'CONCURRENCY', 'ENCODING', 'TASK', 'RULES'} for t in node.targets):
            parts.append(ast.dump(node, include_attributes=False))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {'schema', 'flat', 'make_prompt', 'infer'}:
            parts.append(ast.dump(NormalizeCleanup().visit(copy.deepcopy(node)), include_attributes=False))
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def cleanup_patch_valid(base, current):
    base, current = Path(base), Path(current)
    manifest = base / 'model-transport-patch.json'
    if not manifest.exists():
        return False
    recorded = json.loads(manifest.read_text())
    original = json.loads((base / 'source-hashes-before.json').read_text())['live_math_mcp_prod/causal_model.py']
    return (recorded['before_file_sha256'] == original
            and recorded['after_file_sha256'] == hashlib.sha256(current.read_bytes()).hexdigest()
            and recorded['before_scientific_contract'] == recorded['after_scientific_contract']
            and recorded['after_scientific_contract'] == scientific_contract(current))
