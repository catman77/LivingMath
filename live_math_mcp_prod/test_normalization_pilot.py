from normalization_pilot import create_task, make_prompt, oracle, ENCODING, TOKENS


def test_hidden_state_oracle_has_two_distinct_usable_measurements_and_independent_solution():
    for i in range(4):
        result=oracle(i)
        assert result['implementations_agree']
        assert len(set(result['losses']))>1
        assert len(set(result['residual_error']))>1
        assert all(len(state)==4 for state,weight in result['support'])


def test_pilot_inputs_have_equal_token_budgets_without_ready_predictions(tmp_path):
    for i in range(4):
        task=create_task(tmp_path,i)
        for mode in 'ABCD':
            text=make_prompt(task,mode)
            assert len(ENCODING.encode(text))==TOKENS
            assert 'best_tests' not in text and 'losses' not in text and 'residual_error' not in text
            assert all(tid in text for tid in task['test_ids'])
        assert task['view']['status']=='COMPLETE'
