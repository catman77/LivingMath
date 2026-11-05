#!/usr/bin/env python3
"""Independent finite S/P rewrite 2-complex reference, Python stdlib only.

No MCP, LLM, numerical White Star kernel or external data is used.
The chosen 2-complex has vertices = balanced S/P words of even length <= N,
edges = POSITION-LABELLED cancellations SP/PS -> empty,
faces = local bigons (same result) or diamonds (one-step join).
The pi1 certificate is valid ONLY for this explicitly defined complex.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from itertools import product, combinations
import argparse
import hashlib
import json


@dataclass(frozen=True)
class Edge:
    id: int
    src: str
    dst: str
    pos: int
    pair: str


@dataclass(frozen=True)
class Face:
    id: int
    peak: str
    left: tuple[int, ...]
    right: tuple[int, ...]
    kind: str


def balanced_words(n: int) -> list[str]:
    if n % 2:
        return []
    return [''.join(chars) for chars in product('SP', repeat=n)
            if chars.count('S') == n // 2]


def gf2_rank(columns: list[int]) -> int:
    pivots: dict[int, int] = {}
    for col in columns:
        x = col
        while x:
            p = x.bit_length() - 1
            if p in pivots:
                x ^= pivots[p]
            else:
                pivots[p] = x
                break
    return len(pivots)


class SPComplex:
    def __init__(self, max_len: int, faces: str = 'all'):
        if max_len < 2 or max_len % 2 or max_len > 10:
            raise ValueError('reference fixture supports even 2 <= max_len <= 10')
        if faces not in ('all', 'none', 'bigons', 'diamonds'):
            raise ValueError('bad face policy')
        self.max_len = max_len
        self.words = [''] + [w for n in range(2, max_len + 1, 2)
                           for w in balanced_words(n)]
        self.edges: list[Edge] = []
        self.out: dict[str, list[int]] = defaultdict(list)
        for w in self.words:
            for pos in range(len(w) - 1):
                if w[pos] == w[pos+1]:
                    continue
                dst = w[:pos] + w[pos+2:]
                edge = Edge(len(self.edges), w, dst, pos, w[pos:pos+2])
                self.out[w].append(edge.id)
                self.edges.append(edge)
        self.faces: list[Face] = []
        self.peak_to_face: dict[tuple[int, int], int] = {}
        self.all_peak_count = 0
        self.peak_unresolved = []
        self._build_faces(faces)

    def _build_faces(self, policy: str) -> None:
        for w in self.words:
            for e, f in combinations(self.out[w], 2):
                self.all_peak_count += 1
                a, b = self.edges[e].dst, self.edges[f].dst
                if a == b:
                    kind, l, r = 'bigon', (e,), (f,)
                else:
                    meets = []
                    for g in self.out[a]:
                        for h in self.out[b]:
                            if self.edges[g].dst == self.edges[h].dst:
                                meets.append((self.edges[g].dst, g, h))
                    if not meets:
                        self.peak_unresolved.append((w, e, f))
                        continue
                    _, g, h = min(meets)
                    kind, l, r = 'diamond', (e, g), (f, h)
                if policy == 'none' or (policy == 'bigons' and kind != 'bigon') or (policy == 'diamonds' and kind != 'diamond'):
                    continue
                face = Face(len(self.faces), w, l, r, kind)
                self.peak_to_face[(e, f)] = face.id
                self.faces.append(face)

    def verify_path(self, path: tuple[int, ...], start: str):
        w = start
        for edge_id in path:
            e = self.edges[edge_id]
            if e.src != w:
                raise AssertionError(f'broken directed path at edge {edge_id}')
            if len(e.src) - len(e.dst) != 2:
                raise AssertionError('non-terminating edge')
            if e.pair not in ('SP', 'PS'):
                raise AssertionError('illegal cancellation')
            if e.dst != e.src[:e.pos] + e.src[e.pos+2:]:
                raise AssertionError('incorrect cancellation result')
            w = e.dst
        return w

    def verify_faces(self) -> bool:
        seen: set[tuple[int, int]] = set()
        for face in self.faces:
            assert face.left and face.right
            assert face.peak in self.words
            assert face.kind in ('bigon', 'diamond')
            assert len(face.left) == len(face.right) == (1 if face.kind == 'bigon' else 2)
            e, f = face.left[0], face.right[0]
            assert e != f and self.edges[e].src == self.edges[f].src == face.peak
            pair = tuple(sorted((e, f)))
            assert pair not in seen
            seen.add(pair)
            assert self.verify_path(face.left, face.peak) == self.verify_path(face.right, face.peak)
        assert all(w == '' or self.out[w] for w in self.words)
        return True

    def canonical_path(self, word: str) -> tuple[int, ...]:
        path = []
        w = word
        while w:
            e = self.out[w][0]
            path.append(e)
            w = self.edges[e].dst
        return tuple(path)

    def pi1_certificate(self):
        """Construct and check induction-on-length path coherence certificate.

        A lemma for each noncanonical edge e:u->v proves
        e + C(v) homotopic to C(u). Local peaks provide its face;
        recursively shorter child edges provide the remaining homotopies.
        This is stronger than H1(F2)=0 and is NOT a generic pi1 solver.
        """
        if self.peak_unresolved:
            return None
        if len(self.peak_to_face) != self.all_peak_count:
            return None
        self.verify_faces()
        certificates: dict[int, dict] = {}
        for w in sorted(self.words, key=lambda x: (len(x), x)):
            if not w:
                continue
            canon = self.out[w][0]
            for e in self.out[w]:
                if e == canon:
                    certificates[e] = {'edge': e, 'case': 'canonical', 'canonical': canon,
                                       'dependencies': []}
                    continue
                pair = tuple(sorted((e, canon)))
                fid = self.peak_to_face.get(pair)
                if fid is None:
                    return None
                face = self.faces[fid]
                branches = {face.left[0]: face.left[1:], face.right[0]: face.right[1:]}
                assert set(branches) == {e, canon}
                deps = list(branches[e] + branches[canon])
                for dep in deps:
                    assert len(self.edges[dep].src) < len(w)
                    assert dep in certificates
                certificates[e] = {'edge': e, 'case': 'local_peak',
                                   'canonical': canon, 'face': fid,
                                   'dependencies': deps}
        assert len(certificates) == len(self.edges)
        payload = {'boundary': 'this bounded finite SP 2-complex only',
                   'proof': 'canonical reduction paths unique up to certified local peaks by induction on length',
                   'lemmas': [certificates[i] for i in range(len(self.edges))]}
        payload['sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()
        return payload

    def invariants(self) -> dict:
        assert self.verify_faces()
        edge_count = len(self.edges)
        vertices = len(self.words)
        beta_graph = edge_count - vertices + 1
        column_vectors = []
        for face in self.faces:
            x = 0
            for eid in face.left + face.right:
                x ^= 1 << eid
            column_vectors.append(x)
        rank = gf2_rank(column_vectors)
        certificate = self.pi1_certificate()
        return {
            'max_len': self.max_len,
            'vertices': vertices,
            'edges': edge_count,
            'connected': True,
            'beta1_graph': beta_graph,
            'peak_total': self.all_peak_count,
            'faces': len(self.faces),
            'unresolved_peaks': len(self.peak_unresolved),
            'rank_d2_F2': rank,
            'H1_F2_dim': beta_graph - rank,
            'pi1_status': 'PROVED_TRIVIAL_WITH_CERTIFICATE' if certificate else 'NOT_PROVED',
            'pi1_certificate_sha256': certificate['sha256'] if certificate else None,
            'face_policy': 'all' if len(self.faces) == self.all_peak_count else 'partial',
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-len', type=int, default=10)
    parser.add_argument('--face-policy', choices=['all','none','bigons','diamonds'], default='all')
    parser.add_argument('--certificate-json', default='')
    args = parser.parse_args()
    c = SPComplex(args.max_len, args.face_policy)
    print(json.dumps(c.invariants(), ensure_ascii=False, indent=2))
    if args.certificate_json:
        cert = c.pi1_certificate()
        with open(args.certificate_json, 'w', encoding='utf-8') as f:
            json.dump(cert, f, ensure_ascii=False, sort_keys=True, indent=2)
