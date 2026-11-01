"""Blind source declarations. No correct pair, interpretation, feature path or optimal test."""
from itertools import product


def declarations(namespace: str) -> list[dict]:
    parameters = [
        {'algebra':'boolean_relations','initial':[0,[[1,0],[0,1]]],'generators':[[[1,1],[0,1]],[[0,1],[1,0]]]},
        {'algebra':'annihilation','initial':[0,[0,1,0]],'capacity':5},
        {'algebra':'coloured_stack','initial':[0,[]],'capacity':2},
        {'algebra':'quadratic_residues','initial':[0,2],'modulus':11,'offsets':[1,3],'read_moduli':[3,5]},
    ]
    worlds=[]
    for index,p in enumerate(parameters):
        labels=['u'+str(i) for i in range(5 if index in (1,2) else 4)];p['actions']=labels
        words=[[]]+[[a] for a in labels[:2]]+[list(w) for w in product(labels[:2],repeat=2)]
        tests=[list(w) for size in (1,2) for w in product(labels,repeat=size)]
        worlds.append({'name':'source'+str(index),'project':'LM_QA_CONCEPT012_'+namespace+'_'+str(index),
            'scope':'QA012/'+namespace+'/'+str(index),'parameters':p,'histories':{'h'+str(i):word for i,word in enumerate(words)},
            'tests':[{'id':'q'+str(i),'ordinal':i,'suffix':w,'cost':len(w)-1} for i,w in enumerate(tests)],
            'observer':{'projection':'primary','mod':None},'version':1,
            'prior_description':'Equality of the current primary observation is only a local predictive hypothesis.',
            'independent_branch':{'word':[],'scope':'independent'}})
    return worlds
