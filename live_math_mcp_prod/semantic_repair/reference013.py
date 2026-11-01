"""Independent stdlib finite enumeration: no compiler, DAV or primary inference imports."""
from itertools import product


def enumerate_reference(plan, limit):
    variables = plan['variables']; assignments = []
    def permitted(key, x):
        for c in plan['constraints']:
            if c['key'] == key and ((c['negative'] and x == c['value']) or (not c['negative'] and x != c['value'])):
                return False
        return True
    choices = [[v for v in plan['domains'][key] if permitted(key,v)] for key in variables]
    count=1
    for row in choices: count*=len(row)
    if count>limit:return {'status':'RESOURCE_BOUND','world_count':count,'rows':[]}
    for row in product(*choices):
        world=dict(zip(variables,row))
        truth=[]
        for projection in plan['projections']:
            truth.append(bool(projection) and all(world[x]==world[y] for x,y in projection))
        assignments.append({'world':world,'truth':truth})
    return {'status':'COMPLETE','world_count':count,'rows':assignments}
