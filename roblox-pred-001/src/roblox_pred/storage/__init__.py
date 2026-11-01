"""Append-only typed Parquet parts with a small DuckDB index, private to this pilot."""
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from roblox_pred.config import digest
from roblox_pred.schemas import ConceptArtifact, Game, Outcome, Prediction, Run, SemanticFeatures, Snapshot

MODELS = {'games': Game, 'snapshots': Snapshot, 'concept_artifacts': ConceptArtifact,
          'outcomes': Outcome, 'semantic_features': SemanticFeatures, 'predictions': Prediction, 'runs': Run}
TS = pa.timestamp('us', tz='UTC')
STR, INT, NUM = pa.string(), pa.int64(), pa.float64()
COLUMNS = {
    'games': [('universe_id', INT), ('creator_id', INT), ('creation_date', TS), ('release_date', TS),
              ('release_precision', STR), ('genre', STR), ('known_at', TS), ('source_id', STR), ('source_license', STR)],
    'snapshots': [('universe_id', INT), ('observed_at', TS), ('ingested_at', TS), ('source_id', STR),
        ('title', STR), ('description', STR), ('thumbnail_ref', STR), ('visits_total', INT), ('current_players', INT),
        ('favorites', INT), ('likes', INT), ('dislikes', INT), ('status', STR), ('source_license', STR)],
    'concept_artifacts': [('universe_id', INT), ('known_at', TS), ('source_observed_at', TS), ('source_id', STR),
        ('source_license', STR), ('source_sha256', STR), ('text', STR), ('artifact_kind', STR)],
    'outcomes': [('universe_id', INT), ('as_of', TS), ('window_start', TS), ('window_end', TS),
                 ('metric', STR), ('raw_measure', NUM), ('success', pa.bool_())],
    'semantic_features': [('sample_id', STR), ('extractor_version', STR), ('mcp_version', STR),
                         ('feature_schema', STR), ('known_at', TS), ('status', STR)],
    'predictions': [('experiment_id', STR), ('model_id', STR), ('fold', STR), ('sample_id', STR),
                    ('score', NUM), ('calibrated_probability', NUM), ('as_of', TS)],
    'runs': [('experiment_id', STR), ('git_commit', STR), ('config_sha256', STR),
             ('dataset_manifest_sha256', STR), ('seed', INT), ('status', STR)]}


class Store:
    def __init__(self, directory: Path, database: Path | None = None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = Path(database or self.directory / 'research.duckdb').resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        for table in MODELS:
            schema = self.schema(table)
            with duckdb.connect(str(self.database)) as connection:
                columns = ', '.join('"'+f.name+'" '+self.sql_type(f.type) for f in schema)
                connection.execute('CREATE TABLE IF NOT EXISTS '+table+' ('+columns+', PRIMARY KEY(record_id))')

    @staticmethod
    def schema(table: str) -> pa.Schema:
        if table not in MODELS:
            raise ValueError('UNKNOWN_TYPED_TABLE')
        return pa.schema([pa.field('record_id', STR, nullable=False),
            *[pa.field(name, kind) for name, kind in COLUMNS[table]], pa.field('payload_json', STR, nullable=False)])

    @staticmethod
    def sql_type(kind) -> str:
        if pa.types.is_timestamp(kind): return 'TIMESTAMPTZ'
        if pa.types.is_integer(kind): return 'BIGINT'
        if pa.types.is_floating(kind): return 'DOUBLE'
        if pa.types.is_boolean(kind): return 'BOOLEAN'
        return 'VARCHAR'

    def append(self, table: str, records: list) -> dict:
        schema = self.schema(table); normalized = {}
        for record in records:
            value = MODELS[table].model_validate(record.model_dump() if hasattr(record, 'model_dump') else record)
            encoded = value.model_dump_json()
            if value.record_id in normalized and normalized[value.record_id][0] != encoded:
                raise ValueError('APPEND_ONLY_RECORD_CONFLICT')
            normalized[value.record_id] = (encoded, value)
        pending = []
        with duckdb.connect(str(self.database)) as connection:
            connection.execute('BEGIN TRANSACTION')
            try:
                for key, (encoded, value) in sorted(normalized.items()):
                    old = connection.execute('SELECT payload_json FROM '+table+' WHERE record_id=?', [key]).fetchone()
                    if old:
                        if old[0] != encoded: raise ValueError('APPEND_ONLY_RECORD_CONFLICT')
                        continue
                    pending.append({'record_id': key, **{n: getattr(value, n) for n, _ in COLUMNS[table]},
                                    'payload_json': encoded})
                if not pending:
                    connection.execute('COMMIT'); return {'inserted': 0, 'replayed': len(normalized)}
                batch = pa.Table.from_pylist(pending, schema=schema)
                folder = self.directory / table; folder.mkdir(exist_ok=True)
                part = folder / (digest([r['payload_json'] for r in pending]) + '.parquet')
                if part.exists():
                    if pq.read_table(part).to_pylist() != batch.to_pylist():
                        raise ValueError('IMMUTABLE_PARQUET_DRIFT')
                else:
                    pq.write_table(batch, part, compression='zstd')
                    part.chmod(0o600)
                connection.register('_incoming', batch)
                connection.execute('INSERT INTO '+table+' SELECT * FROM _incoming')
                connection.execute('COMMIT')
                return {'inserted': len(pending), 'replayed': len(normalized)-len(pending), 'part': str(part)}
            except BaseException:
                connection.execute('ROLLBACK'); raise

    def rows(self, table: str) -> list:
        self.schema(table)
        with duckdb.connect(str(self.database), read_only=True) as connection:
            rows = connection.execute('SELECT payload_json FROM '+table+' ORDER BY record_id').fetchall()
        return [MODELS[table].model_validate_json(row[0]) for row in rows]

    def manifest(self) -> dict:
        import hashlib
        return {str(p.relative_to(self.directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.directory.rglob('*.parquet'))}
