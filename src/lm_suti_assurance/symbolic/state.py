"""Immutable words and source spans. History lives separately in a content-addressed DAG."""

from dataclasses import dataclass
import hashlib, re, unicodedata
from ..core import digest
from ..errors import AssuranceError


def require(ok, code="INVALID_INPUT", field=None):
    if not ok:
        raise AssuranceError(code, field)


@dataclass(frozen=True)
class Atom:
    token: str
    spans: tuple  # (original source sha, UTF-8 byte start, byte end)


@dataclass(frozen=True)
class SymbolicState:
    atoms: tuple
    boundaries: tuple = ()  # (token offset, kind, original source position/id)

    @property
    def tokens(self):
        return tuple(a.token for a in self.atoms)

    @property
    def word_hash(self):
        return digest(
            {
                "tokens": self.tokens,
                "boundaries": sorted(set((p, k) for p, k, _ in self.boundaries)),
            }
        )

    def data(self):
        return {
            "tokens": list(self.tokens),
            "boundaries": [list(b) for b in self.boundaries],
            "source_spans": [list(a.spans) for a in self.atoms],
            "word_hash": self.word_hash,
        }


class History:
    def __init__(self):
        self.nodes = {}
        self.states = {}

    def add(self, state, parents, op, args, events=()):
        require(all(p in self.nodes for p in parents), "HISTORY_BROKEN")
        node = {
            "parent_ids": list(parents),
            "op": op,
            "op_args": args,
            "source_spans": sorted(set(s for a in state.atoms for s in a.spans)),
            "output_word_hash": state.word_hash,
            "events": list(events),
        }
        ident = digest(node)
        value = {"node_id": ident, **node}
        if ident in self.nodes:
            require(self.nodes[ident] == value, "HISTORY_BROKEN")
        self.nodes[ident] = value
        self.states[ident] = state
        return ident

    def verify(self):
        seen = set()
        for ident, node in self.nodes.items():
            require(
                ident == digest({k: v for k, v in node.items() if k != "node_id"})
                and set(node["parent_ids"]) <= seen,
                "HISTORY_BROKEN",
            )
            require(
                node["output_word_hash"] == self.states[ident].word_hash,
                "HISTORY_BROKEN",
            )
            seen.add(ident)
        return True


def reduce_sp(tokens):
    require(set(tokens) <= {"S", "P"}, "SP_DOMAIN_REQUIRED")
    current = list(tokens)
    events = []
    while True:
        index = next(
            (i for i in range(len(current) - 1) if current[i] != current[i + 1]), None
        )
        if index is None:
            break
        events.append(
            {"positions": [index, index + 1], "pair": current[index : index + 2]}
        )
        del current[index : index + 2]
    return tuple(current), events


def alpha(tokens):
    names = {}
    return tuple(names.setdefault(t, len(names)) for t in tokens)


def alpha_corpus(words, scope="global"):
    names = {}
    return tuple(
        (
            alpha(w)
            if scope == "local"
            else tuple(names.setdefault(t, len(names)) for t in w)
        )
        for w in words
    )


def normalized_chars(text, policy):
    # Canonical-combining clusters plus a conservative Hangul composition group.
    # Every normalized codepoint points to the complete original byte cluster.
    groups = []
    start = 0
    cluster = ""
    byte = 0
    for c in text:
        compose = bool(
            cluster
            and unicodedata.normalize("NFC", cluster + c)
            != unicodedata.normalize("NFC", cluster) + unicodedata.normalize("NFC", c)
        )
        if cluster and not unicodedata.combining(c) and not compose:
            groups.append((cluster, start, byte))
            cluster = ""
            start = byte
        if not cluster:
            start = byte
        cluster += c
        byte += len(c.encode())
    if cluster:
        groups.append((cluster, start, byte))
    out = []
    for group, a, b in groups:
        for c in unicodedata.normalize("NFC", group) if policy == "NFC" else group:
            # With policy none each original codepoint gets its exact byte interval.
            if policy == "none":
                n = len(c.encode())
                out.append((c, a, a + n))
                a += n
            else:
                out.append((c, a, b))
    return out


