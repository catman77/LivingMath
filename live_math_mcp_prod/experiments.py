"""Executable narrow validations: histories, counterexample, and CA rule-as-data."""
from itertools import product
from core import Laboratory, Evidence
import json, argparse

# Task A: initial equality by total; derive discriminating observation by
# evaluating all available traces, NOT selecting a predefined threshold.
def arith_interpreter(item, lens):
    if lens=='sum':
        return sum(item),Evidence('proof','Sum by integer addition',{'history':item},True)
    if lens=='prefixes':
        acc=0; out=[]
        for a in item: acc+=a; out.append(acc)
        return tuple(out),Evidence('experiment','Deterministic execution trace',out,True)
    if lens=='distinct_from':
        left,right=item
        a,_=arith_interpreter(left,'prefixes'); b,_=arith_interpreter(right,'prefixes')
        differences=sorted(set(a).symmetric_difference(b))
        if not differences: return None,Evidence('experiment','No distinguishing visited value',{},True)
        threshold=differences[0]
        ra=next((v for v in a if v==threshold),sum(left))
        rb=next((v for v in b if v==threshold),sum(right))
        return {'threshold':threshold,'observations':(ra,rb)},Evidence('counterexample',
          'Equality of totals does not imply equality under stop-at-visited-value observation',
          {'lhs':left,'rhs':right,'threshold':threshold,'results':(ra,rb)},ra!=rb)
    raise ValueError(lens)

def arithmetic():
    lab=Laboratory(arith_interpreter)
    histories=[p for n in range(1,5) for p in product((1,2),repeat=n)]
    groups={}
    for h in histories: groups.setdefault(sum(h),[]).append(h)
    witness=None
    for total in sorted(groups):
        for a in groups[total]:
            for b in groups[total]:
                if len(a)!=len(b) or a==b: continue
                lab.attend((a,b),'same numeric result; test contextual equivalence')
                result,e=lab.interpret('distinct_from')
                if e.verified and result is not None:
                    witness=e; break
            if witness: break
        if witness: break
    if witness is None: raise AssertionError('No witness')
    return lab,{'histories':len(histories),'numeric_classes':len(groups),'witness':witness.witness}

# Task B: rule table entirely read from CA ring; no learned policy and no
# preference disguised as fundamental law. Enumerate each focus and check
# whether it changes the continuation.
def read_rule(x,p,n=8):
    return sum(((x>>((p+i)%n))&1)<<(7-i) for i in range(8))
def step(x,p,n=8):
    rule=read_rule(x,p,n)
    y=0
    for i in range(n):
        left=(x>>((i-1)%n))&1; mid=(x>>i)&1; right=(x>>((i+1)%n))&1
        idx=4*left+2*mid+right
        y|=((rule>>idx)&1)<<i
    return y

def boa_interpreter(item,lens):
    x,n=item
    if lens=='possible_next':
        results={p:step(x,p,n) for p in range(n)}
        return results,Evidence('experiment','Exhaustive one-step counterfactuals',results,True)
    if lens=='invariant_full_rotation':
        # (x,p) equivalent to cyclic rotation of both body and head
        def rot(v,k):return ((v<<k)|(v>>(n-k)))&((1<<n)-1) if k else v
        failed=[]
        for p in range(n):
            for k in range(n):
                if step(rot(x,k),(p+k)%n,n)!=rot(step(x,p,n),k): failed.append((p,k))
        return {'equivariant':not failed},Evidence('experiment','Rotation equivariance test',{'failures':failed},not failed)
    raise ValueError(lens)

def boa():
    lab=Laboratory(boa_interpreter)
    distinct=[]; lethal=[]
    for x in range(1,255):
        lab.attend((x,8),'test how moving attention changes available continuation')
        result,e=lab.interpret('possible_next')
        choices=set(result.values())
        if len(choices)>1: distinct.append(x)
        if any(y in (0,255) for y in choices) and any(y not in (0,255) for y in choices): lethal.append(x)
    # A rotation covariance check is a check, not a postulated theorem
    lab.attend((0x66,8),'test compatibility of interpretation with symmetry')
    rot,e=lab.interpret('invariant_full_rotation')
    return lab,{'attention_changes_next_count':len(distinct),'mixed_fate_count':len(lethal),'rotation_check_0x66':rot}

# Research boundary: only projects with a verifier/data adapter can claim
# experimental outcome. RH and FTL are explicitly blocked until evidence.
def project_gate(project):
    if project=='RH': return {'status':'UNTESTED','needed':'formal theorem statement, assumptions, proof object and independent checker'}
    if project=='Soft_FTL': return {'status':'UNTESTED','needed':'timestamped paired source/receiver observations, isolation protocol, shuffled/blinded controls'}
    raise ValueError(project)

def run(output):
    from pathlib import Path
    path=Path(output);path.mkdir(exist_ok=True,parents=True)
    la,a=arithmetic();lb,b=boa()
    la.export(path/'arithmetic_trace.json');lb.export(path/'boa_trace.json')
    report={'arithmetic':a,'boa':b,'RH':project_gate('RH'),'Soft_FTL':project_gate('Soft_FTL')}
    (path/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='results'); args=parser.parse_args()
    print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
