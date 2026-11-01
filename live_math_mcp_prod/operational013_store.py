"""Additional SQL immutability for operator-created013 QA databases only."""
from normalizer import digest
from research_store import ResearchStore
from typed_cycle011_store import assert_isolated,connect


def install_append_only(database):
    """Four guards, no data rewrite or schema-version change; never run from MCP."""
    assert_isolated(database)
    definitions={table+'_013_no_'+action.lower():
        'CREATE TRIGGER '+table+'_013_no_'+action.lower()+' BEFORE '+action+' ON '+table+
        " BEGIN SELECT RAISE(ABORT,'operational013 append-only'); END"
        for table in ('events','operations') for action in ('UPDATE','DELETE')}
    store=ResearchStore(database)
    with connect(database,True) as c:
        existing={r[0]:r[1] for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")}
        if all(existing.get(name)==sql for name,sql in definitions.items()):return {'installed':False,'idempotent':True}
        for name,sql in definitions.items():
            if name in existing and existing[name]!=sql:raise ValueError('APPEND_ONLY_TRIGGER_DEFINITION_CONFLICT')
            if name not in existing:c.execute(sql)
        store._audit(c,'operational013_append_only_installed',{'trigger_definition_sha256':digest(definitions),'authority':'isolated QA operator'})
    return {'installed':True,'idempotent':False,'trigger_definition_sha256':digest(definitions)}
