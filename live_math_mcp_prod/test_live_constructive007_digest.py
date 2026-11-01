import os,subprocess,sys
from pathlib import Path


def test_native_definition_digest_is_independent_of_python_hash_seed():
    source=Path(__file__).resolve().parent
    program='from live_constructive007_native import native_fingerprint;print(native_fingerprint())'
    values=[subprocess.check_output([sys.executable,'-c',program],cwd=source,env={**os.environ,'PYTHONHASHSEED':str(seed)},text=True).strip() for seed in (1,2,7,19)]
    assert len(set(values))==1,values


def test_native_digest_does_not_depend_on_constant_reference_counts():
    import live_constructive007_native as native
    before=native.native_fingerprint()
    retained=[f.__code__.co_consts for f in (native.native_admissible,native.native_extend,native.native_observe)]
    after=native.native_fingerprint()
    assert before==after,(before,after,retained)
