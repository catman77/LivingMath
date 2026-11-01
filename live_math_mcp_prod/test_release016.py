"""016 contract guards; no t15 target values are evaluated in unit tests."""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import zipfile
import pytest
from release016_math import identity, binding_sha, score, ratio, validate_inputs, ARCHIVE_SHA
from real_xi015_source import load_native


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    root = tmp_path_factory.mktemp('source016')
    archive = Path(os.environ.get('LM_RELEASE016_ARCHIVE', str(Path(__file__).parent.parent / 'docs/RH_XI_ROUTES_EXPORT_001.zip')))
    from checkout_test_support import native_source
    native_source(root, archive)
    return load_native(root)


def test_original_source_address_is_not_local_renumbering():
    assert identity(3, '+') == {'index': 4, 'origin_id': 2,
        'source_address': {'cell': 0, 'node': 0, 'n': 3, 'branch': '+'}}
    assert identity(4, '-')['index'] == 7
    with pytest.raises(ValueError):
        identity(5, '+')


def test_source_rename_and_rebind_are_different():
    row = {**identity(3, '+'), 'h': '.0005', 't': '15', 'definition_sha256': ARCHIVE_SHA}
    assert binding_sha(row) == binding_sha({**row, 'display_label': 'new display'})
    for key, value in [('origin_id', 3), ('h', '.002'), ('t', '14'), ('definition_sha256', '0' * 64)]:
        assert binding_sha(row) != binding_sha({**row, key: value})


def test_overlap_is_not_containment():
    predicted = {'re': ['0.9999999999999999999999999999999999999999999', '1.0000000000000000000000000000000000000000001'], 'im': ['0', '0']}
    actual = {'re': ['0.9999999999999999999999999999999999999999998', '1'], 'im': ['0', '0']}
    result = score(predicted, actual)
    assert result['overlap_PASS'] and not result['containment_PASS']


def test_n_step_and_denominator_guards(native):
    with pytest.raises(ValueError, match='N_GUARD'):
        ratio(native, {'u': ['.1', '.1']}, 4)
    with pytest.raises(ValueError, match='UNPROVEN_NONZERO'):
        ratio(native, {'u': ['-1', '-1']}, 1)


def test_target_anchor_is_denied_before_any_inference():
    # Metadata-only negative control; no invented Xi values.
    target = {**identity(3, '+'), 'h': '0', 't': '15'}
    inputs = {'t': '15', 'archive_sha256': ARCHIVE_SHA, 'node': dict.fromkeys(
        ['u', 'quadrature_weight', 'cell', 'node', 'id', 'exact_u']), 'anchors': [target] * 8,
        'pre_registration_sha256': '0' * 64, 'legacy_frame': {}}
    with pytest.raises(ValueError, match='TARGET_ANCHOR_FORBIDDEN'):
        validate_inputs(inputs)


def test_unregistered_input_table_is_denied():
    with pytest.raises(ValueError, match='INPUT_NOT_ALLOWLISTED'):
        validate_inputs({'t': '15', 'archive_sha256': ARCHIVE_SHA, 'target_amplitudes': []})
