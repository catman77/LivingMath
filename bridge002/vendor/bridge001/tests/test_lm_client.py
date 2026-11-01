import asyncio

import pytest

from bridge.canonical import Refusal
from bridge.lm_client import ReadOnlyClient


class TransportMustNotRun:
    async def call_tool(self, *args):
        raise AssertionError('Unsafe request reached transport')


def client():
    catalog = {'tools': [{'name': 'research_context', 'annotations': {'readOnlyHint': True},
                         'inputSchema': {'type': 'object', 'properties': {'project': {'type':'string'}}, 'required':['project'], 'additionalProperties':False}}]}
    return ReadOnlyClient(TransportMustNotRun(), catalog, {'BRIDGE_QA_test'}, max_calls=2)


@pytest.mark.parametrize('name', ['record_result','research_cycle_precommit','activate','commit','transition_research_move','execute','attend','interpret'])
def test_mutations_blocked_before_transport(name):
    with pytest.raises(Refusal, match='READ_ONLY_BOUNDARY'):
        asyncio.run(client().call(name, {'project':'BRIDGE_QA_test'}))


@pytest.mark.parametrize('project', ['RH','soft-ftl','BRIDGE_QA_other','LM_QA_TYPED011_any'])
def test_unauthorized_project_denied(project):
    with pytest.raises(Refusal, match='UNAUTHORIZED_PROJECT'):
        asyncio.run(client().call('research_context', {'project':project}))


def test_exact_server_schema_validation():
    with pytest.raises(Refusal, match='SCHEMA'):
        asyncio.run(client().call('research_context', {'project':'BRIDGE_QA_test','unknown':'field'}))


def test_no_source_adapter_means_no_native_call(fixture):
    env, *_ = fixture
    result = client().native_preview(env)
    assert result['status'] == 'UNSUPPORTED_SOURCE'
    assert result['native_call_sent'] is False
    assert not result['execution_permission']['allowed']


def test_wire_supports_actual_anyio_stream_context(tmp_path):
    import anyio
    from bridge.lm_client import Wire
    async def exercise():
        send, receive = anyio.create_memory_object_stream(1)
        async with Wire(send, tmp_path / 'wire.jsonl', 'request') as sender:
            assert sender.stream is send
        async with Wire(receive, tmp_path / 'wire.jsonl', 'response') as reader:
            assert reader.stream is receive
    asyncio.run(exercise())


def test_explicit_write_hint_denied():
    c = client();c.catalog['research_context']['annotations']['readOnlyHint'] = False
    with pytest.raises(Refusal, match='NOT_NEGOTIATED'):
        asyncio.run(c.call('research_context', {'project':'BRIDGE_QA_test'}))


def test_legacy_absent_hint_uses_reviewed_allowlist():
    class Response:
        def model_dump(self, **kwargs):
            return {'isError':False,'structuredContent':{'events':[]}}
    class Session:
        async def call_tool(self, name, arguments):
            assert name == 'research_context' and arguments == {'project':'BRIDGE_QA_test'}
            return Response()
    c = client();c.session = Session();c.catalog['research_context']['annotations'] = None
    response = asyncio.run(c.call('research_context', {'project':'BRIDGE_QA_test'}))
    assert response['structuredContent']['events'] == []
    assert c.calls[0]['read_only_basis'] == 'EXPLICIT_REVIEWED_RC020_ALLOWLIST'
