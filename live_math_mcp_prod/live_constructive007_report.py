"""007 artifacts and scoped conclusions, excluding canonical data/credentials."""
import ast,hashlib,json,re,shutil,sqlite3,statistics
from pathlib import Path

from normalizer import digest
from live_constructive007 import VERSION
from qa_positive_acceptance import snapshot,write_json
from attention_qa import configure


def load(p,default=None):return json.loads(p.read_text()) if p.exists() else default

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def export(b):
    meta=load(b/'metadata.json');r=Path(meta['report']);r.mkdir(parents=True,exist_ok=True);src=Path(__file__).parent
    for name in ('worlds.json','oracle.json','frozen-contract.json','source-hashes.json','pre-oracle-hashes.json','run-source-hashes.json',
                 'P0-result.json','first-failure.json','pytest.txt','worker.txt','exception.txt','run-failures.json','expected-fault-regressions.json'):
        if (b/name).exists():shutil.copyfile(b/name,r/name)
    for name in ('paired-costs','metamorphic','attention','feedback'):
        rows=[json.loads(s) for s in (b/(name+'.jsonl')).read_text().splitlines()] if (b/(name+'.jsonl')).exists() else []
        write_json(r/(name+'.json'),rows)
    for folder in ('development','frozen-sources'):
        if (b/folder).exists():
            for p in (b/folder).rglob('*'):
                if p.is_file():
                    d=r/folder/p.relative_to(b/folder);d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,d)
    for p in [*src.glob('live_constructive007*.py'),*src.glob('test_live_constructive007*.py'),src/'live_constructive007-contract.json']:shutil.copyfile(p,r/p.name)
    for name in ('result.json','calls.json','checks.json','stdio-wire.jsonl','integrity.json','server-stderr.txt'):
        if (b/'local86'/name).exists():
            d=r/'local86'/name;d.parent.mkdir(exist_ok=True);shutil.copyfile(b/'local86'/name,d)
    reg=load(b/'local86/result.json',{'result':'NOT_RUN'});write_json(r/'regression86.json',reg)
    write_json(r/'mcp-transcript.json',{'transport':'actual isolated ClientSession/stdio on private BackupAPI copy','production_writes':0,'calls':load(b/'local86/calls.json',[])})
    before=load(b/'before.json');after=snapshot(Path(meta['db']));exact={k:after['tables'].get(k)==v for k,v in before['tables'].items()}
    unchanged={p:sha(Path(p))==h for p,h in meta['protected_files'].items()};previous='GENESIS';broken=[]
    for op in after['tables']['operations']:
        expected=digest({'time':op['occurred_at'],'action':op['action'],'details':json.loads(op['details_json']),'previous':previous})
        if op['entry_hash']!=expected or op['previous_hash']!=previous:broken.append(op['id'])
        previous=op['entry_hash']
    with sqlite3.connect(Path(meta['db']).as_uri()+'?mode=ro',uri=True) as c:
        sqlok=c.execute('PRAGMA integrity_check').fetchone()[0];fk=c.execute('PRAGMA foreign_key_check').fetchall()
    integrity={'original_tables_exact':exact,'old_events':len(before['tables']['events']),'current_events':len(after['tables']['events']),
        'old_operations':len(before['tables']['operations']),'current_operations':len(after['tables']['operations']),
        'inode_unchanged':before['inode']==after['inode'],'SQLite':sqlok,'foreign_keys':fk,'chain_broken_ids':broken,'chain_head':previous,
        'protected_file_count':len(unchanged),'changed_original_files':[p for p,ok in unchanged.items() if not ok],
        'backup_hash_matches':sha(b/'research-before.sqlite3')==meta['backup_sha256'],'private_backup_sha256':meta['backup_sha256'],
        'production_writes':0,'MCP_installed':False,'server_restarted':False}
    integrity['result']='PASS' if all(exact.values()) and all(unchanged.values()) and not broken and sqlok=='ok' and not fk and integrity['inode_unchanged'] and integrity['backup_hash_matches'] else 'FAIL'
    write_json(r/'integrity.json',integrity)
    manifest=load(b/'source-hashes.json',{});frozen={p:sha(Path(p))==h for p,h in manifest.items()};write_json(r/'frozen-checks.json',frozen)
    pre=load(b/'preflight.json',{})
    if pre:write_json(r/'live-health.json',{'health':pre['health'],'tools':[x['name'] for x in pre['tools']['tools']],
        'RH_frontier_digest':digest(pre['contract']['frontier']),'raw_private':str(b/'live-readonly'),'connector':'Unknown tool; real HTTPS/OAuth fallback'})
    rows=load(r/'paired-costs.json',[]);decisions=load(r/'attention.json',[]);controls=load(r/'metamorphic.json',[]);cycles=load(r/'feedback.json',[])
    write_json(r/'witnesses.json',[{'world':x['world'],'pair':x['pair'],'C':x['C']['output'],'native_validation_trace':x['C']['native_trace'],
        'independent_verification':x['independent_verification']} for x in rows])
    successful=[x for x in rows if x['pair']['hidden'] and x['C']['output']['status']=='NEW_DISTINCTION' and x['B1']['output']['status']=='NEW_DISTINCTION']
    by_family={}
    for family in sorted({x['family'] for x in rows}):
        group=[x for x in rows if x['family']==family];found=[x for x in successful if x['family']==family]
        cn=sum(x['C']['ledger']['total_native_calls'] for x in found);bn=sum(x['B1']['ledger']['total_native_calls'] for x in found)
        by_family[family]={'cases':len(group),'paired_successful_witnesses':len(found),'C_native_calls':cn,'B1_native_calls':bn,
            'C_B1_ratio':cn/bn if bn else None,'ratio_zero_denominator':'N/A' if not bn else None,
            'constructive_witnesses':sum(x['C']['output']['strategy']=='CONSTRUCTIVE_VALIDATED' for x in found),
            'fallback_cases':sum(x['C']['output']['strategy']=='FALLBACK_BOUNDED' for x in group),
            'cold_pair_wins':sum(x['C']['ledger']['total_native_calls']<x['B1']['ledger']['total_native_calls'] for x in found),
            'all_case_wall_seconds':{m:sum(x[m]['wall_seconds'] for x in group) for m in ('B0','B1','C')},
            'all_case_max_python_peak_bytes':{m:max(x[m]['python_peak_bytes'] for x in group) for m in ('B0','B1','C')},
            'law_validation_seconds':sum(x['C']['output'].get('law',{}).get('validation_wall_seconds',0) for x in group)}
    cn=sum(x['C']['ledger']['total_native_calls'] for x in successful);bn=sum(x['B1']['ledger']['total_native_calls'] for x in successful)
    metrics={'families':by_family,'primary_ratio_C_B1':cn/bn if bn else None,'C_native_calls_paired_success':cn,'B1_native_calls_paired_success':bn,
        'paired_successful_witnesses':len(successful),'coverage':len(rows)/120,'zero_denominator_is_NA':True,
        'constructor_applicability':sum(x['C']['output']['strategy']=='CONSTRUCTIVE_VALIDATED' for x in successful)/len(successful) if successful else None,
        'cold_law_cost_included_per_pair':True,'native_count_scope':'All leaf extend/observe/admissible invocations, including preparation, validator/adapter and fallback; ledger never reset.',
        'structural_work_scope':'Separate typed counts (hashes, descriptor checks/bytes, feature reads, index membership); not equated to CPU cycles or native calls.',
        'common_input_stage':'Normalizer004.1/source frame preparation once per world, native_calls0; measured separately in every pair row. No hidden source-state replay outside ledgers.',
        'time_claim':'Method times include cold C law work; source decoding is shared and visible. No claim of universal CPU speedup.',
        'H3_checks':len(decisions),'H3_errors':sum(x['result']!='PASS' for x in decisions),'metamorphic_controls':len(controls),'P1_calls':0}
    write_json(r/'metrics.json',metrics)
    p0=load(b/'P0-result.json',{'result':'FAIL_RCA'});failures=load(b/'run-failures.json',[])
    def imports(path):
        t=ast.parse(path.read_text());return [n.module for n in ast.walk(t) if isinstance(n,ast.ImportFrom)]+[x.name for n in ast.walk(t) if isinstance(n,ast.Import) for x in n.names]
    ci=imports(src/'live_constructive007.py');li=imports(src/'live_constructive007_laws.py');oi=imports(src/'live_constructive007_oracle.py')
    isolation=not any('oracle' in n for n in ci+li) and not any('live_' in n or 'normalizer' in n for n in oi)
    good=(p0['result']!='FAIL_RCA' and p0.get('correctness')=='PASS' and reg['result']=='PASS' and integrity['result']=='PASS' and all(frozen.values()) and isolation and not failures)
    status=p0['result'] if good else 'FAIL_RCA'
    result={'status':status,'H1':'PASS_BOUNDED_NATIVE_QUERY_REDUCTION' if status=='PASS_CONSTRUCTIVE_TRANSFER_BOUNDED' else 'NOT_ESTABLISHED',
        'H2':'PASS' if good else 'FAIL','H3':'PASS' if good else 'FAIL','engineering':'PASS' if good else 'FAIL',
        'core_version':VERSION,'baseline_B1':'unchanged core006.2','normalizer':'004.1','native_MCP_generator':False,'MCP_installed':False,
        'production_writes':0,'P1':'SKIP','P1_calls':0,'main_calls':0,'universal_constructive_search':'NOT_CLAIMED',
        'P2':'READY_FOR_SEPARATE_READONLY_PREVIEW_REVIEW' if good else 'NO-GO','integrity':integrity['result'],'report':str(r/'report.md')}
    write_json(r/'result.json',result)
    write_json(r/'provenance.json',{'constructor_imports':ci,'validator_imports':li,'oracle_imports':oi,'static_isolation':isolation,
        'I_family_solver_branches':False,'validator_pair_or_D_search':False,
        'source_inputs':['native programs/parameters','raw histories','source-bound law kind/guard/coverage','registered D/cost/priors'],
        'constructor_outputs':['differing certified feature coordinate','one primitive proposal','mandatory native readout witness','fallback with retained spent cost'],
        'validator_outputs':['parameter-domain checks and reviewed code identity','law-derived coordinate index, independent of any target pair'],
        'oracle_outputs':['full raw signatures','witness correctness','independent T loss'],
        'LLM_outputs':[],'source_law_assurance':'SOURCE_SCHEMA_CERTIFIED on fixed reviewed program schemas; experimental coverage BOUND_VALIDATED. Not a universal proof checker or server verified status.',
        'adapter_native_calls_counted_at_leaf_entry':True,'source_preparation_is_not_free':True})
    rows_table='\n'.join(f"| {k} | {v['paired_successful_witnesses']} | {v['C_native_calls']} | {v['B1_native_calls']} | {v['C_B1_ratio']} | {v['cold_pair_wins']} |" for k,v in by_family.items())
    (r/'report.md').write_text(f'''# LM-LIVE-MATH-CONSTRUCTIVE-007

Decision: **{status}**. H1={result['H1']}; H2={result['H2']}; H3={result['H3']}. This is bounded native-query reduction, not universal mathematical search or a proof of RH/SRT.

## Mechanism

I uses one source-certified coordinate-separation contract across affine, right-permutation and prefix-erasure sources. A source-specific validator receives definitions/guards, never the target pair or oracle table. It derives a coordinate→primitive index from source generator descriptions. Generic I reads the two replayed source objects, locates a differing covered feature, constructs one primitive action and validates BOTH histories through the exact metered native operations. A singleton witness is minimal in length because the empty/current observations agree; it need not be first in D or optimal by T cost. T remains exactly core006.2 and does not consult I's witness.

The extra law information is explicit side information, not available for arbitrary opaque sources. The law index does not contain prewritten target suffixes or outputs. Validation checks the bound reviewed native program schema, source hash/project/scope/version/observer, and algebraic parameter guard. It does not prove arbitrary supplied programs correct. The proof schemas/guards are documented in source-audit.md. No new fundamental operation, DSL, program solver or matrix of oracle answers is introduced.

## Cold paired evaluation

Pairs={p0.get('pairs')}; successfully found paired witnesses={len(successful)}. Every raw signature/witness/admissibility is independently replayed. Coverage={metrics['coverage']}; primary ratio C/B1={metrics['primary_ratio_C_B1']}. All native calls include source loads, mandatory validation and fallback. Law validation/preprocessing is paid cold on EVERY pair. Typed structural work, descriptor/hash/feature accesses, wall and allocations are retained rather than called free. B0 is diagnostic only; H1 uses B1 (unchanged006.2 prefix reuse) on the same source/domain/order/caps.

| Algebra | Paired witnesses | C native calls | B1 native calls | C/B1 | Cold pair wins |
| --- | --- | --- | --- | --- | --- |
{rows_table}

The criterion requires a cold verified witness with C<B1 in at least two different algebras. Winning algebras={p0.get('winning_algebras')}. All cases, including slower/unknown/already-observed and opaque cases, remain in paired-costs.json. No result is imputed for zero denominators. Source normalization/frame decoding is a shared, separately timed input stage with zero native invocations; all per-pair history replay and law-specific work is in the ledgers. Native-query savings do not by themselves establish total CPU or wall-time savings.

## H2: fallback and boundaries

Missing, stale, partial, wrong-source/observer or false-kind laws are rejected or yield no covered feature; C falls back to the exact B1 without resetting spent work. If the budget is exhausted it returns UNKNOWN_BOUNDED, never equivalence. Distinct source IDs with equal features/signatures retain their identity. Primitive-label renaming uses the same stable source ordinals as006.2. A permission-only distinction is a witness of admissibility disagreement, not an execution grant. Point/germ representation mismatch is refused. No commuting/reordering rule is assumed for permutations.

The opaque source has a unique late distinguishing continuation and no applicable certificate: C returns to bounded probing, with no expected query advantage. Source law applicability and cold preprocessing costs are explicit. If a proposed law's consequence fails native readout, the candidate is not emitted and fallback records the mismatch. All research outputs remain unverified/no grant/completion; a law schema receipt is not mathematical verification in the server.

## H3 and feedback

Unchanged T has {len(decisions)} checks against independent survivor-cost enumeration, before/after I with fresh equal budgets and identical feasible actions. It ranks cost/remaining ambiguity, not beauty of the witness. Source-linked negative feedback retains independent branches and original source rows; cycles are feedback.json. Structured witness correctness is separate from experiment selection.

## Regression, resources and provenance

Full pytest is pytest.txt; historical86 actual isolated MCP/stdio={reg['result']}. Intentional mutant assertion failures for provenance/alias/noncommutativity/stale/permission are separately labeled expected-fault-regressions.json, not genuine implementation failures or recolored PASS. Any real mismatch writes first-failure.json and stops the cohort; fresh cohorts only after a narrow patch. The005 negative pilot and006 resource/fingerprint failures are preserved unchanged, not pooled.

P0 CPU90s/address-space1024MiB/wall120s, per-pair native limit2048 and witness bound2; observed P0 seconds={p0.get('seconds')}, worker RSS={p0.get('max_rss_KiB')}KiB. Three parameter/operation holdouts were frozen before acceptance and not used to tune the constructor. These are registered finite validation variants, not a claim of externally blind universality.

Canonical integrity={integrity['result']}: {integrity['current_events']} events/{integrity['current_operations']} operations, inode/SQLite/FKs/full hash chain and all old source/reports/AGENTS preserved. Backup remains private. No production write, migration, policy/API change, restart or MCP tool install. Real live health/contract were read only; MCP stays0.4.2/18 tools. Core007 is an experimental Python module, not a deployed MCP generator.

P1=SKIP,0/6 calls: no registered proposer question adds information to this deterministic law test; no LLM re-ranking of computed T. P2={result['P2']}; review is separate from installation. Minimal next experiment: new source-certified algebra/opaque control with the SAME coordinate contract and cold end-to-end ledger, or separately review the bounded read-only preview contract. No automatic main or deployment.
''')
    (r/'source-audit.md').write_text('''# Source audit and paper examples

005.I uses mod5 coordinate/unit/inverse probes;006.2 I uses registered paired probes/prefix reuse.006.2 T groups feasible predicted readouts and minimizes cost+7/3×expected surviving alternatives. Both are frozen and their prior outcomes unchanged.007 preserves the source/guard/trace/witness semantics and T; it changes only I's candidate construction when an independently bound law schema applies.

## Opaque lower bound

With no structure, two opaque oracles can agree on every tested continuation and disagree only on the last untested one. Guaranteed complete discrimination in that model can require all D.007 claims no generic sublinear opaque search. Its advantage is conditional on explicitly certified source representation/readout laws.

## Reviewed source schemas

- Affine: x'=x+k*y mod m, y'=y+k. Equal x and gcd(k,m)=1 imply different y produce different x'. The source validator checks m/initial scalar domain, coefficient types and unit gcds; the coordinate index is derived without a pair. It is not a general affine solver.
- Right permutation: E(v,g)[i]=v[g[i]], so O(E(v,g))=v[g[0]]. Check each g is a permutation and bind the native right-composition implementation. No ab=ba assumption.
- Prefix erasure: E(word,j)=word[j:], O=head or EMPTY, so O(E(word,j)) is padded_word[j]. Check nonnegative cuts/width/EMPTY guard. Deletion and absorption are noninvertible; no inverse is assumed.

These are explicit algebraic arguments about fixed reviewed native code, not a theorem-prover for arbitrary code. SOURCE_SCHEMA_CERTIFIED is scoped to implementation hash/parameters/observer; finite experimental coverage is BOUND_VALIDATED. No research result is set to verified.

## Paper examples fixed before acceptance

Affine m12: history(k=1) gives(1,2); history(k=1,k=6) gives(1,8). Both observe1. Even k=0,2,4,6,8,10 cannot separate delta_y6, while unit k=1 gives3 versus9. The constructor derives the unit from gcd checks, not a target-word field. Cold cost must include law checking, both history replays and native validation.

Permutation n4: identity and swap(1,2) both observe0. A source generator g with g[0]=1 produces1 versus2. The constructor uses the first differing feature and the law-derived generator index, without a target pair in the source contract. The native validation still executes g on both histories. Right-composition order matters.

The law schema verifies no native sample table; validation invokes no extend/observe/admissible. Any native calls in source/adapter/validator are independently counted at leaf entry. Hash/descriptor/coordinate work is reported separately, with actual wall/memory. No cold preprocessing cost is amortized away in the primary metric.
''')
    (r/'RCA.md').write_text('''# RCA

## Genuine cohort failures

A real correctness/source/cost mismatch, if present, is first-failure.json with exact paired outputs and JSONL. It stops acceptance and prevents inference; a minimal patch must start a new cohort without changing source worlds/oracle/D/primary gate. Initial missing-module red trace is expected scaffolding. Intentional corrupt-output regressions are marked EXPECTED_MUTANT_ASSERTION_FAILURE and are not claimed as bugs that were fixed.

## Historical failures remain historical

005: invalid closed fixture, corrected before inference; negative C witness-preview pilot remains negative.006: baseline adapter label mismatch, missing feedback provenance, CPU-limited instrumentation cohort and primitive-label novelty bug remain in their original packages/RCA.007 neither rewrites their scores nor changes their code.

## Capability boundary

The constructor relies on explicit reviewed source-law schemas and direct source features. It is not an opaque black-box improvement, universal program verifier or source-independent algebraic solver. Invalid/nonapplicable laws are advisory failures followed by bounded fallback. Source preprocessing, structural scans and native work remain visible. Native-query reduction may coexist with slower cold CPU time. Source-code matching plus mathematical proof-schema assumptions must be reviewed before any new adapter; self-declared law text is not authority.
'''+f"\nCurrent first-failure={load(b/'first-failure.json')}; pipeline failures={failures}.\n")
    (r/'read-only-preview-proposal.md').write_text('''# Separate review only

A future read-only preview may accept project-local immutable source refs, current obligation/scope/version, a registered native adapter/observer, finite D and explicit caps. It returns source-backed unverified I/T proposals and cold ledgers, never grants/completion/proof or source mutation. Keep law validation separate and whitelist reviewed implementation/schema digests. Do not execute arbitrary uploaded code. Test real tools/list/client schemas, law-source/observer/version binding, invalid/missing-law fallback, leaf native metering including adapter calls, rename/noncommutative/permission/germ controls, independent replay and all historical86 invariants. Installing a tool or migration requires a separate user decision. This proposal performs no installation.
''')
    (r/'README.md').write_text('''# Reproduction

Use the repository .venv with existing requirements-causal-qa.txt. ./reproduce.sh creates a fresh private BackupAPI baseline, freezes sources/laws/oracle, runs full local tests, isolated real MCP86 and capped deterministic P0. No model calls; --help is safe. Existing output directories are refused. P1, if ever useful, needs a separately frozen proposer test and maximum6 calls, never re-ranking a computed T optimum.

Raw native traces, certificate receipts, paired costs, rejected laws and expected mutant failures are included. Canonical snapshots/raw RH/OAuth credentials are private and not exported. Offline artifact check: ../../../../.venv/bin/python verify_artifacts.py from this report directory. The baseline006.2 files are unchanged; new frame/ports implement the same protocol for declared007 sources. Primary native-query ratios include cold law prep/validation and all fallback calls. Structural work categories and common source setup remain separate and must not be mistaken for zero cost or a universal CPU speedup.
''')
    (r/'reproduce.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)"\nexec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/live_constructive007_qa.py" "$@"\n');(r/'reproduce.sh').chmod(0o755)
    (r/'verify_artifacts.py').write_text('''import json,hashlib\nfrom pathlib import Path\nr=Path(__file__).resolve().parent\nload=lambda n:json.loads((r/n).read_text())\nc={}\nc['hashes']=all(hashlib.sha256((r/p).read_bytes()).hexdigest()==h for p,h in load('manifest-sha256.json')['files'].items())\nc['paired_correctness']=all(x['independent_verification']=='PASS' for x in load('paired-costs.json'))\nc['H2']=all(x['result']=='PASS' for x in load('metamorphic.json'))\nc['H3']=all(x['result']=='PASS' for x in load('attention.json'))\nc['integrity']=load('integrity.json')['result']=='PASS'\nc['MCP86']=load('regression86.json')['result']=='PASS'\nc['secrets']=load('secret-scan.json')['result']=='PASS'\nc['isolation']=load('provenance.json')['static_isolation']\nprint(json.dumps({'result':'PASS' if all(c.values()) else 'FAIL','checks':c},indent=2))\nraise SystemExit(0 if all(c.values()) else 1)\n''')
    write_json(r/'changed-files.json',{'added':[str(p.relative_to(src.parent)) for p in src.glob('*constructive007*') if p.is_file()]+['docs/superpowers/plans/2026-10-27-live-math-constructive-007.md'],
        'changed_original_files':integrity['changed_original_files'],'MCP_installed':False})
    secret=Path(configure()['LIVE_MATH_PASSWORD_FILE']).expanduser().read_text().strip().encode();leaks=[];forbidden=[]
    for p in r.rglob('*'):
        if not p.is_file():continue
        data=p.read_bytes()
        if (len(secret)>=8 and secret in data) or re.search(rb'Bearer[ \t]+[A-Za-z0-9._~+/-]{20,}',data):leaks.append(str(p.relative_to(r)))
        if '.sqlite' in p.name or p.name in {'before.json','server.env','auth.json'}:forbidden.append(str(p.relative_to(r)))
    write_json(r/'secret-scan.json',{'result':'PASS' if not leaks and not forbidden else 'FAIL','matches':leaks,'forbidden_files':forbidden,'canonical_backup_exported':False})
    if (r/'local86').exists():
        for p in [r/'local86',*(r/'local86').rglob('*')]:p.chmod(0o700 if p.is_dir() else 0o600)
    write_json(r/'manifest-sha256.json',{'algorithm':'sha256','files':{str(p.relative_to(r)):sha(p) for p in sorted(r.rglob('*')) if p.is_file() and p.name!='manifest-sha256.json'}})
    return result
