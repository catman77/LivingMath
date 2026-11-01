import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from mcp_server import create_server
from native_preview008_qa import readonly_state
from research_store import ResearchStore
from typed_cycle011_public import PUBLIC_TOOLS, register_typed_tools
from typed_cycle011_server import create_typed_server
from typed_cycle011_store import install


def test_mount_rejects_canonical_hardlink_unmarked_and_wrong_binding(tmp_path):
    canonical=tmp_path/'canonical.sqlite3';store=ResearchStore(canonical)
    sandbox=tmp_path/'sandbox.sqlite3';ResearchStore(sandbox)
    before=readonly_state(canonical)
    with pytest.raises(ValueError,match='CANONICAL'):register_typed_tools(create_server(store),canonical,canonical)
    hardlink=tmp_path/'alias.sqlite3';hardlink.hardlink_to(canonical)
    with pytest.raises(ValueError,match='CANONICAL'):register_typed_tools(create_server(store),canonical,hardlink)
    with pytest.raises(ValueError,match='ISOLATED'):register_typed_tools(create_server(store),canonical,sandbox)
    other=tmp_path/'other.sqlite3';ResearchStore(other);install(sandbox,other)
    with pytest.raises(ValueError,match='BINDING_MISMATCH'):register_typed_tools(create_server(store),canonical,sandbox)
    assert readonly_state(canonical)==before


def test_real_client_mount_preserves_catalog_strict_models_and_storage(tmp_path,monkeypatch):
    monkeypatch.delenv('LIVE_MATH_TYPED_CYCLE_DB',raising=False)
    monkeypatch.setenv('LIVE_MATH_NATIVE_PREVIEW','1')
    canonical=tmp_path/'canonical.sqlite3';ResearchStore(canonical)
    sandbox=tmp_path/'sandbox.sqlite3';ResearchStore(sandbox);install(sandbox,canonical)
    baseline=create_server(ResearchStore(canonical));accepted=create_typed_server(sandbox)
    async def exercise():
        old={t.name:t.model_dump(mode='json') for t in await baseline.list_tools()}
        expected={t.name:t.model_dump(mode='json') for t in await accepted.list_tools() if t.name in PUBLIC_TOOLS}
        parameters=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).with_name('mcp_server.py')),'stdio'],
            env={'PATH':__import__('os').environ['PATH'],'LIVE_MATH_DB':str(canonical),
                 'LIVE_MATH_TYPED_CYCLE_DB':str(sandbox),'LIVE_MATH_NATIVE_PREVIEW':'1'})
        before=readonly_state(canonical);sandbox_before=readonly_state(sandbox)
        async with stdio_client(parameters) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize();listed={t.name:t.model_dump(mode='json') for t in (await client.list_tools()).tools}
                assert len(listed)==24 and all(listed[n]==t for n,t in old.items())
                assert all(listed[n]==t for n,t in expected.items())
                response=await client.call_tool('research_cycle_validate',{'project':'LM_QA_TYPED011_UNKNOWN','move_id':1,'event_id':1,'verified':True})
                assert response.isError
                response=await client.call_tool('service_health',{});data=response.structuredContent or json.loads(response.content[0].text)
                assert data['typed_cycle']['version']=='011.1' and data['audit']['ok']
                assert not {'activate','commit','execute','operator_review'} & set(listed)
        assert readonly_state(canonical)==before and readonly_state(sandbox)==sandbox_before
    asyncio.run(exercise())
