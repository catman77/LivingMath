from bridge.demos import g, independent_oracles, poetry, pythagoras, reversible_inverse, reversible_step


def test_poetic_order_is_model_not_reader_truth():
    a = poetry(['read_A', 'read_B']);b = poetry(['read_B', 'read_A'])
    assert a['coordinates'] == [4, 3] and b['coordinates'] == [3, 4]
    assert a['reader_semantics'] == b['reader_semantics'] == 'UNKNOWN'
    assert a['reference_six_readings'] == 'NOT_REPRODUCED'


def test_pythagoras_exact_and_two_questions():
    result = pythagoras('orthogonality')
    assert result['invariant'] and result['orthogonal_dot'] == 0
    assert result['q_sum'] == '25'
    assert all(result['exact_checks'].values())
    other = pythagoras('quadratic')
    assert result['model'] != other['model']
    assert other['model']['q_rotation_invariant']
    assert other['model']['rotated_vector'] == ['-7/5', '24/5']


def test_pair_bijective_but_body_observation_not_injective():
    assert all(reversible_inverse(reversible_step((a, b))) == (a, b)
               for a in range(256) for b in range(256))
    assert len({g(x) for x in range(256)}) < 256
    assert (1, 5) != (2, 5) and (1, 5)[1] == (2, 5)[1]
