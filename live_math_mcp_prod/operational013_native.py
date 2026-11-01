"""013 native source implementations. No fitted transport laws or oracle data."""
from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path


def definition_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@dataclass(frozen=True)
class State:
    payload: tuple
    history: tuple = ()


class Ledger:
    def __init__(self, limit=20000):
        self.limit, self.stage = limit, 'discovery'
        self.rows, self.counts = [], Counter()

    def charge(self, operation, **fields):
        if sum(self.counts.values()) >= self.limit:
            raise ValueError('NATIVE_QUERY_BUDGET')
        self.counts[(self.stage, operation)] += 1
        self.rows.append({'order':len(self.rows), 'stage':self.stage, 'operation':operation, **fields})

    def summary(self):
        result = {}
        for (stage, operation), count in self.counts.items():
            result.setdefault(stage, {})[operation] = count
        return result


class Port:
    """Opaque native states; inspect is a declared source operation, not hidden access."""
    def __init__(self, declaration, ledger=None):
        self.declaration = declaration
        self.ledger = ledger or Ledger()
        self.trace = self.ledger.rows
        self.counts = {}
        self.actions = list(range(declaration['arity']))

    def _charge(self, op, **fields):
        self.ledger.charge(op, **fields)
        self.counts[op] = self.counts.get(op, 0) + 1

    def load(self, word):
        self._charge('load', word=word)
        state = State(tuple(self.declaration['initial']))
        for action in word:
            if not self.admissible(state, action):
                raise ValueError('INADMISSIBLE_HISTORY')
            state = self.extend(state, action)
        return state

    def admissible(self, state, action):
        self._charge('A', word=list(state.history), action=action)
        if action not in self.actions:
            return False
        if self.declaration['algebra'] == 'stack':
            return len(state.payload) < 4 if action < 2 else bool(state.payload)
        return True

    def extend(self, state, action):
        self._charge('E', word=list(state.history), action=action)
        p, kind = state.payload, self.declaration['algebra']
        if kind == 'affine':
            x, y = p
            value = (x+y, y+1) if action == 0 else (x, y+x+1)
        elif kind == 'permutation':
            value = (p[0],p[2],p[1],p[3]) if action == 0 else p[1:]+p[:1]
        elif kind == 'stack':
            if (action < 2 and len(p) >= 4) or (action == 2 and not p):
                raise ValueError('NATIVE_STACK_GUARD')
            value = p+(action,) if action < 2 else p[:-1]
        elif kind == 'insufficient':
            x, y = p
            value = (y,y) if action == 0 else (x,1-y)
        elif kind == 'opaque':
            x, y = p
            value = ((x*x+3*y+action+1)%101, (x+7*y+action)%103)
        else:
            raise ValueError('UNREGISTERED_SOURCE')
        return State(tuple(value),state.history+(action,))

    def inspect(self, state):
        self._charge('inspect', word=list(state.history))
        kind = self.declaration['algebra']
        if kind == 'opaque':
            return None
        p = state.payload[:1] if kind == 'insufficient' else state.payload
        offset = self.declaration.get('presentation_offset',0)
        return [x+offset for x in p]

    def image_state(self, image):
        # Reification is valid only for complete native images. Negative sources refuse.
        if self.declaration['algebra'] in {'opaque','insufficient'}:
            raise ValueError('INSUFFICIENT_SOURCE_IMAGE')
        return State(tuple(image))

    def guard_image(self, image, action):
        return self.admissible(self.image_state(image),action)

    def observe_image(self, image, observer):
        return self.observe(self.image_state(image),observer)

    def observe(self, state, observer):
        self._charge('O', word=list(state.history), observer=observer)
        if observer != {'projection':'primary','mod':None}:
            raise ValueError('OBSERVER_ALIGNMENT_REQUIRED')
        p = state.payload
        if self.declaration['algebra'] == 'stack':
            return p[-1] if p else 0
        return p[0]//2
