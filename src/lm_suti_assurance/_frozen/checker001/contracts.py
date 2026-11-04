"""Canonical typed envelopes; generator identity is provenance, not evidence."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def byte_digest(value):
    return hashlib.sha256(value).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def load(path):
    return strict_json(Path(path).read_text())


def claim_digest(candidate):
    return digest({k: v for k, v in candidate.items() if k not in {'generator', 'candidate_id'}})


@dataclass(frozen=True)
class SourceSnapshot:
    record: dict

    @classmethod
    def create(cls, source_id, text, origin, *, version='1', kind='qa', schema_id=None, can_embed=True):
        return cls({'schema': 'symseq.assurance.source.v1', 'source_id': source_id,
            'version': version, 'kind': kind, 'content_utf8': text,
            'sha256': byte_digest(text.encode('utf-8')), 'schema_id': schema_id,
            'rights': {'origin': origin, 'status': 'DECLARED_USER_AUTHORIZED',
                'can_embed': can_embed, 'attribution': origin},
            'provenance': {'method': 'immutable_bytes', 'author_endorsement_claimed': False}})


@dataclass(frozen=True)
class CandidateRecord:
    record: dict

    @property
    def semantic_digest(self):
        return claim_digest(self.record)


@dataclass(frozen=True)
class Witness:
    record: dict

    @property
    def ref(self):
        return 'sha256:' + digest(self.record)


@dataclass(frozen=True)
class AssuranceDecision:
    record: dict


@dataclass(frozen=True)
class ResearchArtifact:
    record: dict


def source_ref(source):
    return {'source_id': source['source_id'], 'sha256': source['sha256'],
        'pointer': None, 'byte_start': 0,
        'byte_end': len(source['content_utf8'].encode('utf-8')) if source['content_utf8'] is not None else 0}


def verifier_digest():
    root = Path(__file__).parent
    names = ['contracts.py', 'checks.py', 'finite_semantics.py', 'independent_vm.py',
        'bounded_program.py', 'ledger.py', 'ASSURANCE_CLAIM_V1.schema.json', 'ASSURANCE_DECISION_V1.schema.json',
        'SOURCE_SNAPSHOT_V1.schema.json']
    return digest({name: byte_digest((root / name).read_bytes()) for name in names})