def source_states(request, history):
    source = request["source"]
    text = source["text"]
    raw = text.encode()
    sha = hashlib.sha256(raw).hexdigest()
    require(sha == source["sha256"], "SOURCE_MISMATCH", "/source/sha256")
    segmentation = request["segmentation"]
    policy = request.get("normalization", "none")
    chars = normalized_chars(text, policy)
    normalized = "".join(c for c, _, _ in chars)
    require(
        normalized == (unicodedata.normalize("NFC", text) if policy == "NFC" else text),
        "NORMALIZATION_MAP_FAILURE",
    )
    unit = segmentation["unit"]
    pieces = []
    if unit == "literal_token":
        require(
            bool(segmentation.get("tokens")) or not raw,
            "TOKENS_REQUIRED",
            "/segmentation/tokens",
        )
        previous = 0
        for t in segmentation.get("tokens", []):
            a, b = t["byte_start"], t["byte_end"]
            require(
                previous <= a < b <= len(raw), "INVALID_SPAN", "/segmentation/tokens"
            )
            try:
                surface = raw[a:b].decode()
            except UnicodeError:
                raise AssuranceError("INVALID_SPAN", "/segmentation/tokens")
            require(surface == t["token"], "SPAN_TEXT_MISMATCH", "/segmentation/tokens")
            if policy == "NFC":
                require(
                    a in {x for _, x, _ in chars} and b in {y for _, _, y in chars},
                    "NFC_TOKEN_SPLITS_CLUSTER",
                    "/segmentation/tokens",
                )
            pieces.append(
                (
                    (
                        unicodedata.normalize("NFC", t["token"])
                        if policy == "NFC"
                        else t["token"]
                    ),
                    a,
                    b,
                )
            )
            previous = b
    elif unit == "codepoint":
        pieces = [(c, a, b) for c, a, b in chars if c not in "\r\n"]
    else:
        pattern = r"[^\r\n]+" if unit == "line" else r"\S+"
        for match in re.finditer(pattern, normalized):
            a = chars[match.start()][1]
            b = chars[match.end() - 1][2]
            pieces.append((match.group(), a, b))
    atoms = tuple(Atom(t, ((sha, a, b),)) for t, a, b in pieces)
    require(
        len(atoms) <= request["search"]["max_word_tokens"],
        "WORD_TOKEN_LIMIT",
        "/source/text",
    )
    if "alphabet" in source:
        require(
            set(a.token for a in atoms) <= set(source["alphabet"]),
            "ALPHABET_MISMATCH",
            "/source/alphabet",
        )
    if request["algebra"]["kind"] == "SP":
        require(
            set(a.token for a in atoms) <= {"S", "P"},
            "SP_DOMAIN_REQUIRED",
            "/source/text",
        )
    segments = source.get("segments", [])
    ids = {s["id"] for s in segments}
    require(len(ids) == len(segments), "INVALID_HIERARCHY")
    previous_ids = {}
    valid_bytes = (
        {0, len(raw)}
        | {a for _, a, _ in normalized_chars(text, "none")}
        | {b for _, _, b in normalized_chars(text, "none")}
    )
    for s in segments:
        a, b = s["byte_start"], s["byte_end"]
        require(
            a in valid_bytes and b in valid_bytes and a <= b,
            "INVALID_SPAN",
            "/source/segments",
        )
        parent = s.get("parent_id")
        require(parent is None or parent in previous_ids, "INVALID_HIERARCHY")
        if parent is not None:
            require(
                previous_ids[parent]["byte_start"]
                <= a
                <= b
                <= previous_ids[parent]["byte_end"],
                "INVALID_HIERARCHY",
            )
        previous_ids[s["id"]] = s
    boundaries = []
    ranges = []
    offset = 0
    lines = (
        text.splitlines(keepends=True)
        if segmentation["record_boundaries"] == "lines"
        else [text]
    )
    if not lines:
        lines = [""]
    for index, line in enumerate(lines):
        end = offset + len(line.encode())
        indices = [i for i, (_, a, b) in enumerate(pieces) if offset <= a and b <= end]
        start_i = indices[0] if indices else sum(b <= offset for _, a, b in pieces)
        end_i = indices[-1] + 1 if indices else start_i
        boundaries.extend(
            [(start_i, "record_start", str(index)), (end_i, "record_end", str(index))]
        )
        ranges.append((start_i, end_i, offset, end))
        offset = end
    state = SymbolicState(atoms, tuple(sorted(set(boundaries))))
    root = history.add(
        state,
        (),
        "SOURCE",
        {"source_sha256": sha, "segmentation": segmentation, "normalization": policy},
    )
    records = []
    for i, (a, b, _, _) in enumerate(ranges):
        child = SymbolicState(
            atoms[a:b],
            tuple(
                (p - a, k, n)
                for p, k, n in state.boundaries
                if a <= p <= b and n == str(i)
            ),
        )
        records.append(
            history.add(child, (root,), "SOURCE_RECORD", {"record": i, "range": [a, b]})
        )
    coverage = sorted(set((a, b) for _, a, b in pieces))
    gaps = []
    p = 0
    for a, b in coverage:
        if p < a:
            gaps.append([p, a])
        p = max(p, b)
    if p < len(raw):
        gaps.append([p, len(raw)])
    return (
        root,
        records,
        {
            "original": source,
            "normalized_text": normalized,
            "normalization": policy,
            "normalized_codepoint_to_original_bytes": [[a, b] for _, a, b in chars],
            "unrepresented_separators": gaps,
            "declared_hierarchy": segments,
            "layout_status": "PROVIDED" if source.get("layout") else "UNAVAILABLE",
        },
    )


