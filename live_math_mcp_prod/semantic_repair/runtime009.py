"""Fixture-free observation assembly and finite candidate planning for the controller."""
import copy

from davcore.ast import digest

from .search import enumerate_bindings


def assemble(observations: list[dict], project: str) -> dict:
    # General source views are competing readings, not successive truth edits.
    # A less decisive view must not erase a useful earlier conditional model.
    latest={(o['source_packet']['id'], o['observer']) if o['observer'].startswith(('general011', 'observer012'))
        else o['source_packet']['id']:o for o in observations}
    slices=[copy.deepcopy(s) for o in latest.values() for s in o['slices']]
    narrative=[s for s in slices if s['kind']=='TEXTUAL_PROGRESSION']
    if narrative:
        ps={p['id']:p for s in narrative for p in s['premises']}
        slices=[s for s in slices if s['kind']!='TEXTUAL_PROGRESSION']+[
            {**narrative[0],'premises':sorted(ps.values(),key=lambda p:p['realization']['source_order'])}]
    unique={digest([s['kind'],[p['id'] for p in s['premises']]]):s for s in slices}
    plans: list[dict]=[]
    losses: list[dict]=[]
    families: list[dict]=[]
    losses.extend(loss for o in latest.values() for loss in o.get('source_coverage_losses',[]))
    for s in unique.values():
        # Explicit local interfaces, never a purported global invariant.
        bound={'TEXTUAL_PROGRESSION':5,'GUARDED_TRANSFORMATION':2,'SIGNED_RESPONSE':3,'STATE_TRANSITION':12}[s['kind']]
        chunks=[s['premises'][i:i+bound] for i in range(0,len(s['premises']),bound)]
        if len(chunks)>1:
            losses.append({'reason':'LOCAL_SLICES_ONLY_INTERFACE_NOT_PROVED','source_refs':sorted({r for p in s['premises'] for r in p['source_refs']})})
        for chunk in chunks:
            if s['kind'] == 'STATE_TRANSITION' and not any(
                    p['realization']['transition']['version'] == 'source-transition012/1' or
                    p['realization']['transition']['relation_kind'] in {'TRANSITION', 'SEQUENCE', 'CONDITION'} for p in chunk):
                losses.append({'reason': 'SOURCE_ONLY_META_RELATIONS',
                    'source_refs': sorted({r for p in chunk for r in p['source_refs']})})
                continue
            family=enumerate_bindings(s['dimensions'],project=project)
            families.append({'kind':s['kind'],'premise_ids':[p['id'] for p in chunk],'family':family})
            if not family['bindings'] or family['truncated']:
                losses.append({'reason':'EMPTY_FAMILY' if not family['bindings'] else 'TRUNCATED_FAMILY','family':family});continue
            for binding in family['bindings']:
                plans.append({'premises':chunk,'binding':binding,'kind':s['kind'],
                    'slice_id':'slice_'+digest([p['id'] for p in chunk])[:24]})
    return {'plans':plans,'families':families,'losses':losses,
        'unparsed_refs':sorted({r for o in latest.values() for r in o['unparsed_refs']}),
        'analogy_boundaries':sorted({r for o in latest.values() for r in o['analogy_boundaries']})}
