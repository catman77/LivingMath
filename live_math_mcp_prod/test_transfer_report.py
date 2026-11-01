import hashlib
import json
from pathlib import Path

from qa_positive_acceptance import snapshot
from research_store import ResearchStore
import transfer_report


def test_archived_source_hash_reference_does_not_claim_available_bytes(tmp_path):
    import pytest
    audit = transfer_report.archived_causal_audit(tmp_path)
    assert set(audit['source_check_methods'].values()) == {'HASH_REFERENCE_ONLY_BYTES_NOT_DISTRIBUTED'}
    assert set(audit['files']) == {'report.md', 'RCA.md', 'model_outputs.jsonl'}
    (tmp_path / 'report.md').write_text('changed original')
    with pytest.raises(ValueError, match='ARCHIVED_CAUSAL_SOURCE_DRIFT'):
        transfer_report.archived_causal_audit(tmp_path)


def test_report_export_handles_a_regression_log_alongside_its_directory(tmp_path, monkeypatch):
    original_glob = Path.glob
    def files_first(path, pattern, **kwargs):
        entries = original_glob(path, pattern, **kwargs)
        return iter(sorted(entries, key=lambda p: not p.is_file())) if pattern == 'regression-*' else entries
    monkeypatch.setattr(Path, 'glob', files_first)
    db = tmp_path / 'research.sqlite3'
    ResearchStore(db)
    base = tmp_path / 'private';base.mkdir()
    report = tmp_path / 'report'
    password = tmp_path / 'owner';password.write_text('unit-secret-never-exported')
    monkeypatch.setattr(transfer_report, 'configure', lambda: {'LIVE_MATH_DATA_DIR': str(tmp_path), 'LIVE_MATH_PASSWORD_FILE': str(password)})
    root = Path(transfer_report.__file__).resolve().parents[1]
    data = {
        'metadata.json': {'report': str(report), 'code_before': {}, 'auth_mode': 'unit fixture',
            'AGENTS_sha256': hashlib.sha256((root / 'AGENTS.md').read_bytes()).hexdigest(),
            'endpoint': 'https://unit.invalid/mcp', 'codex_version': 'unit',
            'backup_sha256': hashlib.sha256(db.read_bytes()).hexdigest()},
        'before.json': snapshot(db), 'cost.json': {}, 'failures.json': [], 'stage.json': {'stage': 'unit'},
        'preflight.json': {'rh_frontier': {}}, 'postflight.json': {'rh_frontier': {}},
        'controls.json': [{'result': 'PASS'}] * 10,
    }
    (base / 'research-before.sqlite3').write_bytes(db.read_bytes())
    for name, value in data.items():
        (base / name).write_text(json.dumps(value))
    (base / 'regression-log.txt').write_text('not a directory')
    prompts = base / 'frozen-prompts';prompts.mkdir()
    frozen = prompts / 'input.txt';frozen.write_text('immutable input');frozen.chmod(0o444)
    regression = base / 'regression-unit';regression.mkdir()
    (regression / 'result.json').write_text(json.dumps({'result': 'PASS', 'pass_count': 86}))
    result = transfer_report.export(base)
    assert result['existing_MCP_regression']['passed'] == 86
    assert (report / 'report.md').exists() and (report / 'artifact-sha256.json').exists()
    transfer_report.export(base)
    assert (report / 'frozen-prompts/input.txt').read_text() == 'immutable input'
