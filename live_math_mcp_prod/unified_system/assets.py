"""Build and read a hash-pinned, operator-selected public research asset bundle."""
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse
from zipfile import ZipFile


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build(repo: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    # Source checkouts carry the reviewed bundle, not whole private author archives.
    published = repo / 'assets/unified'
    if (published / 'manifest.json').is_file() and not (repo / 'SUTI.uni.zip').exists():
        checked = Assets(published)
        for name in (*checked.manifest, 'manifest.json'):
            (out / name).write_bytes((published / name).read_bytes())
        return checked.manifest
    pairs = json.loads((repo/'bridge004/frozen-pairs.json').read_text())
    source_bytes = {}
    for pair in pairs:
        archive = repo/pair['archive_name']
        if sha(archive.read_bytes()) != pair['archive_sha256']:
            raise ValueError('SUTI_WORKING_ARCHIVE_HASH_DRIFT')
        with ZipFile(archive) as z:
            pending = [pair['member']]
            while pending:
                member = pending.pop()
                if member in source_bytes:
                    continue
                matches = [x for x in z.infolist() if x.filename == member]
                if len(matches) != 1 or matches[0].file_size > 2097152 or '..' in PurePosixPath(member).parts:
                    raise ValueError('UNSAFE_OR_AMBIGUOUS_REVIEWED_SOURCE')
                raw = z.read(member)
                if member == pair['member'] and sha(raw) != pair['source_sha256']:
                    raise ValueError('ORIGINAL_SOURCE_SCHEMA_DRIFT')
                document = json.loads(raw)
                source_bytes[member] = {'text': raw.decode('utf-8'), 'sha256': sha(raw),
                    'archive': pair['archive_name'], 'archive_sha256': pair['archive_sha256']}
                # Traverse data only. No source program from the archives is imported/executed.
                def refs(value):
                    if isinstance(value, dict):
                        ref = value.get('$ref')
                        if isinstance(ref, str) and not ref.startswith('#'):
                            if urlparse(ref).scheme:
                                raise ValueError('REMOTE_SCHEMA_REFERENCE_NOT_REVIEWED')
                            target = urljoin('https://source.invalid/'+member, ref).split('#')[0]
                            pending.append(unquote(target.removeprefix('https://source.invalid/')))
                        for child in value.values():
                            refs(child)
                    elif isinstance(value, list):
                        for child in value:
                            refs(child)
                refs(document)
    relations = [json.loads(line) for line in (repo/'bridge004/candidate-relations.jsonl').read_text().splitlines() if line]
    bundle = {'format': 'unified-source-assets/1', 'pairs': pairs, 'schema_members': source_bytes,
              'relations': relations, 'reviewed_contexts': json.loads((repo/'bridge004/reviewed-contexts.json').read_text()),
              'native_SUTI_runtime': 'NOT_EXECUTED', 'proof_status': 'unverified'}
    (out/'bridge.json').write_text(json.dumps(bundle, ensure_ascii=False))
    (out/'alch006.json').write_bytes((repo/'alch006/final-model.json').read_bytes())
    manifest = {p.name: sha(p.read_bytes()) for p in out.iterdir()}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    return manifest


class Assets:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        manifest = json.loads((self.root/'manifest.json').read_text())
        for name, expected in manifest.items():
            if name not in {'bridge.json', 'alch006.json'} or sha((self.root/name).read_bytes()) != expected:
                raise ValueError('UNIFIED_ASSET_HASH_DRIFT')
        self.manifest = manifest
        self.bridge = json.loads((self.root/'bridge.json').read_bytes())
        self.model = json.loads((self.root/'alch006.json').read_bytes())
        for member, item in self.bridge['schema_members'].items():
            if sha(item['text'].encode()) != item['sha256']:
                raise ValueError('BUNDLED_SOURCE_SCHEMA_HASH_DRIFT:' + member)
