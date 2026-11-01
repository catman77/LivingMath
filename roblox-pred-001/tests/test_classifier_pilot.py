from pathlib import Path

import pytest
import yaml

from roblox_pred.classifier_pilot import classify, clean_description, assign_components, model_input
from roblox_pred.classifier_benchmark import score_rows, features

CONFIG=yaml.safe_load((Path(__file__).parents[1]/'configs/classifier-pilot.yaml').read_text())


def example(**changes):
    r=dict(universe_id=1,title='Original unit game',description='Explore an original maze, solve its puzzles and cooperate with your friends to escape.',
        launch_date_proxy='2020-01-01T00:00:00Z',observed_at='2026-11-02T00:00:00Z',
        current_players=0,visits_total=100,creator_key='User:1',genre='Adventure')
    r.update(changes);return r


def test_mature_low_reach_is_negative_proxy():
    r=classify(example(),CONFIG['labels'])
    assert r['label']==0 and r['activity_class']=='LOW_TRACTION_MATURE'


def test_zero_online_with_past_reach_is_not_failed_launch():
    r=classify(example(visits_total=3000000),CONFIG['labels'])
    assert r['label'] is None and r['activity_class']=='DORMANT_HIGH_REACH'


def test_new_or_missing_audience_is_not_negative():
    for change in [{'current_players':None},{'launch_date_proxy':'2026-11-01T00:00:00Z'}]:
        assert classify(example(**change),CONFIG['labels'])['label'] is None


def test_default_and_empty_descriptions_not_training_negatives():
    for desc in ['', 'This is your very first Roblox creation. Check it out and build more worlds.']:
        assert classify(example(description=desc),CONFIG['labels'])['label'] is None


def test_raw_description_retained_but_promo_counter_not_feature():
    text='Solve the maze together.\nThank you for 10 million visits!\nBuild new paths.'
    row=classify(example(description=text),CONFIG['labels'])
    assert row['description']==text
    assert 'million' not in clean_description(text) and 'maze' in clean_description(text)


def test_grouping_transitive_creator_and_clone():
    rows=[{'creator_key':'a','model_description':'Original mystery maze with friends and cooperative puzzles.'},
          {'creator_key':'b','model_description':'Original mystery maze with friends and cooperative puzzles.'},
          {'creator_key':'b','model_description':'A completely different economic simulation collecting minerals.'}]
    assign_components(rows,.92)
    assert len({r['split_group'] for r in rows})==1


def test_model_inputs_and_predictor_frame_exclude_labels_and_audience():
    row=classify(example(current_players=4000),CONFIG['labels']);row['case_id']='case-1'
    assert not {'label','current_players','visits_total','creator_key','split_group'} & model_input(row).keys()
    assert not {'label','current_players','visits_total'} & set(features([row]).columns)


def test_scorer_requires_exact_blind_test_coverage():
    rows=[{'case_id':'a','label':0},{'case_id':'b','label':1}]
    assert score_rows(rows,[{'case_id':'a','score':.1},{'case_id':'b','score':.9}])['balanced_accuracy']==1
    with pytest.raises(ValueError,match='COVERAGE'):
        score_rows(rows,[{'case_id':'a','score':.1},{'case_id':'a','score':.9}])
    with pytest.raises(ValueError,match='INVALID_PROBABILITY'):
        score_rows(rows,[{'case_id':'a','score':float('nan')},{'case_id':'b','score':.9}])


def test_api_zero_id_placeholder_remains_unavailable_not_negative():
    from datetime import UTC, datetime
    from roblox_pred.classifier_pilot import filter_zero_placeholders
    from roblox_pred.sources import normalize
    payload,count=filter_zero_placeholders({'data':[{'id':0,'playing':0}]},[42])
    assert count==1 and payload['data']==[]
    games,rows=normalize(payload,[42],datetime.now(UTC),{'response_sha256':'a'*64},'unit','UNIT_ONLY')
    assert not games and rows[0].current_players is None and rows[0].status=='UNAVAILABLE_UNKNOWN'
    with pytest.raises(ValueError,match='RESPONSE_BINDING'):
        filter_zero_placeholders({'data':[{'id':43}]},[42])


def test_current_audience_proxy_preserves_past_success_subtype():
    settings={**CONFIG['labels'],'target_mode':'CURRENT_AUDIENCE','low_activity_max_ccu':100}
    row=classify(example(current_players=80,visits_total=3000000),settings)
    assert row['label']==0 and row['activity_class']=='LOW_ACTIVITY_PAST_REACH'
    assert 'launch' not in row['label_basis'].lower()
    assert classify(example(current_players=101),settings)['label'] is None
