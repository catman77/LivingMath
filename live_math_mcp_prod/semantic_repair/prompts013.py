"""Same initial source-only prompt for A/B/C; no requested theorem or label."""
import json

from .prompts012 import CRITIC as BASE_CRITIC
from .prompts012 import PROPOSE as BASE

PROPOSE=BASE+'''
Version013: preserve actual feature VALUES, not only words or a claim of equality.
Use status KNOWN only for an explicitly supplied value; EXPLICIT_NEGATIVE(v)
means not-v, not an invented alternative. UNKNOWN has value=null and no conflicts.
CONFLICT has value=null and at least two contradictory addressed value assertions.
Do not convert "same color" into red/red or "different mass" into numbers.
Record each sample's source-supported scope, time and referent binding, with
binding_evidence. Null is preferable to invented time/scope/referent. A shared
referent label is an interpretive source binding, not physical identity. Use
ATEMPORAL only for explicitly static mathematical definitions. Preserve ALL/SOME.
For a source speaker's comparison use comparison EQUALITY, RETURN or UNSPECIFIED.
reported_value TRUE/FALSE is the fully signed REPORTED content (include stance
and polarity once, not twice); it is not world truth. Supply comparison_scope
and comparison_time only if addressed. Do not force common meanings of "same"
and "return"; that can only be a separately labelled hypothetical assumption.
Retain separate observers even if their words look alike. Do not invent a causal
command from textual order or a return from repeated description.
'''
CRITIC=BASE_CRITIC+'''
Separately audit each observer profile in observations: exact explicit values,
negative versus unknown versus genuine conflicting assignments, temporal/scope
comparability and referent binding evidence. A bare reported equivalence does
not supply missing values. Source-support of conflicting reports is not a global
refutation. No target questions, model, proof, desired outcome or holdout labels
are supplied. Your review is fallible source critique, not external validation.
'''


def request(role,packet,proposals=None,feedback=None):
    data={'task':CRITIC if role=='critic013' else PROPOSE,'source_window':packet}
    if role=='critic013':data['source_candidates']=proposals
    elif role=='neutral_repair013':data.update(previous_candidates=proposals,neutral_executor_feedback=feedback)
    elif feedback is not None:data['source_view_obligations']=feedback
    return json.dumps(data,ensure_ascii=False,separators=(',',':'))
