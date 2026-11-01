from datetime import timedelta

import pytest

from roblox_pred.evaluation import temporal_split, train_threshold
from test_temporal_leakage import sample


def rows():
    out=[]
    for i,day in enumerate([0, 10, 180, 190, 360, 370]):
        s=sample(); shift=timedelta(days=day)
        s=s.model_copy(update={'sample_id': 's'+str(i), 'universe_id': i+1, 'creator_key': 'User:'+str(i+1),
            'as_of':s.as_of+shift,'creator_known_at':s.creator_known_at+shift,
            'features':{k:v.model_copy(update={'known_at':v.known_at+shift,'source_observed_at':v.source_observed_at+shift}) for k,v in s.features.items()},
            'outcome_window_start':s.outcome_window_start+shift,'horizon_end':s.horizon_end+shift,
            'outcome_available_at':s.outcome_available_at+shift})
        out.append(s)
    return out


def test_temporal_split_is_forward_and_group_disjoint():
    ss=rows(); folds=temporal_split(ss, ss[0].as_of, [0,60], [151,211], [302,400],91)
    assert [len(folds[k]) for k in ['train','validation','test']] == [2,2,2]


@pytest.mark.parametrize('field', ['creator_key','clone_group_id'])
def test_cross_fold_creator_or_clone_never_silently_dropped(field):
    ss=rows()
    for i in [0, -1]:
        update = {field: 'same'}
        if field == 'clone_group_id':
            update['clone_known_at'] = ss[i].as_of
        ss[i] = ss[i].model_copy(update=update)
    with pytest.raises(ValueError, match='GROUP_OVERLAP'):
        temporal_split(ss,ss[0].as_of,[0,60],[151,211],[302,400],91)


def test_labels_must_be_available_before_next_fold():
    ss=rows();ss[0]=ss[0].model_copy(update={'outcome_available_at':ss[2].as_of+timedelta(days=1)})
    with pytest.raises(ValueError,match='LABEL_NOT_AVAILABLE'):
        temporal_split(ss,ss[0].as_of,[0,60],[151,211],[302,400],91)


def test_threshold_only_uses_train_and_requires_contrast():
    assert train_threshold([0,1,2,3,4,5,6,7,8,9],.1)==pytest.approx(8.1)
    with pytest.raises(ValueError,match='NO_OUTCOME_CONTRAST'):train_threshold([1,1,1],.1)
