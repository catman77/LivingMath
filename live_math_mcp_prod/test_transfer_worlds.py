import itertools

from transfer_worlds import atoms, base_value, canonical_atoms, reference_base, render, world


def test_all_finite_sources_have_independent_evaluators():
    for index in range(9):
        w = world(index, 0)
        assert len(w['theories']) == 5
        for bits in itertools.product((0, 1), repeat=4):
            assert base_value(index, bits) == reference_base(index, bits)
        assert w['target'] not in {0, 15}
        assert len({tuple(t['predictions']) for t in w['theories']}) == 4


def test_both_treatments_contain_exactly_the_same_atoms():
    for i in range(9):
        for repeat in (0, 1):
            for time in (0, 1):
                facts = atoms(world(i, repeat), time)
                assert canonical_atoms(render(facts, 'F'), 'F') == canonical_atoms(render(facts, 'S'), 'S')


def test_cosmetic_renaming_preserves_numerical_source_and_negative_intervention():
    for i in range(9):
        a, b = world(i, 0), world(i, 1)
        assert a['source_id'] != b['source_id']
        assert a['coefficients'] == b['coefficients']
        assert a['target'] == b['target']
        assert a['costs'] == b['costs']
        assert [t['predictions'] for t in a['theories']] == [t['predictions'] for t in b['theories']]


def test_adverse_intervention_preserves_physical_data_and_independent_branch():
    for i in range(9):
        w = world(i, 0)
        a, b = atoms(w, 0), atoms(w, 1)
        retained = set(w['features'][:4]) | {w['independent_id']}
        assert canonical_atoms(render([f for f in a if f[0] in retained], 'F'), 'F') == canonical_atoms(render([f for f in b if f[0] in retained], 'S'), 'S')
