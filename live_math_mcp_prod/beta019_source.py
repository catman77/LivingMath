"""Reviewed adapter to the original automata-lib9.2.0 public NFA example.

No remote code/path input. Native transitions use the installed upstream NFA;
forecast guards/observer never execute a transition. Coordinates are a declared
injective encoding of source configurations, not a new source operation.
"""
from collections import deque
from dataclasses import dataclass
import hashlib
import importlib.util
from importlib.metadata import version
import json
from pathlib import Path

from normalizer import digest
from operational013_native import Ledger

ADAPTER = 'automata-nfa019/v1'
COMMIT = '04dc1947315f322825991b5dc637604567703c9c'
OBJECT = {'states': ['q0', 'q1', 'q2'], 'input_symbols': ['a', 'b'],
    'transitions': {'q0': {'a': ['q1']}, 'q1': {'': ['q2'], 'a': ['q1']}, 'q2': {'b': ['q0']}},
    'initial_state': 'q0', 'final_states': ['q1']}
# Lexicographic configuration order, fixed before any hypothesis/outcome trial.
CODEBOOK = [[], ['q0'], ['q1', 'q2']]
OBSERVER = {'projection': 'primary', 'mod': None}


def package_hashes() -> dict:
    if version('automata-lib') != '9.2.0':
        raise ValueError('019_UNREVIEWED_PACKAGE_VERSION')
    directory = Path(next(iter(importlib.util.find_spec('automata').submodule_search_locations)))
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.rglob('*.py'))}


