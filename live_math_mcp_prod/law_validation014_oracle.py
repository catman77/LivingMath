"""Independent evaluation code. Absent from the engine's filesystem allowance."""


def replay(declaration,word):
    value=list(declaration['initial']);steps=[]
    for number,a in enumerate(word,1):
        old=value[:];kind=declaration['algebra']
        allowed=a in range(declaration['arity']) and (kind!='stack' or (len(value)<4 if a!=2 else len(value)>0))
        if not allowed:return {'defined':False,'observation':None,'admissibility':[True]*len(steps)+[False]},None,steps
        if kind=='affine':
            value=[old[0]+old[1],old[1]+1] if a==0 else [old[0],sum(old)+1]
        elif kind=='permutation':
            if a==1 and declaration['clock_period'] and number%declaration['clock_period']==0:value=[old[2],old[1],old[0],old[3]]
            elif a==0:value=[old[0],old[2],old[1],old[3]]
            else:value=[old[(i+1)%4] for i in range(4)]
        elif kind=='stack':
            value=old[:-1] if a==2 else old+[a]
        elif kind=='latch':value=[old[1],old[1]] if a==0 else [old[0],1-old[1]]
        else:raise ValueError('ORACLE_SOURCE')
        steps.append({'before':old,'action':a,'after':value[:]})
    observation=(value[-1] if value else 0) if declaration['algebra']=='stack' else value[0]//2
    return {'defined':True,'observation':observation,'admissibility':[True]*len(word)},value,steps


def rank_probes(domain,seen,covered_pairs):
    eligible=[p for p in domain if tuple(p['word']) not in seen]
    def key(p):
        pairs=set(zip(p['word'],p['word'][1:]));new=len(pairs-set(covered_pairs))
        return (-new,-len(p['word']),p['cost'],p['ordinal'])
    return [p['id'] for p in sorted(eligible,key=key)]
