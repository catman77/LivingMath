"""006 evidence export; never exports canonical DBs or OAuth credentials."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import statistics

from attention_qa import configure
from normalizer import digest
from live_transfer006 import VERSION
from qa_positive_acceptance import snapshot,write_json


def load(path,default=None):
    return json.loads(path.read_text()) if path.exists() else default


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def export(base: Path):
    meta=load(base/'metadata.json');r=Path(meta['report']);r.mkdir(parents=True,exist_ok=True);src=Path(__file__).parent
    for name in ('worlds.json','oracle.json','frozen-contract.json','source-manifest.json','pre-oracle-source-manifest.json',
                 'source-audit005.json','P0-result.json','first-failure.json','pytest.txt','p0-worker.txt','exception.txt',
                 'run-failures.json','run-source-manifest.json'):
        if (base/name).exists():shutil.copyfile(base/name,r/name)
    for name in ('witnesses','attention-decisions','adversarial-controls','feedback'):
        rows=[json.loads(s) for s in (base/(name+'.jsonl')).read_text().splitlines()] if (base/(name+'.jsonl')).exists() else []
        write_json(r/(name+'.json'),rows)
    for folder in ('development','frozen-sources'):
        if not (base/folder).exists():continue
        for p in (base/folder).rglob('*'):
            if p.is_file():
                dest=r/folder/p.relative_to(base/folder);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    for p in [*src.glob('live_transfer006*.py'),*src.glob('test_live_transfer006*.py'),src/'live_transfer006-contract.json']:
        shutil.copyfile(p,r/p.name)
    transcript=[]
    for name in ('calls.json','stdio-wire.jsonl','result.json','checks.json','integrity.json','server-stderr.txt'):
        p=base/'local86'/name
        if p.exists():
            dest=r/'local86'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(p,dest)
    if (base/'local86/calls.json').exists():transcript=load(base/'local86/calls.json')
    write_json(r/'mcp-transcript.json',{'transport':'actual isolated MCP ClientSession/stdio on private BackupAPI copy','calls':transcript,'production_research_writes':0})
    before=load(base/'before.json');after=snapshot(Path(meta['db']))
    exact={name:after['tables'].get(name)==rows for name,rows in before['tables'].items()};oldfiles={p:sha(Path(p))==value for p,value in meta['protected_files'].items()}
    prev='GENESIS';broken=[]
    for op in after['tables']['operations']:
        expected=digest({'time':op['occurred_at'],'action':op['action'],'details':json.loads(op['details_json']),'previous':prev})
        if expected!=op['entry_hash'] or prev!=op['previous_hash']:broken.append(op['id'])
        prev=op['entry_hash']
    with sqlite3.connect(Path(meta['db']).as_uri()+'?mode=ro',uri=True) as conn:
        sqlok=conn.execute('PRAGMA integrity_check').fetchone()[0];fk=conn.execute('PRAGMA foreign_key_check').fetchall()
    integrity={'original_tables_exact':exact,'old_events':len(before['tables']['events']),'current_events':len(after['tables']['events']),
        'old_operations':len(before['tables']['operations']),'current_operations':len(after['tables']['operations']),
        'unchanged_inode':before['inode']==after['inode'],'SQLite':sqlok,'foreign_keys':fk,'broken_chain_ids':broken,'chain_head':prev,
        'protected_files_count':len(oldfiles),'modified_original_files':[p for p,ok in oldfiles.items() if not ok],
        'private_backup_sha256':meta['backup_sha256'],'backup_matches':sha(base/'research-before.sqlite3')==meta['backup_sha256'],
        'production_research_writes':0,'server_restarted':False,'MCP_API_modified':False}
    integrity['result']='PASS' if (all(exact.values()) and all(oldfiles.values()) and not broken and sqlok=='ok' and not fk and integrity['unchanged_inode'] and integrity['backup_matches']) else 'FAIL'
    write_json(r/'source-preservation.json',integrity)
    patches=load(base/'development/patches.json',[]);allowed={p['file']:p for p in patches};manifest=load(base/'source-manifest.json',{})
    checks={p:sha(Path(p))==h for p,h in manifest.items()}
    frozen_ok=all(ok or (p in allowed and allowed[p]['before_sha256']==manifest[p] and sha(Path(p))==allowed[p]['after_sha256']) for p,ok in checks.items())
    write_json(r/'frozen-checks.json',{'current_original_hash_matches':checks,'explicit_patches':patches,'valid_with_documented_patches':frozen_ok})
    pre=load(base/'preflight.json',{})
    if pre:write_json(r/'live-preflight-summary.json',{'health':pre['health'],'tool_names':[t['name'] for t in pre['tools']['tools']],
        'RH_contract_frontier_digest':digest(pre['contract']['frontier']),'raw_RH_read_private':str(base/'live-readonly')})
    witnesses=load(r/'witnesses.json',[]);decisions=load(r/'attention-decisions.json',[]);controls=load(r/'adversarial-controls.json',[]);cycles=load(r/'feedback.json',[])
    p0=load(base/'P0-result.json',{'result':'FAIL'});reg=load(base/'local86/result.json',{'result':'NOT_RUN'});failures=load(base/'run-failures.json',[])
    core_tree=ast.parse((src/'live_transfer006.py').read_text());oracle_tree=ast.parse((src/'live_transfer006_oracle.py').read_text())
    def imports(tree):return [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names]
    core_imports=imports(core_tree);oracle_imports=imports(oracle_tree)
    isolation=not any('oracle' in n for n in core_imports) and not any('live_transfer' in n or 'normalizer' in n for n in oracle_imports)
    write_json(r/'provenance-review.json',{'core_imports':core_imports,'oracle_imports':oracle_imports,'static_isolation':isolation,
        'family_solver_branches_in_I_T':False,'source_specific_code':'native_extend/observe/admissible only; source rules/data are not oracle tables',
        'input_hints':'closed schema rejects local_rule/omitted_guard/oracle answers; new raw worlds contain none',
        'algorithm_generated':['paired primitive traces','bounded continuation witnesses','source-linked finite guards','attention weighted partitions','derived feedback exclusions'],
        'operator_supplied':['raw histories','native operation definitions','observer and admissibility','costs/weights and finite D_q','independent dependency graph'],
        'oracle_generated':['complete raw replay signatures','ground-truth bounded distinctions','independent survivor loss and feedback statuses'],
        'LLM_generated':[],'LLM_calls':0,'MCP_native_generator_installed':False,
        'limitation':'Registered-prefix probing may degenerate to flat execution.005 coordinate-target inverse construction is not transferred.'})
    by_family={}
    for family in ('register','rewrite','permutation','history'):
        rows=[x for x in witnesses if x['family']==family]
        if not rows:continue
        by_family[family]={'pairs':len(rows),'new_distinctions':sum(x['I']['status']=='NEW_DISTINCTION' for x in rows),
            'unknown_bounded':sum(x['I']['status']=='UNKNOWN_BOUNDED' for x in rows),
            'portable_calls':sum(sum(x['I']['primitive_calls'].values()) for x in rows),
            'flat_calls':sum(sum(x['flat']['primitive_calls'].values()) for x in rows),
            'portable_seconds':sum(x['measurements']['portable']['wall_seconds'] for x in rows),
            'flat_seconds':sum(x['measurements']['flat']['wall_seconds'] for x in rows),
            'baseline005_seconds':sum(x['measurements']['baseline005']['wall_seconds'] for x in rows),
            'max_portable_python_peak_bytes':max(x['measurements']['portable']['python_peak_bytes'] for x in rows),
            'max_flat_python_peak_bytes':max(x['measurements']['flat']['python_peak_bytes'] for x in rows),
            'witness_lengths':[len(x['I']['witness']['suffix']) for x in rows if x['I']['status']=='NEW_DISTINCTION']}
    metrics={'P0':p0,'by_family':by_family,'baseline005_comparable_cases':sum(x['baseline005']['input_reencoded_mod5_only'] for x in witnesses),
        'baseline005_unsupported_cases':sum(not x['baseline005']['input_reencoded_mod5_only'] for x in witnesses),
        '005_primary_calls_note':'005 has no port boundary; actual internal function calls profiled without modifying its code. Boundary zero is not zero work.',
        'measurement_scope':'per-case wall and Python allocations for portable/flat;005 uses C-profiled calls and process high-water RSS (not per-case Python peak); source frame validation amortized once per world,005 validates each call. No universal speed/memory claim.',
        'P1':{'calls':0,'decision':p0.get('P1_decision','NOT_RUN_P0_NOT_PASS')},'LLM_utility':'NOT_TESTED','T_error_count':sum(x['result']!='PASS' for x in decisions)}
    write_json(r/'metrics.json',metrics)
    good=p0['result']=='PASS' and reg['result']=='PASS' and integrity['result']=='PASS' and frozen_ok and isolation and not failures
    result={'engineering':'PASS' if good else 'FAIL','mathematical_mechanism':p0.get('mathematical_mechanism','FAIL'),
        'bounded_completeness':'PASS' if good else 'FAIL','algebraic_shortcut_transfer':'MISSING_CAPABILITY',
        'universal_transfer':'INCONCLUSIVE','LLM_utility':'NOT_TESTED','P1_calls':0,'main_calls':0,
        'finite_preview_proposal':'GO_FOR_SEPARATE_REVIEW' if good else 'NO-GO','MCP_deployed':False,
        'production_research_writes':0,'integrity':integrity['result'],'historical86':reg['result'],'core_version':VERSION,
        'report':str(r/'report.md')}
    write_json(r/'result.json',result);write_json(r/'failures.json',{'original_development_failures':patches,'first_P0_failure':load(base/'first-failure.json'),
        'pipeline_failures':failures,'prior_scores_replaced':False})
    examples=[]
    for family in by_family:
        sample=next((x for x in witnesses if x['family']==family and x['I']['status']=='NEW_DISTINCTION'),None)
        if sample:examples.append({'family':family,'world':sample['world'],'sources':sample['I']['source_hashes'],
            'current':sample['I']['novelty_basis'],'witness':sample['I']['witness'],'predictions':sample['I']['predictions']})
    write_json(r/'concrete-examples.json',examples)
    table='\n'.join(f"| {k} | {v['pairs']} | {v['new_distinctions']} | {v['portable_calls']} | {v['flat_calls']} |" for k,v in by_family.items())
    (r/'report.md').write_text(f'''# LM-LIVE-MATH-TRANSFER-006

Engineering: **{result['engineering']}**. Mathematical mechanism: **{result['mathematical_mechanism']}**. Global/universal transfer: **INCONCLUSIVE**. Algebraic shortcut transfer: **MISSING_CAPABILITY**. No deployment.

## Causal source audit

005 source/results remain unchanged. Its I constructs unit/modular-inverse/guard-boundary probes in a fixed mod5 register representation; T already uses a general weighted outcome partition.006 preserves the probe→paired readout→guard loop and cost+7/3×expected remaining hypotheses, replacing only access to native extend/observe/admissible and the nonportable probe schedule. See source-audit005.json.005.P1 A=.7558/B=.8712/C=0 remains a negative witness-preview result, not an improvement.

One engine processes all families with no family-specific solver branch. Native source definitions differ, as they must; their code/parameters are bound by SHA256. No DSL, Z3, program synthesis, oracle-derived automaton or answer table. I constructs only registered finite continuations and reuses exact prefixes, never quotienting distinct histories by their observation/alias. It stops at the first source-observed mismatch. This is operational probing, not a claim that005's special algebraic inverse construction has become universal. In the worst case it executes the whole registered domain; flat baseline exposes that boundary.

## Registered worlds and correctness

Four different primary algebras: affine register, irreversible adjacent-symbol absorption, noncommuting permutation composition, and history-dependent resource admissibility. Four changed-constant/renamed-operation variants use the same I/T. These are fixed validation variants, not an externally blind generalization benchmark. No local_rule/omitted_guard hint is present in new sources. Bound2, registered D_q,2048 primitive calls per I/T, cooperative2s; resource-limited worker CPU90s/address-space1024MiB/wall120s. Raw sources/oracle/generator/criteria froze before acceptance; documented output/input-adapter patches do not change worlds or oracle.

P0={p0['result']}; pairs={p0.get('pairs')}; new distinctions={p0.get('new_distinctions')}; false witness/novelty/admissibility/grant/provenance={p0.get('false_witnesses')}/{p0.get('false_novelty')}/{p0.get('incorrect_admissibility')}/{p0.get('false_grants')}/{p0.get('missing_source_provenance')}. Negative controls={len(controls)}. Witness correctness and detection are checked separately; equivalent finite signatures produce UNKNOWN_BOUNDED, never a mathematical equivalence claim. Missing context is FAIL_CLOSED. Full independent raw Sig replay is oracle.json; every candidate has source IDs/hashes, guard/version, operation/admissibility trace and an independent receipt in witnesses.json.

| Family | Pairs | New distinctions | Portable primary calls | Flat primary calls |
| --- | --- | --- | --- | --- |
{table}

Costs/time/memory/witness lengths for each case and T are retained. Flat recomputes full signatures without prefix reuse.005 is invoked unchanged: {metrics['baseline005_comparable_cases']} compatible mod5 cases use an explicit input-only re-encoding/conditioning; {metrics['baseline005_unsupported_cases']} other cases preserve its actual unsupported-source refusal. Internal calls are profiled without replacing005 functions. No unsupported result is imputed as correct transfer. Source preparation/validation differences prevent attributing wall-time changes solely to mathematical ingenuity.

## Attention and negative feedback

T is deterministic and checks every intermediate extension against all active hypotheses. It rejects unsafe or uninformative tests and ranks feasible alternatives, independently of which suffix I happened to witness. A permission-divergence witness does not authorize executing its forbidden branch. T has explicit counterfactual readouts and exact rational costs; independent pairwise oracle agreement is attention-decisions.json. Current observed guard filters alternatives before scoring; unrelated/independent hypotheses are retained.

Feedback uses a registered last-consistent source environment, not an oracle-selected future answer. Receipts append only to isolated local DBs, retain source hashes, provisionally exclude contradicted current/dependent predictions and preserve the independent branch. Full cycles and concrete source-linked narrowed applicability are feedback.json. Original source rows remain unchanged. This is not mathematical refutation or a proof. All outputs remain unverified and execution_allowed=false.

## Limits, P1 and integration

P1 optional decision: **SKIP**, calls0/6, main0. The native question is answered deterministically; asking a model to guess an already computed T optimum would repeat the005 design error. No LLM utility result is claimed. A future optional protocol may test a model-proposed hypothesis separately from computed T; it requires its own frozen proposal scoring and stop rules.

Bounded operational transfer is supported; efficient algebraic construction beyond005 is not demonstrated. Exact general discrimination through opaque operations can require all registered probes. No universal mathematics, RH/SRT theorem, semantic equivalence from aliases, or intelligence-growth claim. A separately reviewable read-only MCP proposal/test contract is included; it is not installed.

Canonical preservation={integrity['result']}: {integrity['current_events']} events/{integrity['current_operations']} operations; all old sources/reports/AGENTS, rows, inode, SQLite/FKs and audit chain unchanged. Chain head={prev}. Private BackupAPI snapshot retained. Historical86 actual ClientSession/stdio on private copy={reg['result']}; full local regression in pytest.txt. Live health/RH contract were read only; MCP remains0.4.2/18 tools, normalizer004.1 local. No production API, schema, policy or record modification, no restart/reconnection needed.
''')
    (r/'RCA.md').write_text('''# RCA

## SOURCE_BINDING_BUG —005 baseline input adapter

The first adapter emitted unsupported question label other. Unchanged005 correctly returned INSUFFICIENT_CONTEXT/INVALID_HYPOTHESIS_BINDING before any arithmetic. development/baseline-first-result.json preserves the exact expected/actual; original adapter and minimum patch retained. The fix conditions only the current hypothesis input domain, retains the independent branch, and uses supported005 labels. No005 code, world, oracle or criterion was changed. Targeted and full regression are retained.

## SOURCE_BINDING_BUG — feedback provenance export

A bound feedback receipt affected derived statuses but its ID/hash was absent from the explicit source_event_ids/known_failures export. development/feedback-provenance-before.txt retains the failing assertion. The minimum patch adds retained adverse source references to exported provenance; it does not alter predictions, selection, grants or truth status. Original code/hashes and patch are retained. No source/oracle score is rewritten.

## MISSING_CAPABILITY — nonportable algebraic shortcut

The005 modular-inverse coordinate-target probe generator is specific to its native affine arithmetic.006 transfers operational paired probing and weighted attention through primitive ports, not that inverse heuristic. Its worst-case work can equal registered finite probing/flat signatures. UNKNOWN_BOUNDED never asserts equivalence. This limitation is explicit even if all finite correctness/completeness criteria pass; it does not establish a universal algebraic method.

## Stop and scientific boundaries

Any genuine mismatch saves first-failure.json and partial JSONL, stops P0, and blocks inference. Source/observer/version/leakage/budget controls preserve their negative outcomes. Initial missing-module red test is scaffolding, not a mathematical failure. P1 is skipped by an explicit deterministic-usefulness decision; no missing model scores are imputed.005 negative pilot remains unchanged. Native source rules are operator-provided, I/T outputs algorithm-produced, oracle tables independently computed, LLM outputs absent.
'''+f"\nCurrent first P0 failure={load(base/'first-failure.json')}; pipeline failures={failures}.\n")
    (r/'read-only-preview-proposal.md').write_text('''# Proposal only: live_math_preview

A separate future MCP tool may accept project, source IDs, current obligation/scope/version, observer, registered finite D_q and explicit primitive/time/length bounds. It returns either an unverified source-backed distinction/attention recommendation or FAIL_CLOSED/UNKNOWN_BOUNDED. No grant, completion, proof, policy or source mutation. Existing attend/interpret remain persistence endpoints.

Required tests: real tools/list/client schema compatibility; project/source-hash/scope/version binding; C4 and partial source refusal; exact independent finite witness/admissibility checks; robustly feasible deterministic T; source-linked feedback and independent-branch retention; bounded unknown; primitive/time/memory quota; rejection of oracle/guard hints; immutable DB/inode/hash-chain and existing86 invariants. Keep native source adapters explicit; no arbitrary code supplied over MCP. Installation/migration requires a separate user decision. This file performs no deployment.
''')
    (r/'README.md').write_text('''# Reproduce006

Use the repository .venv with existing requirements-causal-qa.txt. ./reproduce.sh creates a fresh private BackupAPI baseline, freezes new synthetic sources/oracle, runs full local tests, actual isolated MCP86 and resource-limited P0. No LLM calls. --help only prints options; existing result directories are refused. Canonical DB/raw RH/OAuth data stay private.

The report includes native source definitions, port-based I/T, independent oracle and unchanged005 baseline adapter. Flat signature output is a baseline artifact, never generator input. Mathematically compatible005 input re-encoding changes detached fixture representations only. It does not edit any historical source or code. Per-case allocation/time/primary-operation metrics have distinct scopes.

Offline package check: ../../../../.venv/bin/python verify_artifacts.py from this folder. Source-manifest.json records preregistration; frozen-checks.json documents exact pre-P0 bug fixes without world/oracle changes. Reproduction after the fixes starts directly from corrected source. Historical development FAIL traces in this initial cohort remain authoritative evidence of those fixes. A resource or capability failure is a reportable negative, never a reason to silently expand the domain or inference budget.
''')
    (r/'reproduce.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)"\nexec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/live_transfer006_qa.py" "$@"\n');(r/'reproduce.sh').chmod(0o755)
    (r/'verify_artifacts.py').write_text('''import json,hashlib\nfrom pathlib import Path\nr=Path(__file__).resolve().parent\nload=lambda n:json.loads((r/n).read_text())\nc={}\nc['hashes']=all(hashlib.sha256((r/p).read_bytes()).hexdigest()==h for p,h in load('manifest-sha256.json')['files'].items())\nc['P0']=load('P0-result.json')['result']=='PASS'\nc['witnesses']=all(x['independent_verification']=='PASS' for x in load('witnesses.json'))\nc['attention']=all(x['result']=='PASS' for x in load('attention-decisions.json'))\nc['controls']=all(x['result']=='PASS' for x in load('adversarial-controls.json'))\nc['source']=load('source-preservation.json')['result']=='PASS'\nc['secrets']=load('secret-scan.json')['result']=='PASS'\nc['isolation']=load('provenance-review.json')['static_isolation']\nprint(json.dumps({'result':'PASS' if all(c.values()) else 'FAIL','checks':c},indent=2))\nraise SystemExit(0 if all(c.values()) else 1)\n''')
    write_json(r/'changed-files.json',{'added':[str(p.relative_to(src.parent)) for p in src.glob('*transfer006*') if p.is_file()]+['docs/superpowers/plans/2026-10-27-live-math-transfer-006.md'],
        'original_sources_modified':integrity['modified_original_files'],'production_deployed':False})
    secret=Path(configure()['LIVE_MATH_PASSWORD_FILE']).expanduser().read_text().strip().encode();leaks=[];forbidden=[]
    for p in r.rglob('*'):
        if not p.is_file():continue
        data=p.read_bytes()
        if (len(secret)>=8 and secret in data) or re.search(rb'Bearer[ \t]+[A-Za-z0-9._~+/-]{20,}',data):leaks.append(str(p.relative_to(r)))
        if '.sqlite' in p.name or p.name in {'before.json','server.env','auth.json'}:forbidden.append(str(p.relative_to(r)))
    write_json(r/'secret-scan.json',{'result':'PASS' if not leaks and not forbidden else 'FAIL','credential_matches':leaks,'forbidden_files':forbidden,'canonical_backup_exported':False})
    for folder in ('local86',):
        if (r/folder).exists():
            for p in [r/folder,*(r/folder).rglob('*')]:p.chmod(0o700 if p.is_dir() else 0o600)
    hashes={str(p.relative_to(r)):sha(p) for p in sorted(r.rglob('*')) if p.is_file() and p.name!='manifest-sha256.json'}
    write_json(r/'manifest-sha256.json',{'algorithm':'sha256','files':hashes})
    return result
