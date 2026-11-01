"""Common direct/A0 prompt; source review and bounded ordinary repair, no target Q."""
import json

from .prompts013 import CRITIC as BASE_CRITIC
from .prompts013 import PROPOSE as BASE

PROPOSE=BASE+'''
Version014. First supply readable_model: a complete, self-contained human-readable
formalization with entities, relations, live mathematical formulas, attribution,
negation, time, scope, unknowns and losses. Never replace this account with status
labels. This is the common direct A/B/B+/C baseline, not a desired conclusion.
Then give TWO substantively competing source readings where justified, otherwise
one with explicit uncertainty. Keep at most3 readings, at most4 states and4
relations per reading. Preserve every important relation in the readable account
even if it cannot be represented by this bounded typed graph.
Contrasts name a concrete source-level observable, opposite TRUE/FALSE/UNKNOWN
forecasts under each reading, the actual differing assumption, exact evidence,
and what additional evidence could settle it. Do not manufacture alternatives
by renaming variables. Do not identify EQUALITY with RETURN. No preselected
question, desired answer or checker result is supplied.
An observation's time means the addressed observation/record session, not an
invented physical configuration time. A stated common session can bind record
samples using its exact quote. A and B may be distinct samples. Do not infer
one sample's identity from equality of named features. Preserve known literal
values, negative values, and reported same/different claims separately.
'''
CRITIC=BASE_CRITIC+'''
Version014. Re-read full clauses, not isolated matching words. Audit the entire
readable account and typed alternatives. Check whether each contrast is a real
source distinction, a disputed interpretation, or unsupported. You do not see
any selected question, target model, proof, gold or desired verdict. A source
quote may be exact while the proposed meaning is wrong: label it accordingly.
List only concrete addressed mismatches in issues, including an omitted record
session when it is actually stated. Ordinary source critique is shared equally
with B+ and C; it is fallible, not external semantic validation. Do not approve
speculative assumptions as source facts and do not force a substantive family.
'''

def request(role: str, packet: dict, proposals: dict | None = None, feedback: dict | None = None) -> str:
    data: dict={'task':CRITIC if role=='critic014' else PROPOSE,'source_window':packet}
    if role=='critic014':data['source_candidates']=proposals
    elif role=='repair014':
        data.update(previous_candidates=proposals,addressed_source_issues=feedback,
            repair_instruction='One ordinary source-only repair of these issues. Preserve all other content and IDs. Record losses. No selected question or desired verdict is supplied.')
    return json.dumps(data,ensure_ascii=False,separators=(',',':'))
