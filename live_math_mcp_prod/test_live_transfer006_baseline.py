from live_transfer006_worlds import create_world,frame
from live_transfer006_baselines import old_pair,old_attention
from live_transfer006_oracle import attention


def test_unchanged005_accepts_the_explicitly_conditioned_mod5_adapter(tmp_path):
    w=create_world(tmp_path/'source.sqlite3',0);f=frame(w)
    pair=old_pair(w,f,w['refs']['h0'],w['refs']['h3'])
    assert pair['output']['status']=='NEW_DISTINCTION'
    assert pair['actual_function_calls']['register_state']>0
    assert old_attention(w,f)['output']['test_id']==attention(w['history'],w['query'])['selected_test_id']
