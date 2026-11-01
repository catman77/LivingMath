import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from bridge.canonical import read_json
from bridge.intake import ROOT
from bridge.pilot import load_fixture


@pytest.fixture
def fixture():
    envelope, source = load_fixture('poetry')
    return envelope, source, read_json(ROOT / 'fixtures/trust.json'), read_json(ROOT / 'eval/settings.json')
