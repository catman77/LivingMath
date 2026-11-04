"""Readable exact artifacts, escaped as JSON; statements keep their scope."""
from .core import canonical, identity
from .service import require

BOUNDARY = ('CHECKED_FINITE covers only the complete declared finite class/domain. '
            'SOURCE_ATTESTED covers exact source fields/projection, not physical truth. '
            'UNKNOWN/HOLD is not refutation. No model verification, native SUTI, formal kernel '
            'or permission for external actions is provided.')


def report(workspace):
    with workspace.locked():
        rows = workspace.history()
        require(bool(rows), 'PROJECT_NOT_FOUND')
        records = []
        for row in rows:
            if row['action'] != 'check':
                continue
            value = workspace.get(row['result']['check_ref'])
            submission = workspace.get(value['candidate_ref'])
            task = workspace.get(submission['task_ref'])['task']
            records.append({'check_ref': row['result']['check_ref'], 'status': value['status'],
                'reason_code': value['reason_code'], 'claim_kind': task['claim_kind'],
                'original_question': task['question'], 'original_submission': submission,
                'machine_term': (value.get('candidate') or {}).get('assertion', {}).get('machine_term'),
                'assumptions': task['assumptions'], 'scope': task['scope'],
                'source_refs': (value.get('candidate') or {}).get('source_refs', []),
                'decision': value['decision'], 'witnesses_and_countermodels': value['witnesses'],
                'binding_provenance': value.get('binding'), 'execution_permission': False})
        return {'project': workspace.project, **identity(), 'records': records,
                'journal_head': rows[-1]['hash'], 'boundary': BOUNDARY,
                'execution_permission': False}


def text_report(value):
    # Plain text avoids making untrusted source text active HTML/Markdown.
    return 'LivingMath × SUTI assurance report\n\n' + value['boundary'] + '\n\n' + canonical(value) + '\n'
