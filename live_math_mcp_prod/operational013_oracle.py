"""Independent raw replay evaluator; never imported by the law generator."""


def replay(declaration, word):
    value = list(declaration['initial'])
    flags, steps = [], []
    for a in word:
        algebra = declaration['algebra']
        allowed = 0 <= a < declaration['arity']
        if algebra == 'stack':
            allowed &= (len(value)<4 if a!=2 else len(value)>0)
        flags.append(bool(allowed))
        if not allowed:
            return {'defined':False,'observation':None,'admissibility':flags}, steps
        old = value[:]
        if algebra == 'affine':
            if a == 0:
                value[0] += old[1]; value[1] += 1
            else:
                value[1] += old[0]+1
        elif algebra == 'permutation':
            if a == 0:
                value[1],value[2] = old[2],old[1]
            else:
                value = [old[(i+1)%4] for i in range(4)]
        elif algebra == 'stack':
            if a == 2:
                value.pop()
            else:
                value.append(a)
        elif algebra == 'insufficient':
            value = [old[1],old[1]] if a == 0 else [old[0],1-old[1]]
        elif algebra == 'opaque':
            value = [(old[0]**2+3*old[1]+a+1)%101,(old[0]+7*old[1]+a)%103]
        else:
            raise ValueError('ORACLE_UNREGISTERED_SOURCE')
        steps.append({'before':old,'action':a,'after':value[:]})
    observation = (value[-1] if value else 0) if declaration['algebra']=='stack' else value[0]//2
    return {'defined':True,'observation':observation,'admissibility':flags}, steps
