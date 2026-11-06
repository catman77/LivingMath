"""Second, independently implemented replay/checker for two *proposed* bounded ASTs.
It never calls typed_ast_reference.evaluate(). It rejects unsupported operations, invalid
structural steps and truncated traces. Not a general theorem prover.
"""
from __future__ import annotations

class TraceReject(ValueError): pass


def execute_checked(ast:dict, sequence:tuple[str,...], trace:list[dict], budget:int)->bool:
    if len(sequence)>budget:raise TraceReject('OUT_OF_SCOPE')
    if not isinstance(trace,list):raise TraceReject('TRACE_NOT_LIST')
    op=ast.get('composition')
    cursor=0
    def expect(name):
        nonlocal cursor
        if cursor>=len(trace):raise TraceReject(f'MISSING_{name}')
        record=trace[cursor];cursor+=1
        if record.get('op')!=name:raise TraceReject(f'OPERATOR_ORDER_OR_NAME_{name}')
        return record
    def check(condition,kind):
        if not condition:raise TraceReject(kind)
    if op=='iterate_on_inner_fragment':
        check(ast.get('trim_left')==1 and ast.get('trim_right')==1,'INVALID_TRIM')
        check(ast.get('fragment_operations')==['SPLIT','SPLIT'],'INVALID_FRAGMENT_PROGRAM')
        cond=ast.get('relation',{})
        check(cond.get('composition')=='aligned_token_equality' and cond.get('expected_equal') is True
              and cond.get('offset')==0 and cond.get('base_max_tokens')==1
              and cond.get('left_operations')==['SPLIT']
              and cond.get('right_operations')==['REVERSE','SPLIT'],'INVALID_RELATION_PROGRAM')
        seq=list(sequence)
        while len(seq)>1:
            r=expect('REVERSE')
            check(r.get('input')==seq and r.get('output')==seq[::-1],'REVERSE_MISMATCH')
            l=expect('SPLIT')
            check(l.get('input')==seq and l.get('position')==1 and l.get('outputs')==[seq[:1],seq[1:]],'FIRST_SPLIT_MISMATCH')
            rl=expect('SPLIT')
            check(rl.get('input')==seq[::-1] and rl.get('position')==1 and rl.get('outputs')==[seq[-1:],seq[-2::-1]],'REVERSED_SPLIT_MISMATCH')
            eq=expect('literal_word_equality')
            ans=(seq[0]==seq[-1])
            check(eq.get('left')==seq[:1] and eq.get('right')==seq[-1:] and eq.get('equal') is ans,'EQUALITY_MISMATCH')
            if not ans:
                check(cursor==len(trace),'EXTRA_STEPS_AFTER_FALSE')
                return False
            inner=expect('SPLIT')
            check(inner.get('input')==seq[1:] and inner.get('position')==len(seq)-2
                 and inner.get('outputs')==[seq[1:-1],seq[-1:]],'SECOND_SPLIT_MISMATCH')
            seq=seq[1:-1]
        check(cursor==len(trace),'TRAILING_STEPS')
        return True
    if op=='compare_fragments':
        cut=ast.get('cut',{})
        check(cut.get('operator')=='SPLIT' and cut.get('position')=='MIDPOINT_EXACT_EVEN'
            and ast.get('comparison')=='literal_word_equality' and ast.get('expected_equal') is True,
            'INVALID_COMPARE_PROGRAM')
        if len(sequence)%2:
            z=expect('CHECK_EVEN_LENGTH')
            check(z.get('result') is False,'ODD_GUARD_MISMATCH')
            check(cursor==len(trace),'TRAILING_STEPS')
            return False
        mid=len(sequence)//2
        a,b=list(sequence[:mid]),list(sequence[mid:])
        step=expect('SPLIT')
        check(step.get('input')==list(sequence) and step.get('position')==mid and step.get('outputs')==[a,b],
          'MIDPOINT_SPLIT_MISMATCH')
        equal=(a==b)
        step=expect('literal_word_equality')
        check(step.get('left')==a and step.get('right')==b and step.get('equal') is equal,'HALVES_EQUALITY_MISMATCH')
        check(cursor==len(trace),'TRAILING_STEPS')
        return equal
    raise TraceReject('UNKNOWN_COMPOSITION')
