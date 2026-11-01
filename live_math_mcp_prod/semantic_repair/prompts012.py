"""Source-only012 task, identical for initial A/B/C and independent of finite Q."""
import json

PROPOSE = '''Extract at most three alternative bounded semantic readings from the
addressed source, each at most eight states and twelve relations. Cite exact
substrings at supplied span refs. This is an interpretive hypothesis, not proof.
No target query, expected outcome, withheld evidence, or hidden labels are given.

Preserve the difference between source narration, a directly stated proposition,
and a proposition ATTRIBUTED to a speaker. A quoted observer asserting p is NOT
an assertion of p as a world fact. A speaker denying p does not make global not-p.
Record source_claim.mode, speaker, stance, connective and exact speaker evidence.
Keep participant/referent separate from narrator/speaker. Use UNKNOWN explicitly.
Treat OR and AND and SOME versus ALL as different source distinctions.
Classify each state level: WORLD_STATE for a symbolic scene/configuration,
SOURCE_EVENT for an utterance/text occurrence, OBSERVATION_RECORD for a record
of a perspective, UNKNOWN if uncertain. This never identifies a physical world.
Speech-event nodes must not be executed as changes of a world configuration.

For observations name a source-grounded observer profile with owner, criterion,
feature vocabulary and samples at particular source states. A sample value null
is unknown, not false/absent. Omitted feature values are unknown. Select only
coordinates actually supported by addressed evidence; do not invent an observer
or a feature value to obtain equality. Distinct observers may use incompatible
criteria without either becoming the world truth. Partial equality cannot imply
identity of complete states. Preserve different word/feature orders separately.

Use TRANSITION only for a described change; SEQUENCE/ORDER may describe text
presentation without causation. REPEAT/EQUIVALENT_O/NEGATED/IDENTICAL/SIMILAR_O
are meaningful meta relations even when no command is executable. A repeat does
not license a backward transition. Do not add a positive edge to rescue a model.
For a direct/narrated change that can conditionally be encoded as a command, add
CONDITIONAL_EXECUTABLE_CHANGE to interpretation_assumptions. Do not give that
assumption to attributed/quoted propositions, mere order, similarity or negation.
PRESCRIBED remains an instruction, not evidence of performance.

Retain useful partial readings and list concrete unresolved scope/provenance.
Source states are symbolic roles; identical names alone do not prove identity.
Choose initial_state_ids only as an explicit conditional source reading, citing
states already declared. An empty initial list means no source-attested initial
condition; the finite encoding may make a labelled local choice, not a source fact.
'''

CRITIC = '''Independently reread the addressed source and audit every candidate.
No target model/proof/query or desired answer is supplied. Assess all ten named
dimensions exactly once: participant, referent, predicate, quantifier, polarity,
tense, modal, scope, text_order_vs_event_order, projection. Separately check
attribution and observer/mask scope. Report conditional HYPOTHESIS, CONFLICT,
UNSUPPORTED or UNKNOWN, never source verified. Missing observations stay unknown.
An attributed assertion can be source-supported as speech while its content is
not established. Check speaker citations and do not flatten reported disagreement
into global contradiction. Only a source-supported direct/narrated change may
support executable_assumption_supported; quotation/meta/negative/order alone
never does. Formal model derivation cannot improve this source assessment.
Preserve all disagreements and alternatives and exact distinguishing evidence.
'''


def request(role: str, packet: dict, proposals=None, feedback=None) -> str:
    data = {'task': CRITIC if role == 'critic012' else PROPOSE, 'source_window': packet}
    if role == 'critic012':
        data['source_candidates'] = proposals
    elif role == 'neutral_repair012':
        data['previous_candidates'] = proposals
        data['neutral_executor_feedback'] = feedback
    elif feedback is not None:
        data['source_view_obligations'] = feedback
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))
