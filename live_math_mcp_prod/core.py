"""Living-math MVP: two operations, explicit claims and witnesses.
No hidden reward or 'correct' lens lookup; detectors are swappable adapters.
"""
from dataclasses import dataclass, asdict
from typing import Callable, Any
import json

@dataclass(frozen=True)
class Evidence:
    kind: str  # proof, counterexample, experiment, interpretation
    statement: str
    witness: Any
    verified: bool

class Laboratory:
    def __init__(self, interpreter: Callable[[Any, str], tuple[Any, Evidence]]):
        self.interpreter=interpreter
        self.focus=None
        self.history=[]

    def attend(self, item: Any, reason: str):
        self.focus=item
        self.history.append({'operation':'attention','reason':reason,'item':repr(item)})

    def interpret(self, lens: str):
        if self.focus is None: raise ValueError('attention required')
        result, evidence=self.interpreter(self.focus,lens)
        self.history.append({'operation':'interpretation','lens':lens,'focus':repr(self.focus),
                             'result':repr(result),'evidence':asdict(evidence)})
        return result,evidence

    def export(self, file):
        with open(file,'w',encoding='utf8') as f: json.dump(self.history,f,ensure_ascii=False,indent=2)
