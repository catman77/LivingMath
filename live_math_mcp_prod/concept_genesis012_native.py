"""Four finite source algebras; these functions perform source operations, not inference."""
from dataclasses import dataclass
import hashlib
import inspect
import time

from live_transfer006_primitives import Exhausted


@dataclass(frozen=True)
class State:
    value: tuple
    history: tuple
    origin: tuple = ()


def admissible(state: State, action: int, parameters: dict) -> bool:
    carrier = state.value[1]
    if parameters['algebra'] == 'coloured_stack':
        if action in (0, 1): return len(carrier) < parameters['capacity']
        if action in (2, 3): return bool(carrier) and carrier[-1] == action - 2
    if parameters['algebra'] == 'annihilation':
        if action in (0, 1): return len(carrier) < parameters['capacity']
        if action == 4: return bool(carrier)
    return True


def extend(state: State, action: int, parameters: dict) -> State:
    visible, carrier = state.value
    kind = parameters['algebra']
    if kind == 'boolean_relations':
        if action < 2:
            matrix = parameters['generators'][action]
            carrier = tuple(tuple(int(any(matrix[i][k] and carrier[k][j] for k in range(2)))
                                  for j in range(2)) for i in range(2))
        else: visible = carrier[0][1] if action == 2 else carrier[1][0]
    elif kind == 'annihilation':
        if action < 2:
            word = list(carrier) + [action]
            while True:
                at = next((i for i in range(len(word)-1) if word[i:i+2] in ([0,0], [0,1])), None)
                if at is None: break
                word[at:at+2] = [] if word[at:at+2] == [0,0] else [1]
            carrier = tuple(word)
        elif action == 2: visible = carrier[0] + 1 if carrier else 0
        elif action == 3: visible = len(carrier)
        else: carrier = carrier[1:]
    elif kind == 'coloured_stack':
        if action < 2: carrier = carrier + (action,)
        elif action < 4: carrier = carrier[:-1]
        else: visible = len(carrier)
    elif kind == 'quadratic_residues':
        if action < 2: carrier = (carrier * carrier + parameters['offsets'][action]) % parameters['modulus']
        else: visible = carrier % parameters['read_moduli'][action-2]
    else: raise ValueError('UNSUPPORTED_SOURCE_ALGEBRA')
    return State((visible, carrier), state.history + (action,), state.origin)


def observe(state: State, observer: dict) -> int:
    return state.value[0] if observer['mod'] is None else state.value[0] % observer['mod']


def definition_sha256() -> str:
    return hashlib.sha256(''.join(inspect.getsource(f) for f in (admissible, extend, observe)).encode()).hexdigest()


def freeze_value(value):
    return tuple(freeze_value(v) for v in value) if isinstance(value, list) else value


class Ledger:
    def __init__(self, limit: int = 4096, seconds: float = 5):
        self.limit, self.seconds, self.start = limit, seconds, time.perf_counter()
        self.stage = 'input'; self.counts = {'extend': 0, 'observe': 0, 'admissible': 0}
        self.trace = []; self.work = {}

    def charge(self, name: str, n: int = 1):
        key = self.stage + ':' + name; self.work[key] = self.work.get(key, 0) + n

    def call(self, operation: str, state: State, argument, fn):
        if sum(self.counts.values()) >= self.limit or time.perf_counter()-self.start > self.seconds:
            raise Exhausted('SOURCE_OPERATION_OR_TIME_BOUND')
        self.counts[operation] += 1; result = fn()
        self.trace.append({'stage': self.stage, 'operation': operation,
            'source': {'value': state.value, 'history_ordinals': state.history, 'event_refs': state.origin},
            'argument': argument, 'result': {'value': result.value, 'history_ordinals': result.history} if isinstance(result, State) else result})
        return result

    def summary(self) -> dict:
        return {'native_calls': dict(self.counts), 'total_native_calls': sum(self.counts.values()),
                'structural_work': self.work, 'trace_events': len(self.trace)}


class Port:
    def __init__(self, parameters: dict, words: dict, ledger: Ledger):
        self.parameters, self.words, self.ledger = parameters, words, ledger
        self.actions = parameters['actions']

    @property
    def counts(self): return self.ledger.counts
    @property
    def trace(self): return self.ledger.trace

    def admissible(self, state: State, action: str) -> bool:
        return self.ledger.call('admissible', state, self.actions.index(action), lambda: admissible(state, self.actions.index(action), self.parameters))

    def extend(self, state: State, action: str) -> State:
        return self.ledger.call('extend', state, self.actions.index(action), lambda: extend(state, self.actions.index(action), self.parameters))

    def observe(self, state: State, observer: dict):
        return self.ledger.call('observe', state, observer, lambda: observe(state, observer))

    def load(self, word: list[str]) -> State:
        self.ledger.charge('source_load')
        origins = tuple(sorted(ref for ref, candidate in self.words.items() if candidate == word))
        state = State(freeze_value(self.parameters['initial']), (), origins)
        for action in word:
            if not self.admissible(state, action): raise ValueError('INVALID_SOURCE_HISTORY')
            state = self.extend(state, action)
        return state
