"""Independent014 storage gate. Installer requires a private011-marked copy."""
from normalizer import digest
from research_store import ResearchStore
from typed_cycle011_store import assert_isolated,connect

SQL={name:'CREATE TRIGGER '+name+' BEFORE '+operation+' ON '+table+
     " BEGIN SELECT RAISE(ABORT,'law014 append-only'); END"
     for table in ('events','operations') for operation in ('UPDATE','DELETE')
     for name in [table+'_014_no_'+operation.lower()]}


def install(database):
    assert_isolated(database)
    store=ResearchStore(database)
    with connect(database,True) as c:
        existing=dict(c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
        if all(existing.get(n)==sql for n,sql in SQL.items()):return {'idempotent':True}
        for name,sql in SQL.items():
            if name in existing and existing[name]!=sql:raise ValueError('TRIGGER_DEFINITION_CONFLICT')
            if name not in existing:c.execute(sql)
        store._audit(c,'law014_append_only_installed',{'definitions_sha256':digest(SQL),'authority':'isolated operator'})
    return {'idempotent':False,'definitions_sha256':digest(SQL)}