def definition_sha() -> str:
    return digest({'protocol': ADAPTER, 'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'package_sources': package_hashes(), 'object': OBJECT, 'codebook': CODEBOOK, 'upstream_commit': COMMIT})


def declaration() -> dict:
    raw = Path(__file__).with_name('external019')
    registration = json.loads((raw / 'registration.json').read_text())
    for name, entry in registration['files'].items():
        if hashlib.sha256((raw / name).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('019_RAW_SOURCE_IDENTITY_DRIFT:' + name)
    if json.loads((raw / 'nfa.json').read_text()) != OBJECT:
        raise ValueError('019_SOURCE_OBJECT_REPLACEMENT')
    expected = registration['files']['nfa.py.txt']['sha256']
    if package_hashes()['fa/nfa.py'] != expected:
        raise ValueError('019_WHEEL_UPSTREAM_CODE_MISMATCH')
    return {'algebra': ADAPTER, 'arity': 2, 'initial': encode(['q0']), 'guard_width': 3,
        'source_object': OBJECT, 'codebook': CODEBOOK, 'upstream_commit': COMMIT,
        'raw_object_sha256': registration['files']['nfa.json']['sha256'],
        'discrimination_histories': [[], [1]]}


def encode(configuration) -> list[int]:
    value = sorted(configuration)
    if value not in CODEBOOK:
        raise ValueError('019_CONFIGURATION_OUTSIDE_DECLARED_IMAGE')
    return [2 if value == state else 0 for state in CODEBOOK]


def decode(image) -> list[str]:
    if not isinstance(image, list) or len(image) != 3 or image.count(2) != 1 or any(type(x) is not int or x not in (0, 2) for x in image):
        raise ValueError('019_INVALID_CONFIGURATION_IMAGE')
    return CODEBOOK[image.index(2)]


def native_trace(word: list[int]) -> list[list[str]]:
    """Actual independently distributed NFA implementation, not the forecast."""
    from automata.fa.nfa import NFA
    from automata.base.exceptions import RejectionException
    if len(word) > 7 or any(type(a) is not int or a not in (0, 1) for a in word):
        raise ValueError('019_NATIVE_WORD_BOUND')
    data = OBJECT
    native = NFA(states=set(data['states']), input_symbols=set(data['input_symbols']),
        transitions={q: {a: set(states) for a, states in t.items()} for q, t in data['transitions'].items()},
        initial_state=data['initial_state'], final_states=set(data['final_states']))
    iterator = native.read_input_stepwise(''.join(data['input_symbols'][a] for a in word))
    states = []
    try:
        for state in iterator:
            states.append(sorted(state))
    except RejectionException:
        # Rejection is a normal value of the mathematical observer, not ERROR.
        pass
    if len(states) != len(word) + 1:
        raise ValueError('019_INCOMPLETE_NATIVE_TRACE')
    return states


@dataclass(frozen=True)
class State:
    value: tuple
    history: tuple = ()


class Port:
    def __init__(self, declared, ledger=None):
        if declared.get('algebra') != ADAPTER or declared.get('source_object') != OBJECT or declared.get('codebook') != CODEBOOK:
            raise ValueError('019_UNSUPPORTED_SOURCE_DEFINITION')
        self.declaration, self.ledger = declared, ledger or Ledger(256)
        self.trace, self.counts = self.ledger.rows, {}

    def charge(self, operation, **fields):
        self.ledger.charge(operation, **fields)
        self.counts[operation] = self.counts.get(operation, 0) + 1

    def load(self, word):
        self.charge('load', word=word)
        return State(tuple(encode(native_trace(list(word))[-1])), tuple(word))

    def admissible(self, state, action):
        self.charge('A', action=action)
        return type(action) is int and action in (0, 1)

    def extend(self, state, action):
        if not self.admissible(state, action):
            raise ValueError('019_UNSUPPORTED_OPERATION')
        self.charge('E', word=list(state.history), action=action)
        word = list(state.history) + [action]
        return State(tuple(encode(native_trace(word)[-1])), tuple(word))

    def inspect(self, state, opaque=False):
        self.charge('inspect', word=list(state.history))
        return None if opaque else list(state.value)

    def guard_image(self, image, action):
        self.charge('G', action=action)
        try:
            decode(image)
            return type(action) is int and action in (0, 1)
        except ValueError:
            return False

    def within_guard(self, image):
        self.charge('G_terminal', image=image)
        try:
            decode(image)
            return True
        except ValueError:
            return False

    def observe_image(self, image, observer):
        self.charge('O', image=image)
        if observer != OBSERVER:
            raise ValueError('OBSERVER_ALIGNMENT_REQUIRED')
        return int(bool(set(decode(image)) & set(OBJECT['final_states'])))

    def observe(self, state, observer):
        return self.observe_image(list(state.value), observer)


def acquisition(declared) -> dict:
    """BFS of the original reachable configurations, without outcome tuning."""
    port = Port(declared)
    root = port.load([])
    frontier, seen, transitions, words = deque([root]), set(), [], []
    while frontier:
        state = frontier.popleft()
        if state.value in seen:
            continue
        seen.add(state.value)
        for action in range(2):
            following = port.extend(state, action)
            transitions.append({'history': list(state.history), 'action': action,
                'before': list(state.value), 'after': list(following.value)})
            words.append(list(following.history))
            frontier.append(following)
    if {tuple(encode(c)) for c in CODEBOOK} != seen:
        raise ValueError('019_FROZEN_CODEBOOK_NOT_SOURCE_CLOSED')
    return {'origin': list(root.value), 'transitions': transitions, 'executed_words': words,
        'actual_native_calls': port.counts, 'quality': 'UPSTREAM_NFA_COMPUTATION', 'proof_status': 'unverified'}


def calculate(declared, target, suffix, observer, mode):
    if mode not in ('exact', 'withheld_sensor', 'instrument_error') or len(target) > 3 or not 1 <= len(suffix) <= 4:
        raise ValueError('019_INSTRUMENT_OR_WORD_BOUND')
    if mode == 'instrument_error':
        return {'observed': {'defined': False, 'observation': None, 'admissibility': []}, 'coordinate': [],
            'trace': [], 'quality': 'NO_OBSERVATION_INSTRUMENT_ERROR', 'native_costs': {}}
    port = Port(declared)
    state = port.load(target)
    flags = []
    for action in suffix:
        flags.append(port.guard_image(list(state.value), action))
        if not flags[-1]:
            raise ValueError('019_ACTUAL_GUARD_DENIED')
        state = port.extend(state, action)
    observation = port.observe(state, observer)
    return {'observed': {'defined': mode == 'exact', 'observation': observation if mode == 'exact' else None, 'admissibility': flags},
        'coordinate': list(state.value) if mode == 'exact' else [], 'trace': port.trace,
        'quality': 'COMPUTABLE_CHECKED' if mode == 'exact' else 'DECLARED_SENSOR_WITHHELD', 'native_costs': port.ledger.summary()}
