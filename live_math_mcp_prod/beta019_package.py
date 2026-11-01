"""Signed minimal beta distribution; no015/016/RH ZIP/Bridge/data credentials."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption

SOURCE = Path(__file__).resolve().parent


def closure() -> list[str]:
    modules = {p.stem: p for p in SOURCE.glob('*.py')}
    todo = [p.stem for p in SOURCE.glob('beta019*.py')] + [
        'test_beta019', 'test_beta019_admin', 'test_engine017', 'test_deploy018', 'test_deploy018_bounds', 'test_deploy018_http',
        'engine017_operator', 'engine017_server', 'http_server', 'typed_cycle011_operator', 'native_preview008_worker']
    found = set()
    while todo:
        name = todo.pop()
        if name in found or name not in modules:
            continue
        found.add(name)
        for node in ast.walk(ast.parse(modules[name].read_text())):
            if isinstance(node, ast.Import):
                todo.extend(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                todo.append(node.module.split('.')[0])
    if any('015' in name or '016' in name or 'bridge' in name.lower() for name in found):
        raise ValueError('019_UNREVIEWED_SCIENCE_OR_BRIDGE_DISTRIBUTION')
    return sorted(found)


def build(out: Path, private: Path, frozen017: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    target = out / 'source'; target.mkdir()
    for module in closure():
        shutil.copy2(SOURCE / (module + '.py'), target / (module + '.py'))
    for name in ('normalization-schema.json', 'native_preview008-adapters.json', 'live_core005-contract.json',
                 'live_transfer006-contract.json', 'live_constructive007-contract.json'):
        shutil.copy2(SOURCE / name, target / name)
    shutil.copytree(SOURCE / 'migrations', target / 'migrations')
    shutil.copytree(SOURCE / 'external019', target / 'external019')
    shutil.copy2(SOURCE / 'requirements-019.lock', out / 'requirements.lock')
    frozen = out / 'frozen017'; frozen.mkdir()
    shutil.copy2(frozen017 / 'pre-registration.json', frozen / 'pre-registration.json')
    (out / 'README.md').write_text('''# LivingMath1.0.0b1 — private beta019

Новый экземпляр, новая база, Python3.12/3.13 Linux x86_64. Production не обновляется. Постоянный адрес отложен владельцем; временный loopback TLS/OAuth допустим. Bridge отсутствует.

Проверьте SHA ZIP и fingerprint release-public.pem по независимому отчёту оператора. Подпись self-managed operator обеспечивает целостность, не независимую сертификацию автора.

`python3 source/beta019_install.py --package . --root /tmp/lm019-install install` устанавливает locked dependencies с pip --require-hashes и применяет018 guards только в новой beta DB. Повтор идемпотентен.

Полный пример: `bash reproduce.sh /tmp/lm019-NEW-work`. Work path должен отсутствовать. Пример включает настоящий HTTPS/OAuth/PKCE, исходный публичный NFA, server-owned I/T, отдельные owner/executor, signed receipt, negative controls, restart и exact-snapshot restore с SIGKILL.120s максимум на отдельный опыт,1GiB worker; dependency setup учитывается отдельно. Модель/API OpenAI не вызываются.

При независимом запуске historical86 — SKIP_NO_PRIVATE_SNAPSHOT. Подлинные рабочие SQLite/RH ZIP не входят в пакет. Portable регрессии выполняются отдельно. Граф source операций взят из automata-lib9.2.0 MIT, исходные docs/LICENSE/code сохранены в source/external019. Координаты — фиксированное инъективное кодирование; observer acceptance теряет различение q0/empty. Отказ языка — обычное значение observer0, не ERROR. Успех — вычислительный результат, proof_status всегда unverified.

Прямое выполнение исходной формулы является baseline. Превосходство и автономное открытие не заявляются. Unknown adapter/law/C4 не получают разрешения. Регистрация только local reviewed owner, MCP не принимает executable code/path/plugin.

Uninstall: остановить beta process, `python3 source/beta019_install.py --package . --root /tmp/lm019-install uninstall`. Удаляются только code/venv; state/seals/exports и вся история остаются. Повтор install возвращает код без перезаписи ledger. Restore допускается только для exact snapshot, без новых событий после backup; исходный state сохраняется в отдельном namespace. Никакого rollback путём удаления новых данных.

Релизный статус определяется внешним report/result/readiness-v2, не наличием этого README. R5a blocking, R5b DEFERRED_BY_OWNER. Production R4/R5 и прежние science NO_GO не переписываются.
''')
    (out / 'api-contract.md').write_text('''# API019

Transport: existing MCP Streamable HTTP/TLS+OAuth research scope, private pinned CA. Default-off24 legacy tools; --enable019 gives27. Core health version0.4.2/schema5; research_contract.http018.version=1.0.0b1 and protocol=livingmath-research019/v1 identify the beta capability layer. Address is not a release invariant.

research_cycle_next(query), research_cycle_preview(request), research_cycle_precommit(request,request_key), research_cycle_validate(project,move_id,event_id), research_novelty_snapshot(request), research_cycle_history(project), research_source_contract(project). Query017 data fields retain project/source_id/version/observer/context_level/display_label; caller history/labels do not own novelty. Registered adapters: accepted017 affine/permutation/stack plus automata-nfa019/v1. SourceEnvelope017 carries hashes/scope/version/rights/provenance/unknowns; generic envelope is independent of any future semantic bridge. Unknown adapters require explicit owner code review; no dynamic loader.

PROPOSAL_READY never grants execution. Local owner audit/activation issues scoped expiring018 nonce; separate beta019_executor performs actual upstream NFA; owner beta019_operator commit atomically appends receipt/journal/projection/nonce consumption. COMPLETED does not mean mathematical truth. Generic model activation/complete returns MCP isError plus structured error.code=018_OPERATOR_AUTHORITY_REQUIRED, permission=false. Malformed/foreign/stale/signed tamper is REJECTED with precise reason. C4 or unsupported/source rebinding is INSUFFICIENT_CONTEXT. Noninformative finite domains honestly stop; INCONCLUSIVE/ERROR retain uncertainty and wait for owner attention.

Private entrypoint: python code/beta019_http.py --data STATE --typed STATE/beta.sqlite3 --origin https://localhost:PORT --port PORT --cert CERT --key TLSKEY --password PASSFILE --enable019. Owner pre-start reconcile is automatic before sandbox/mount. No executor private key is made readable by MCP. Native definitions pin installed upstream code and reviewed adapter; SHA/signature is not physical authenticity or proof. Closed historical receipt inspection does not revive a lease.
''')
    (out / 'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
TASK_PACKAGE=$(cd -- "$(dirname -- "$0")" && pwd)
TASK_PYTHON=${PYTHON:-python3}
exec "$TASK_PYTHON" "$TASK_PACKAGE/source/beta019_reproduce.py" --package "$TASK_PACKAGE" --work "${1:?Specify a NEW private work path}"
''')
    key_file = private / 'release-signing-key.ed25519'
    if not key_file.exists():
        key = Ed25519PrivateKey.generate()
        with key_file.open('xb') as stream:
            stream.write(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()))
        key_file.chmod(0o600)
    key = Ed25519PrivateKey.from_private_bytes(key_file.read_bytes())
    (out / 'release-public.pem').write_bytes(key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))
    fingerprint = hashlib.sha256(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).hexdigest()
    manifest = {'version': '1.0.0b1', 'scope': 'private beta candidate; no production authorization',
        'public_key_fingerprint_sha256': fingerprint, 'source_modules': closure(), 'source_license': 'external019 MIT with original notice',
        'files': {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}}
    raw = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    (out / 'release-manifest.json').write_bytes(raw); (out / 'release.sig').write_bytes(key.sign(raw))
    archive = out.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():
                z.write(p, str(Path(out.name) / p.relative_to(out)))
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    return {'package': str(out), 'archive': str(archive), 'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'signing_public_key_fingerprint': fingerprint, 'files': len(manifest['files']) + 2}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', type=Path, required=True); parser.add_argument('--private', type=Path, required=True); parser.add_argument('--frozen017', type=Path, required=True)
    a = parser.parse_args(); print(json.dumps(build(a.out, a.private, a.frozen017), ensure_ascii=False))
