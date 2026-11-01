"""Documented public transport with explicit collection/analysis scope and bounded IO."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time

import httpx

from roblox_pred.config import SourcePolicy, authorize, digest
from roblox_pred.schemas import Game, Snapshot


class RobloxPublicSource:
    endpoint = 'https://games.roblox.com/v1/games'

    def __init__(self, policy: SourcePolicy, root: Path, limits: dict, client=None):
        self.policy, self.root, self.limits = policy, root, limits
        self.client = client
        self.calls = 0
        self.started = time.monotonic()

    def fetch(self, universe_ids: list[int]) -> tuple[list[Game], list[Snapshot], dict]:
        if not universe_ids or len(universe_ids) > 50:
            raise ValueError('REGISTERED_PUBLIC_SOURCE_AND_BOUNDED_UNIVERSES_REQUIRED')
        if len(set(universe_ids)) != len(universe_ids) or any(type(x) is not int or x <= 0 for x in universe_ids):
            raise ValueError('INVALID_UNIVERSE_IDENTITIES')
        payload, receipt = self.get_public_json('/v1/games', {'universeIds': ','.join(map(str, universe_ids))})
        receipt['requested_universe_ids'] = universe_ids
        observed = datetime.fromisoformat(receipt['observed_at'])
        games, snapshots = normalize(payload, universe_ids, observed, receipt, self.policy.source_id,
                                     self.policy.authorization_sha256 or '')
        return games, snapshots, receipt

    def get_public_json(self, path: str, params: dict) -> tuple[dict, dict]:
        import re
        authorize(self.policy, self.root, collect=True)
        if self.policy.family != 'ROBLOX_PUBLIC' or not re.fullmatch(
                r'/v1/games|/v2/groups/[1-9][0-9]*/gamesV2|/v2/users/[1-9][0-9]*/games', path):
            raise ValueError('UNDOCUMENTED_OR_PRIVATE_ENDPOINT')
        if path != '/v1/games' and params.get('accessFilter') != 'Public':
            raise ValueError('PUBLIC_CATALOG_FILTER_REQUIRED')
        if self.calls >= self.limits['max_requests'] or time.monotonic()-self.started >= self.limits['max_total_seconds']:
            raise ValueError('SOURCE_REQUEST_BUDGET_EXHAUSTED')
        if self.calls:
            time.sleep(self.limits['interval_seconds'])
        self.calls += 1
        client = self.client or httpx.Client(timeout=self.limits['timeout_seconds'], follow_redirects=False)
        try:
            with client.stream('GET', 'https://games.roblox.com'+path, params=params,
                    headers={'User-Agent': 'LivingMath-ROBLOX-PRED-001/0.1 authorized-aggregate-collector'}) as response:
                status = response.status_code
                if status == 429:
                    raise ValueError('RATE_LIMIT_STOP_RETRY_AFTER:' + response.headers.get('Retry-After', 'UNKNOWN'))
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if time.monotonic()-self.started >= self.limits['max_total_seconds']:
                        raise ValueError('SOURCE_TOTAL_TIME_BOUND')
                    if len(raw) > self.limits['max_response_bytes']:
                        raise ValueError('SOURCE_RESPONSE_BYTE_BOUND')
                captured = datetime.now(UTC)
                receipt = {'source_id': self.policy.source_id, 'url': str(response.url), 'http_status': status,
                    'observed_at': captured.isoformat(), 'response_sha256': hashlib.sha256(raw).hexdigest(),
                    'server_date': response.headers.get('Date'),
                    'automatic_retries': 0}
        finally:
            if self.client is None: client.close()
        folder = self.root / 'data' / 'raw' / 'captures'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / (receipt['response_sha256'] + '.json')
        if path.exists() and path.read_bytes() != bytes(raw):
            raise ValueError('IMMUTABLE_CAPTURE_DRIFT')
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(raw)
            path.chmod(0o600)
        receipt['raw_capture_path'] = str(path.relative_to(self.root))
        return json.loads(raw), receipt


def normalize(payload: dict, universe_ids: list[int], observed: datetime, receipt: dict,
              source_id: str, license_ref: str) -> tuple[list[Game], list[Snapshot]]:
    """Creation/updated dates never become release evidence or text-version timestamps."""
    raw_rows = payload['data']
    if len({r['id'] for r in raw_rows}) != len(raw_rows) or any(r['id'] not in universe_ids for r in raw_rows):
        raise ValueError('SOURCE_UNIVERSE_RESPONSE_BINDING')
    by_id = {r['id']: r for r in raw_rows}; games = []; snapshots = []
    for uid in universe_ids:
        row = by_id.get(uid)
        provenance = {**receipt, 'object_address': 'data[id='+str(uid)+']',
            'release_date_assurance': 'NOT_ESTABLISHED', 'usage_scope': 'OPERATOR_AUTHORIZED_ONLY'}
        rid = digest([source_id, uid, observed.isoformat(), receipt['response_sha256']])
        if row is None:
            snapshots.append(Snapshot(record_id=rid, universe_id=uid, observed_at=observed, ingested_at=observed,
                source_id=source_id, status='UNAVAILABLE_UNKNOWN', source_license=license_ref,
                source_sha256=receipt['response_sha256'], source_provenance=provenance))
            continue
        creator = row.get('creator') or {}
        games.append(Game(record_id=rid, universe_id=uid, creator_id=creator.get('id'),
            creator_type=creator.get('type', 'UNKNOWN'), creation_date=row.get('created'),
            known_at=observed, source_id=source_id, source_license=license_ref,
            genre=row.get('genre'), source_provenance=provenance))
        snapshots.append(Snapshot(record_id=rid, universe_id=uid, observed_at=observed, ingested_at=observed,
            source_id=source_id, title=row.get('name'), description=row.get('description'),
            thumbnail_ref=None, visits_total=row.get('visits'), current_players=row.get('playing'),
            favorites=row.get('favoritedCount'), likes=None, dislikes=None, status='OBSERVED',
            source_license=license_ref, source_sha256=receipt['response_sha256'], source_provenance=provenance))
    return games, snapshots
