"""Optional schema QA: pip install -r requirements-qa.txt, then run this file."""
from copy import deepcopy
import json
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


def main():
    for name in ['white_star_request.schema.json', 'formal_model.schema.json']:
        Draft202012Validator.check_schema(read('contracts/'+name))
    validator = Draft202012Validator(read('contracts/white_star_request.schema.json'))
    for name in ['blok_request.json', 'original_request.json']:
        validator.validate(read('fixtures/'+name))
    tools = read('contracts/proposed_tools.json')['tools']
    for tool in tools:
        Draft202012Validator.check_schema(tool['inputSchema'])
    call = read('fixtures/mcp_blok_call.json')['params']
    schema = next(t['inputSchema'] for t in tools if t['name'] == call['name'])
    Draft202012Validator(schema).validate(call['arguments'])
    mutations = [
        lambda q: q['encoding']['protocol'].__setitem__('steps', True),
        lambda q: q.__setitem__('eval', '1+1'),
        lambda q: q['encoding']['concepts'][0].__setitem__('coordinates', [1.5, 2]),
        lambda q: q['encoding']['protocol'].__setitem__('optimizer_feedback', True),
    ]
    for mutation in mutations:
        item = deepcopy(call['arguments']['request']); mutation(item)
        try:
            validator.validate(item)
        except ValidationError:
            continue
        raise AssertionError('invalid input admitted')
    print('PASS: 2 schemas, 2 fixtures, 6 tool input schemas, MCP arguments, 4 invalid inputs')


if __name__ == '__main__':
    main()
