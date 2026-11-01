"""Preregistered source programs and structurally separated continuations."""
from itertools import product
import random


POLICY = {
    'schema':'operational013-freeze/v1','algorithm':'one rational linear map on observed input span per native generator',
    'representation':'origin-relative right-aligned integer sequence, constant/length/occupancy/value, width4',
    'guard':'exact input-span membership, valid integer sequence, native admissibility, source/version/observer binding',
    'discovery_prefix_length':2,'validation_prefix_length':3,
    'heldout_seed':130027,'heldout_lengths':[6,8,10,12,14],'heldout_count_per_source':40,
    'budgets':{'native_queries_per_method_source':20000,'P0_wall_seconds':120,'P0_CPU_seconds':90,'RSS_KiB':524288},
    'baselines':{'B1':'unchanged006.2 endpoint, exact shared-prefix cache and full heldout horizon',
                 'B2':'unchanged012 construct from source-field traces; never extrapolate its finite applicability',
                 'B3':'exact observed transition memory; refuse absent keys'},
    'gate':'at least two distinct sources fully correct prereveal predictions, missing B3 transitions, total native query savings; all controls/regressions',
    'failure':'first false guarded prediction stops scientific claim; preserve original failure, no heldout repair',
    'claim':'bounded empirical transport, proof_status unverified; source equality and universal transfer not asserted',
    'typed_hidden_histories':{'A':[0,1],'B':[0]},'typed_iterations_per_selected_family':2,
    'P1':'NOT_AUTHORIZED_AUTOMATICALLY','production_install':False}


def declarations():
    return [
        {'id':'A','algebra':'affine','initial':[1,0],'arity':2},
        {'id':'B','algebra':'permutation','initial':[0,1,2,3],'arity':2},
        {'id':'C','algebra':'stack','initial':[],'arity':3},
        {'id':'D','algebra':'opaque','initial':[2,3],'arity':2},
        {'id':'E','algebra':'insufficient','initial':[0,0],'arity':2},
    ]


def prefixes(arity, length, exact=False):
    return [list(w) for n in ([length] if exact else range(length+1)) for w in product(range(arity),repeat=n)]


def sealed_words(declaration):
    rng = random.Random(POLICY['heldout_seed']+ord(declaration['id']))
    words = []
    for i in range(POLICY['heldout_count_per_source']):
        size = POLICY['heldout_lengths'][i%5]
        if declaration['algebra']=='stack':
            # Contexts include depth4; a learner with a narrower span must refuse.
            depth, word = 0, []
            for _ in range(size):
                choices = ([0,1] if depth<4 else [])+([2] if depth else [])
                a = rng.choice(choices); word.append(a); depth += -1 if a==2 else 1
        else:
            word = [rng.randrange(declaration['arity']) for _ in range(size)]
        words.append(word)
    return words
