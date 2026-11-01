"""Auditable local metrics; unavailable paired or human scores stay null."""


def score(branches):
    ledgers = [x for branch in branches for x in branch['audit']['loss_ledger']]
    mandatory = [x for x in ledgers if x['must_preserve']]
    return {'mandatory_declarations': len(mandatory),
            'mandatory_preserved': sum(x['state'] == 'PRESERVED' for x in mandatory),
            'R_T_O': {section: {state: sum(x['section'] == section and x['state'] == state for x in ledgers)
                               for state in ('PRESERVED','NARROWED','LOST','UNKNOWN','REJECTED')}
                      for section in ('R','T','O')},
            'false_grants': sum(x['audit']['execution_permission']['allowed'] for x in branches),
            'false_verified': sum(x['audit']['proof_status'] == 'verified' for x in branches),
            'author_recognition_rate': None, 'blind_correctness_score': None,
            'paired_LLM_advantage': None, 'human_baseline': None,
            'claim_scope': 'Declared structure and finite local tests only; no human meaning score.'}
