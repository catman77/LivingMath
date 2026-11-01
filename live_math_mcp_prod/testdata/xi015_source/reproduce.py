#!/usr/bin/env python3
"""Offline export of the current T49->T54 Xi source. Python standard library.

No reduction axioms are added. The point-value deletion is a labelled rejected
control, not a native SRT rewrite. All numerical output uses full 58-digit
outward-rounded intervals; symbolic expressions retain exact input bindings.
"""
import argparse
import hashlib
import json
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
from intervals import I, pi_interval, exp_i, P

M,N,U=256,4,2
TARGET='14.134725141734694'
SELECTED=(14,2)  # source cell and increasing Gauss-node index, both zero based
SOURCE_SHA='265b21e4baaa3c0f1488ee718a541b8ca710a5233666b095bc89afce1f84ba58'
INTERVAL_SHA='9a84ae1b1e9270fea0b8cd67480c7c4e2eca00aef4c1e22b6caa90dd8690cba9'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def zero():return (I(0),I(0))
def add(a,b):return (a[0]+b[0],a[1]+b[1])
def sub(a,b):return (a[0]-b[0],a[1]-b[1])
def scale(a,v):return (a[0]*v,a[1]*v)
def times_i(a):return (-a[1],a[0])
def cj(a):return {'re':a[0].json(),'im':a[1].json()}
def contains_zero(a):return all(v.lo<=0<=v.hi for v in a)
def maxnorm(a):return max(v.radius_bound() for v in a)
def sign(v):return 'POSITIVE' if v.lo>0 else 'NEGATIVE' if v.hi<0 else 'ZERO' if v.lo==v.hi==0 else 'UNRESOLVED'
def overlaps(a,b):return all(max(x.lo,y.lo)<=min(x.hi,y.hi) for x,y in zip(a,b))
def abs_lower(v):return min(v.lo.copy_abs(),v.hi.copy_abs()) if v.lo>0 or v.hi<0 else Decimal(0)
def dump(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')

def poly(x):return 6435*x**8-12012*x**6+6930*x**4-1260*x**2+35

def nodes():
    fixture=json.loads((ROOT/'vendor/ALGEBRAIC_NODES.json').read_text())
    out=[];previous=None
    for j,row in enumerate(fixture['nodes']):
        lo,hi=F(row['lo']),F(row['hi'])
        assert lo<hi and poly(lo)*poly(hi)<0
        assert previous is None or previous<lo
        previous=hi
        x=I(I.frac(lo).lo,I.frac(hi).hi)
        D=(51480*x**7-72072*x**5+27720*x**3-2520*x)/128
        w=2/((1-x*x)*D*D)
        assert w.lo>0
        out.append((x,w,{'node':j,'polynomial':'6435*x^8-12012*x^6+6930*x^4-1260*x^2+35',
                       'root_bracket_rational':[str(lo),str(hi)],'x':x.json(),'weight':w.json()}))
    assert len(out)==8
    # Eight disjoint sign-change intervals exhaust roots of a degree-eight polynomial.
    assert (sum((x[1] for x in out),I(0))-2).lo<=0<=(sum((x[1] for x in out),I(0))-2).hi
    return out

def geometry():
    pi=pi_interval();gauss=nodes();d=I(U)/(2*M)
    params=[];atoms=[];source_nodes=[]
    for cell in range(M):
        c=I(U)*(2*cell+1)/(2*M)
        for j,(x,w,_) in enumerate(gauss):
            u=c+d*x;q=d*w;gid=len(params)
            assert u.lo>0 and q.lo>0
            params.append((u,q))
            source_nodes.append({'id':gid,'cell':cell,'node':j,'u':u.json(),'quadrature_weight':q.json(),
               'exact_u':{'cell_center':str(F(U*(2*cell+1),2*M)),'half_width':str(F(U,2*M)),
                          'gauss_root_index':j}})
            exp2=(2*u).exp()
            for n in range(1,N+1):
                a=pi*n*n*exp2
                theta=(-a).exp()
                phi=(4*a*a-6*a)*(u/2-a).exp()
                amp=q*phi
                assert amp.lo>0
                atoms.append((gid,n,u,amp))
    return pi,gauss,params,atoms,source_nodes

def complete_error_bounds():
    pi=pi_interval();d=I(U)/(2*M);R=I(1)/16;H=I('.5');L=I(27)
    total=I(0);moment=I(0)
    for j in range(M):
        c=I(U)*(2*j+1)/(2*M)
        for n in range(1,N+1):
            a=pi*n*n*(2*c).exp()
            b=2*((I('.5')+H)*c+a*((2*R).exp()-2)).exp()*(4*a*a*((I('4.5')+L)*R).exp()+6*a*((I('2.5')+L)*R).exp())
            total=total+b
            moment=moment+(c+R)*b
    eq=4*d*total*(d/R)**16
    eq1=4*d*moment*(d/R)**16
    k=N+1
    en=27*k*k*I(-3*k*k).exp()/(1-4*I(-3*(2*k+1)).exp())
    X=I(2*U).exp()
    eu=27*X**2*(-3*X).exp()/(1-4*(-9*X).exp())
    return {'value':{'quadrature':eq.json(),'n_tail':en.json(),'u_tail':eu.json(),'total':(eq+en+eu).json()},
      'first_derivative':{'quadrature':eq1.json(),'n_tail':en.json(),'u_tail':eu.json(),'total':(eq1+en+eu).json()},
      'domain':{'abs_h_max':'0.5','abs_h_plus_it_max':'27'},
      'derivative_tail_reason':'u<=exp(u), H+1<=1.5; the same x^2 integral majorant applies.',
      'derivative_quadrature_reason':'multiply the T49 coefficient majorant on each u-disc by c+R'}

def evaluate(params,atoms,h,t,exact_phase_gid=None):
    h=I(h);t=I(t);factors=[]
    for gid,(u,q) in enumerate(params):
        if gid==exact_phase_gid:
            co,sn=I(0),I(1) # t=pi/(2*u_star), with the SAME exact u_star
        else:co,sn=exp_i(t*u)
        factors.append(((h*u).exp(),(-h*u).exp(),co,sn))
    edges=[];objs=[]
    for origin,(gid,n,u,a) in enumerate(atoms):
        eh,em,co,sn=factors[gid]
        for branch,expv in [(1,eh),(-1,em)]:
            v=(a*expv*co,a*expv*sn*branch)
            dh=scale(v,u*branch);dt=times_i(dh)
            edges.append((v,dh,dt))
            objs.append({'index':len(objs),'origin_id':origin,
              'source_address':{'cell':gid//8,'node':gid%8,'n':n,'branch':'+' if branch==1 else '-'},
              'exponent_sign':branch,'amplitude_sign':'POSITIVE',
              'component_signs':{'re':sign(v[0]),'im':sign(v[1])},
              'value':cj(v),'d_h':cj(dh),'d_t':cj(dt),
              'exact_expression':{'op':'A*exp(epsilon*u*(h+i*t))','origin_id':origin,'epsilon':branch}})
    return edges,objs

def route(edges,removed=()):
    removed=set(removed);v=zero();dh=zero();dt=zero();ids=[];parts=[cj(v)]
    for i,(x,xh,xt) in enumerate(edges):
        if i in removed:continue
        ids.append(i);v=add(v,x);dh=add(dh,xh);dt=add(dt,xt);parts.append(cj(v))
    return {'active_edge_indices':ids,'partial_sums':parts,'endpoint':cj(v),'d_h':cj(dh),'d_t':cj(dt)},(v,dh,dt)

def sums(edges,ids):
    out=[zero(),zero(),zero()]
    for i in ids:
        for k in range(3):out[k]=add(out[k],edges[i][k])
    return out

def status(value,detail):return {'status':value,'detail':detail}

def manifest_audit():
    z=zipfile.ZipFile(ROOT/'provenance/DIAG008_bundle.zip')
    data=json.loads(z.read('SRT_RH_DIAG_008/MANIFEST_SHA256.json'))
    for name,digest in data.items():
        assert hashlib.sha256(z.read('SRT_RH_DIAG_008/'+name)).hexdigest()==digest,name
    exact=json.loads(z.read('SRT_RH_DIAG_008/results/exact_results.json'))
    solver=json.loads(z.read('SRT_RH_DIAG_008/results/smt_results.json'))
    interval=json.loads(z.read('SRT_RH_DIAG_008/results/interval_sign.json'))
    assert exact['status']=='PASS' and all(t['actual']==t['expected'] for t in solver['tests'])
    return {'id':'DIAG-008','date':'2026-10-24','latest_found_as_of':'2026-10-26',
      'status':['REWRITE_CLOSED','BOUNDARY_CLOSED_BY_WITNESS','FINITE_REGRESSION_PASS',
                'INTERVAL_SIGN_CERTIFIED_IN_DECLARED_TRUST_BASE','NUMERICAL_AUDIT_PASS'],
      'manifest_files_checked':len(data),'recorded_exact_counts':exact['counts'],
      'recorded_smt_count':solver['count'],'recorded_interval_sign':interval['full_block_interval'],
      'audit_scope':'archive hashes and recorded statuses checked; DIAG-008 computations not rerun here',
      'native_SRT_Final_run':False,'RH_proved':False}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=str(ROOT));args=ap.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    assert sha(ROOT/'vendor/source.py')==SOURCE_SHA
    assert sha(ROOT/'vendor/intervals.py')==INTERVAL_SHA
    diag=manifest_audit()
    pi,gauss,params,atoms,node_records=geometry()
    gid_star=SELECTED[0]*8+SELECTED[1]
    ustar=params[gid_star][0];tc=pi/(2*ustar)
    print('Exact C parameter pi/(2*u_star), interval:',tc.json(),flush=True)
    bounds=complete_error_bounds()
    definitions=[('CASE-A','0',I(TARGET),None),('CASE-B','.001',I(TARGET),None),('CASE-C','0',tc,gid_star)]
    origins=[]
    for origin,(gid,n,u,a) in enumerate(atoms):
        kernel_arg=pi*n*n*(2*u).exp();theta=(-kernel_arg).exp()
        phi=(4*kernel_arg*kernel_arg-6*kernel_arg)*(u/2-kernel_arg).exp()
        origins.append({'id':origin,'node_id':gid,'n':n,'source_generator':'exp(-pi*n^2*exp(2*u))',
           'theta_weight':theta.json(),'theta_polynomial_argument':kernel_arg.json(),
           'theta_density':phi.json(),'amplitude':a.json(),
           'amplitude_construction':'quadrature_weight[node_id]*theta_density',
           'exact_origin':['cell','node','n','branch']})
    cases={'schema':'RH-XI-ROUTES-EXPORT-001/v1','research_version':'T54 (2026-10-24), unchanged T49 generator',
      'export_date':'2026-10-26','last_diag':diag,'precision':{'decimal_digits':P,
       'arithmetic':'outward-rounded Decimal intervals, all endpoints serialized without display rounding',
       'exact_values':'symbolic exp/gaussian/root expressions plus certified refinable enclosures',
       'underflow_policy':'no float conversion or edge removal; Decimal exponent range inherited from intervals.py'},
      'generator':{'M':M,'N':N,'U':U,'gauss_order':8,'edge_count_per_case':M*8*N*2,
       'order':['cell increasing','Gauss node increasing','n increasing','plus then minus'],
       'Phi_n':'(4*a^2-6*a)*exp(u/2-a), a=pi*n^2*exp(2*u)',
       'word':'ordered_concat(A_jkn*exp(+u_jk*(h+i*t)), A_jkn*exp(-u_jk*(h+i*t)))',
       'full_Xi_bridge':'xi(1/2+h+i*t)=integral_0^infty sum_n Phi_n(u)*(exp(z*u)+exp(-z*u)) du',
       'DIAG008_bridge':'x=exp(2*u); Phi_n(u)=2*exp(u/2)*(2*(pi*n^2*x)^2-3*pi*n^2*x)*exp(-pi*n^2*x)',
       'full_Xi_is_one_finite_expanded_SP_word':False,
       'structural_equality':'literal equality of addressed ordered source sequences; endpoint equality is insufficient',
       'derivative_rule':'d_h^p d_t^q edge = (epsilon*u)^(p+q)*i^q*edge; u, weights and selected basepoint t_star are fixed source constants',
       'finite_shift_rule':'edge(h+dh,t+dt)=exp(epsilon*u*(dh+i*dt))*edge(h,t)',
       'source_sha256':SOURCE_SHA,'intervals_sha256':INTERVAL_SHA},
      'pi':pi.json(),'gauss_nodes':[g[2] for g in gauss],'source_nodes':node_records,
      'origins':origins,'cases':[]}
    loops={'schema':cases['schema'],'search_scope':'All 8192 adjacent +- pairs per case; not an exhaustive search over all substrings.',
      'native_reduction_rule':'No nonempty zero-endpoint path is erased. T49 preserves pair edges; T54 and manual require source/observer witnesses.',
      'permitted_erasure_steps':[],
      'diagnostic_rule':{'id':'POINT_VALUE_DELETE_REJECTED_CONTROL',
        'definition':'Delete a fixed pair only in a separate point-observer diagnostic if its endpoint is proved zero at the selected point.',
        'is_native_SRT_rule':False,'purpose':'test invalid promotion of pointwise value equality to analytic/structural equality'},
      'status_meanings':{'A':'Exact zero at the selected parameter point; not a claim that this is the only zero anywhere.',
        'B':'Interval/numerical zero within a specified error, never a proof of exact zero on its own.',
        'C':'Identically zero analytic function of independent h,t with source geometry fixed.',
        'D':'Equality to the empty word in the declared addressed ordered-word semantics.'},'cases':[]}
    routes={'schema':cases['schema'],'cases':[]}
    checks={'schema':cases['schema'],'complete_source_error_bounds':bounds,'cases':[],
      'rule_audit':'No native erase rule found or added. Deletion states below are explicit negative controls.',
      'last_diag':diag}
    for name,h,t,special in definitions:
        edges,records=evaluate(params,atoms,h,t,special)
        base,bs=route(edges)
        value_e=bounds['value']['total'][1];d_e=bounds['first_derivative']['total'][1]
        full=(bs[0][0].widen(value_e),bs[0][1].widen(value_e))
        full_h=(bs[1][0].widen(d_e),bs[1][1].widen(d_e))
        full_t=(bs[2][0].widen(d_e),bs[2][1].widen(d_e))
        cr=sub(bs[2],times_i(bs[1]));assert contains_zero(cr)
        # Independent reflected-parameter evaluation, preserving all addresses.
        reflected,_=evaluate(params,atoms,-I(h),t,special)
        rv=zero()
        for e in reflected:rv=add(rv,e[0])
        reflection_error=sub(rv,(bs[0][0],-bs[0][1]));assert contains_zero(reflection_error)
        found=[];unresolved=[]
        for pair in range(len(atoms)):
            ids=[2*pair,2*pair+1];point,dh,dt=sums(edges,ids)
            if special is not None and atoms[pair][0]==special:
                a=atoms[pair][3];uu=atoms[pair][2]
                k=2*a*uu
                cert={'A':status('PROVED','h=0, t=pi/(2*u_star), shared u_star. Edges are +i*A and -i*A.'),
                  'B':status('PASS_ENCLOSURE','The outward interval contains zero; exactness comes from A, not this test.'),
                  'C':status('REFUTED','L(h,t)=2*A*cosh(u*(h+i*t)); L(0,0)=2*A>0.'),
                  'D':status('REFUTED','Two nonzero addressed edges are not the empty ordered word under the declared semantics.')}
                assert contains_zero(point) and dh[1].lo>0 and dt[0].hi<0
                assert overlaps(dh,(I(0),k)) and overlaps(dt,(-k,I(0)))
                found.append({'id':name+'-PAIR-'+str(pair),'element_indices':ids,
                   'source_address':{'cell':SELECTED[0],'node':SELECTED[1],'n':atoms[pair][1]},
                   'zero_statuses':cert,'primary_zero_class':'A','native_erase_allowed':False,
                   'point_observer_deletion_allowed':True,'value_interval':cj(point),'exact_point_value':['0','0'],
                   'd_h':cj(dh),'d_t':cj(dt),'strict_derivative_change_lower_bound':str(k.lo),
                   'analytic_local_form':'L(z_star+w)=2*i*A*sinh(u_star*w); z_star=i*pi/(2*u_star)',
                   'minimality':'Both edges are nonzero; no one-edge zero loop exists.',
                   'native_full_SRT_kernel_status':'UNKNOWN (not available or run)'})
            elif contains_zero(point):
                unresolved.append({'element_indices':ids,'A':'UNKNOWN','B':'INTERVAL_CONTAINS_ZERO',
                                   'C':'UNKNOWN','D':'UNKNOWN','native_erase_allowed':False})
        item={'id':name,'h':str(h),'t_interval':t.json(),
          't_exact':TARGET if special is None else {'op':'pi/(2*u)','source_node_id':gid_star},
          't_selection':'parent decimal near first known zero' if special is None else 'fixed real generator node; exact half-turn event, not a claimed Xi zero',
          'edges':records,'finite_endpoint':cj(bs[0]),'full_Xi_interval':cj(full),
          'finite_d_h':cj(bs[1]),'finite_d_t':cj(bs[2]),'full_Xi_d_h_interval':cj(full_h),'full_Xi_d_t_interval':cj(full_t),
          'case_scope':'critical-line near-zero route' if name=='CASE-A' else 'off-critical route with identical generator and height' if name=='CASE-B' else 'real Xi route with four pointwise local zero pairs and nonzero full endpoint; erasure only as rejected diagnostic',
          'full_Xi_zero_status':'UNKNOWN' if contains_zero(full) else 'REFUTED_BY_INTERVAL',
          'finite_word_zero_status':'UNKNOWN' if contains_zero(bs[0]) else 'REFUTED_BY_INTERVAL',
          'whole_route_numeric_near_zero':'WITHIN_CERTIFIED_ABSOLUTE_ERROR_ONLY' if contains_zero(full) else 'EXCLUDED_BY_CERTIFIED_INTERVAL',
          'found_exact_adjacent_loops':len(found),'whole_route_exact_zero_claim':False}
        if name in ('CASE-B','CASE-C'):assert not contains_zero(full)
        stages=[];removed=[];change_records=[]
        for loop in found:
            removed+=loop['element_indices']
            after,ss=route(edges,removed)
            deleted=sums(edges,removed)
            assert contains_zero(sub(bs[0],ss[0]))
            assert not contains_zero(deleted[1]) and not contains_zero(deleted[2])
            assert overlaps(sub(bs[1],ss[1]),deleted[1])
            assert overlaps(sub(bs[2],ss[2]),deleted[2])
            cr_after=sub(ss[2],times_i(ss[1]));assert contains_zero(cr_after)
            mirrored=zero()
            for i,e in enumerate(reflected):
                if i not in set(removed):mirrored=add(mirrored,e[0])
            sym_after=sub(mirrored,(ss[0][0],-ss[0][1]));assert contains_zero(sym_after)
            stage={'step':len(stages)+1,'deleted_loop_id':loop['id'],'cumulative_deleted_indices':list(removed),
               'operation':'POINT_VALUE_DELETE_REJECTED_CONTROL','native_SRT_authorized':False,
               'full_value_with_unchanged_error_remainder':cj((ss[0][0].widen(value_e),ss[0][1].widen(value_e))),**after}
            stages.append(stage)
            change_records.append({'step':len(stages),'deleted_loop_id':loop['id'],
              'endpoint_difference_before_minus_after':cj(sub(bs[0],ss[0])),
              'endpoint_preservation':status('PROVED_AT_SELECTED_POINT','Each removed pair has exact point value zero.'),
              'first_h_derivative_preserved':status('REFUTED','Deleted derivative is strictly nonzero.'),
              'first_t_derivative_preserved':status('REFUTED','Deleted derivative is strictly nonzero.'),
              'derivative_difference_h':cj(deleted[1]),'derivative_difference_t':cj(deleted[2]),
              'CR_preserved':status('PROVED','A fixed subset of entire exponential terms is still entire; dt=i*dh.'),
              'CR_residual_interval':cj(cr_after),
              'critical_reflection_preserved':status('PROVED','Complete +- pairs are removed; each pair satisfies F(-h,t)=conj(F(h,t)).'),
              'reflection_residual_interval':cj(sym_after),
              'active_route_provenance_preserved':False,'archive_provenance_preserved':True,
              'missing_active_origin_edges':list(removed),'structural_equality_preserved':'REFUTED_IN_DECLARED_SEMANTICS',
              'analytic_function_preserved':'REFUTED',
              'full_Xi_value_interpretation':'Same selected-point value if the unchanged full-source error remainder is retained; no germ equality.'})
        checks['cases'].append({'id':name,'CR_residual_interval':cj(cr),'reflection_residual_interval':cj(reflection_error),
           'full_Xi_nonzero_certified':not contains_zero(full),'local_candidates_scanned':len(atoms),
           'exact_local_loops_found':len(found),'unresolved_interval_candidates':len(unresolved),
           'permitted_reduction_count':0,'deletion_diagnostics':change_records,
           'nonzero_edges_certified':sum(not contains_zero(e[0]) for e in edges),'expected_edges':len(edges),
           'native_reduction_checks':'NOT_APPLICABLE: native guard retains the word; no preservation claim inferred from absence of reductions'})
        assert checks['cases'][-1]['nonzero_edges_certified']==len(edges)
        cases['cases'].append(item)
        loops['cases'].append({'id':name,'loops':found,'unresolved_candidates':unresolved,
            'limitation':'No exact local zero pair found in the declared search scope.' if not found else 'Pointwise loops exist; their erasure is not licensed in native T54.'})
        routes['cases'].append({'id':name,'before':base,'permitted_reduction_stages':[],
          'native_after':{'same_as':'before','reason':'No nonempty zero path is erased'},
          'point_observer_deletion_diagnostics':stages})
        print(name,'endpoint',cj(bs[0]),'local exact loops',len(found),flush=True)
    # Minimal pair finite-motion check, independent from differentiation formulas.
    first=loops['cases'][2]['loops'][0]
    origin=first['element_indices'][0]//2
    _,_,uu,aa=atoms[origin];eps=I('0.000001')
    eh=(eps*uu).exp();em=(-eps*uu).exp()
    normal=(I(0),aa*(eh-em))
    co,sn=exp_i(eps*uu)
    tangent=(-2*aa*sn,I(0))
    assert normal[1].lo>0 and tangent[0].hi<0
    checks['minimal_witness']={'case':'CASE-C','loop_id':first['id'],'indices':first['element_indices'],
       'minimal_edge_count':2,'exact_point_value_preserved':True,
       'analytic_semantics_changed':True,'native_rewrite_allowed':False,
       'delta_h':'0.000001','loop_after_h_shift':cj(normal),
       'delta_t':'0.000001','loop_after_t_shift':cj(tangent),
       'source_geometry_frozen_during_differentiation':True,
       'invalid_move_rejected':'Do not keep t*u=pi/2 as an identity while varying t; it holds only at the base point.'}
    checks['continuation_policies']={
      'freeze_reduced_word':{'endpoint_at_basepoint':'PRESERVED','derivatives':'CHANGED',
         'local_function':'original finite endpoint minus the fixed analytic loop function'},
      'regenerate_original_and_recheck':{'endpoint_function':'PRESERVED_POINTWISE',
         'derivatives_of_endpoint_function':'PRESERVED_BY_FUNCTION_EQUALITY',
         'pair_erasure_guard_after_delta_h':'REJECTED_NONZERO','pair_erasure_guard_after_delta_t':'REJECTED_NONZERO',
         'cost':'Requires retained original generator/provenance; the erased word alone does not supply it.'},
      'native_T54_guard':{'erasure':'REJECTED','source':'RETAINED',
         'not_claimed':'Absence of an authorized deletion is not a theorem about all possible SRT contractions.'}}
    refs=json.loads((ROOT/'provenance/T49_REFERENCE_VALUES.json').read_text())
    comparison=[]
    for case in cases['cases'][:2]:
        ref=refs['cases'][case['id']]
        for comp in ['re','im']:
            new=I(*case['finite_endpoint'][comp]);old=I(*ref['finite_'+comp])
            assert max(new.lo,old.lo)<=min(new.hi,old.hi)
        comparison.append({'id':case['id'],'finite_endpoint_interval_overlap':True,
           'reference':'provenance/T49_REFERENCE_VALUES.json','method':'parent paired evaluator versus current individual-edge ordered evaluator'})
    checks['parent_implementation_comparison']=comparison
    checks['status']='PASS_EXPORT_AND_EXPECTED_NEGATIVE_CONTROLS'
    checks['runtime_seconds']=time.perf_counter()-started
    checks['runtime_scope']='CPU computation before JSON serialization; no network or third-party packages'
    for name,data in [('cases.json',cases),('loops.json',loops),('routes.json',routes),('checks.json',checks)]:
        dump(out/name,data)
    metadata={'files':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'vendor').glob('*')) if p.is_file()},
      'diagnostic_archive_sha256':sha(ROOT/'provenance/DIAG008_bundle.zip'),
      'latest_lookup':'Library filename search plus complete /SymSeq list after 2026-10-24T03:51Z found DIAG-008 as latest.',
      'LivingMath_observed':{'version':'0.3.1','sqlite_integrity':'ok','audit_ok':True,'event_count':12,
        'observed_on':'2026-10-26','offline_reproduction_refreshes_service_state':False,
        'mathematical_verification_performed_by_MCP':False,'new_research_events_written':False},
      'implementation':'standard-library interval adapter of unchanged T49 formula, current in T54; not a new source or a new reduction rule'}
    dump(out/'provenance.json',metadata)
    print('PASS. Compute seconds:',checks['runtime_seconds'],'Total seconds:',time.perf_counter()-started,flush=True)

if __name__=='__main__':main()