def apply(state, op, args, other=None):
    require(
        op
        in (
            "CONCAT",
            "SPLIT",
            "RENAME",
            "SUBSTITUTE",
            "REVERSE",
            "SP_INV",
            "REDUCE_SP",
            "INSERT_CANCEL_PAIR",
        ),
        "UNKNOWN_OPERATOR",
    )
    atoms = state.atoms
    n = len(atoms)
    bounds = state.boundaries
    events = []
    if op == "SPLIT":
        k = args["position"]
        require(type(k) is int and 0 <= k <= n)
        return (
            SymbolicState(atoms[:k], tuple(b for b in bounds if b[0] <= k)),
            SymbolicState(
                atoms[k:], tuple((p - k, t, s) for p, t, s in bounds if p >= k)
            ),
        ), events
    if op == "CONCAT":
        require(other is not None)
        return (
            SymbolicState(
                atoms + other.atoms,
                tuple(
                    sorted(
                        set(
                            bounds
                            + tuple((p + n, t, s) for p, t, s in other.boundaries)
                        )
                    )
                ),
            ),
        ), events
    if op in ("RENAME", "SUBSTITUTE"):
        mapping = args["mapping"]
        scope = args.get("scope", "global")
        require(scope in ("local", "global"))
        require(
            set(mapping) <= set(state.tokens)
            and all(isinstance(v, str) and v for v in mapping.values())
        )
        selected = set(range(n))
        if scope == "local":
            record = args.get("record")
            require(record is not None, "LOCAL_SCOPE_RECORD_REQUIRED")
            starts = [
                p for p, k, i in bounds if k == "record_start" and i == str(record)
            ]
            ends = [p for p, k, i in bounds if k == "record_end" and i == str(record)]
            require(len(starts) == len(ends) == 1, "INVALID_LOCAL_SCOPE")
            selected = set(range(starts[0], ends[0]))
        domain = {atoms[i].token for i in selected}
        require(set(mapping) <= domain, "MAPPING_OUTSIDE_SCOPE")
        if op == "RENAME":
            require(
                len({mapping.get(t, t) for t in domain}) == len(domain),
                "RENAME_NOT_BIJECTIVE",
            )
        out = tuple(
            Atom(mapping.get(a.token, a.token) if i in selected else a.token, a.spans)
            for i, a in enumerate(atoms)
        )
        return (SymbolicState(out, bounds),), events
    if op == "REVERSE":
        return (
            SymbolicState(
                tuple(reversed(atoms)),
                tuple(sorted((n - p, t, s) for p, t, s in bounds)),
            ),
        ), events
    require(set(state.tokens) <= {"S", "P"}, "SP_DOMAIN_REQUIRED")
    if op == "SP_INV":
        return (
            SymbolicState(
                tuple(Atom("P" if a.token == "S" else "S", a.spans) for a in atoms),
                bounds,
            ),
        ), events
    if op == "INSERT_CANCEL_PAIR":
        k = args["position"]
        kind = args["kind"]
        require(type(k) is int and 0 <= k <= n and kind in ("SP", "PS"))
        generated = tuple(Atom(t, ()) for t in kind)
        return (
            SymbolicState(
                atoms[:k] + generated + atoms[k:],
                tuple((p + (2 if p > k else 0), t, s) for p, t, s in bounds),
            ),
        ), events
    if op == "REDUCE_SP":
        reduced, events = reduce_sp(state.tokens)
        current = list(atoms)
        positions = list(range(n))
        for event in events:
            k = event["positions"][0]
            del current[k : k + 2]
            del positions[k : k + 2]
        newbounds = tuple(
            sorted(set((sum(i < p for i in positions), t, s) for p, t, s in bounds))
        )
        return (SymbolicState(tuple(current), newbounds),), events
    raise AssuranceError("UNKNOWN_OPERATOR")
