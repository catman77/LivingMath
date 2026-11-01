from pathlib import Path
import pytest
from live_constructive007_qa import ensure_fresh


@pytest.mark.parametrize('marker',['run-failures.json','pytest.txt','worker.txt','local86','run-state.json'])
def test_even_failed_cohort_is_refused_before_any_output_overwrite(tmp_path,marker):
    target=tmp_path/marker
    if marker=='local86':target.mkdir()
    else:target.write_text('preserve original')
    with pytest.raises(SystemExit):ensure_fresh(tmp_path)
    if target.is_file():assert target.read_text()=='preserve original'
