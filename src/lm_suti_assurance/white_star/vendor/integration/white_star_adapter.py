"""Runnable integration seam; no MCP, database, LLM or new search algorithm.

The frozen experiment source lives in ../code. Production should run this in
an isolated worker (the legacy modules use short, top-level import names).
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from math import gcd
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code/experiments/llm_white_star_transfer'))
from rotated_atlas import expand, search
from bridge import compile_atlas, validate


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


class ContractError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise ContractError(code, message)


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, 'INVALID_INPUT',
            f'{name}: expected integer in [{low}, {high}]')


def common_snapshot(data):
    """Explicit source/concept intersection for a future SUTI ingress adapter.

    This is not already an accepted schema of the connected SUTI runtime.
    Coordinate and protocol choices remain in the separately hashed encoding.
    """
    return dict(schema='levinmas-semantic-input/1', source=data['source'],
                concepts=[{k: c[k] for k in ('id', 'label', 'evidence')}
                          for c in data['concepts']],
                source_relations=data['source_relations'],
                uncertainties=data['uncertainties'])


def explore(request):
    request = deepcopy(request)
    require(request.get('schema') == 'levinmas-white-star-request/1',
            'INVALID_INPUT', 'unsupported request schema')
    require(set(request) <= {'schema', 'encoding', 'atlas_profile'},
            'INVALID_INPUT', 'unknown request field')
    data = request['encoding']
    profile = request.get('atlas_profile', 'cj_v1')
    require(profile in ('base_v1', 'cj_v1'), 'INVALID_INPUT', 'unknown atlas_profile')
    protocol = data['protocol']
    integer(protocol['seed'], -(2**31), 2**31-1, 'seed')
    integer(protocol['steps'], 1, 4096, 'steps')
    integer(protocol['candidates_per_step'], 1, 16, 'candidates_per_step')
    integer(protocol['frame_size'], 1, protocol['steps'], 'frame_size')
    integer(protocol['decode_first_frames'], 1, 64, 'decode_first_frames')
    require(protocol.get('semantic_reranking', False) is False and
            protocol.get('optimizer_feedback', False) is False and
            protocol.get('exclude_zero_direction', True) is True,
            'UNSUPPORTED_POLICY', 'no reranking, feedback or zero-direction decoding')
    require(len(data['source']['text'].encode('utf-8')) <= 48000,
            'SOURCE_TOO_LARGE', 'raw UTF-8 text limit is 48000 bytes')
    require(len(encode(request).encode('utf-8')) <= 262144,
            'INPUT_TOO_LARGE', 'request limit is 256 KiB')
    validate(data)
    require(isinstance(data['axes'], list) and len(data['axes']) == 2,
            'INVALID_INPUT', 'exactly two declared axes are required')
    for c in data['concepts']:
        require(isinstance(c['label'], str) and bool(c['label']),
                'INVALID_INPUT', 'a concept label is required')
        require(isinstance(c['encoding_rationale'], str) and bool(c['encoding_rationale']),
                'INVALID_INPUT', 'an explicit coordinate rationale is required')
    if profile == 'cj_v1':
        atlas = expand(data)
    else:
        old = compile_atlas(data)
        atlas = dict(charts=[dict(view=c['view'], matrix=c['matrix'], aliases=[dict(
                         concepts=c['pair'], orientation='I', original_view=c['view'],
                         original_matrix=c['matrix'])]) for c in old['charts']],
                     semantic_maps=len(old['charts']), old_maps=len(old['charts']),
                     omitted_collinear_pairs=old['omitted_collinear_pairs'])
    require(len(atlas['charts']) <= 4096, 'ATLAS_LIMIT_EXCEEDED',
            'expanded unique CAD chart count exceeds native limit; do not truncate')
    native_protocol = dict(frozen_seed=protocol['seed'], steps=protocol['steps'],
                           candidates_per_step=protocol['candidates_per_step'])
    trace, readouts, stats = search(data, atlas, native_protocol)
    by_step = {r['step']: r for r in trace}
    for readout in readouts:
        x, y = by_step[readout['step']]['coordinates']
        scale = gcd(abs(x), abs(y))
        readout['signed_weights'] = [x // scale, y // scale]
        readout['claim_status'] = 'CREATIVE_RELATION_PROPOSAL_NOT_SOURCE_ENTAILMENT'
    size = protocol['frame_size']
    frames = []
    for start in range(0, len(readouts)-size+1, size):
        links = readouts[start:start+size]
        frames.append(dict(id=f'F{len(frames)+1:02}', steps=[x['step'] for x in links],
                           links=links))
    selected = frames[:protocol['decode_first_frames']]
    common = common_snapshot(data)
    states = {tuple(a['state']) for r in readouts for a in r['alternatives']}
    result = dict(
        schema='levinmas-white-star-local-result/1', engine='white_star',
        atlas_profile=profile, input_sha256=digest(request),
        common_snapshot_sha256=digest(common), encoding_sha256=digest(data),
        source_sha256=data['source']['sha256'], common_snapshot=common,
        atlas=atlas, trace=trace, readouts=readouts, frames=frames,
        selected_frames=selected,
        summary=dict(**stats, unique_numeric_maps=len(atlas['charts']),
                     labelled_maps=atlas['semantic_maps'], unique_qualitative_modes=len(states),
                     nonzero_observations=len(readouts), frames=len(frames),
                     decoded_frame_slots=len(selected),
                     tail_observations=len(readouts) % size,
                     semantic_aliases_are_not_extra_numeric_projections=True),
        decoder_packet=dict(
            schema='levinmas-white-star-decoder/1', source=data['source'],
            axes=data['axes'], concepts=data['concepts'],
            source_relations=data['source_relations'], uncertainties=data['uncertainties'],
            frames=selected,
            instruction='Use every selected frame in order. Retain all aliases as alternative '
                        'labels of the same numeric observation, not independent findings. '
                        'Separate literal quotations, proposed relations, added images and '
                        'target-model assumptions. Weights are not probabilities or truth. '
                        'Do not reinterpret sign as negation of a source sentence.'),
        status=dict(numeric_run='COMPUTED', source_bytes='MATCHED',
                    semantic_fidelity='UNASSESSED', prose='NOT_GENERATED',
                    formal_model='NOT_REQUESTED', physical_validity='NOT_CLAIMED'),
    )
    result['artifact_sha256'] = digest(result)
    require(len(encode(result).encode('utf-8')) <= 33554432,
            'RESULT_TOO_LARGE', 'local result exceeds 32 MiB; lower the explicit budget')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.input.stat().st_size > 262144:
            raise ContractError('INPUT_TOO_LARGE', 'request limit is 256 KiB')
        result = explore(json.loads(args.input.read_text(encoding='utf-8')))
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps(dict(ok=False, error=dict(code=getattr(exc, 'code', 'INVALID_INPUT'),
                                                  message=str(exc))), ensure_ascii=False),
              file=sys.stderr)
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding='utf-8')
        print(json.dumps(dict(output=str(args.output), artifact_sha256=result['artifact_sha256'],
                              summary=result['summary']), ensure_ascii=False))
    else:
        print(rendered, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
