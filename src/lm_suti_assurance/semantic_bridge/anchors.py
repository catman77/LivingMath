"""Exact UTF-8 byte anchors. LF is navigation only; no Unicode/text repair."""
from ..core import byte_digest
from ..errors import AssuranceError
from .records import seal, validate


def line_index(text):
    rows=[];offset=0
    for number, line in enumerate(text.encode('utf-8').split(b'\n'),1):
        rows.append({'line_number':number,'byte_start':offset,'byte_end':offset+len(line),
                     'quote_utf8':line.decode('utf-8')})
        offset += len(line)+1
    return rows


def make_anchor(project, edition_ref, edition, source, quote):
    if not isinstance(quote,str) or not quote:
        raise AssuranceError('SOURCE_ANCHOR_MISMATCH')
    raw=source['content_utf8'].encode('utf-8');needle=quote.encode('utf-8')
    start=raw.find(needle)
    if start<0 or raw.find(needle,start+1)>=0:
        raise AssuranceError('SOURCE_ANCHOR_MISMATCH',details={'cause':'QUOTE_MISSING_OR_AMBIGUOUS'})
    value=seal('source-anchor',project,edition['source_snapshot_digest'],{
        'source_ref':edition['source_ref'],'edition_ref':edition_ref,'source_sha256':source['sha256'],
        'byte_start':start,'byte_end':start+len(needle),'quote_utf8':quote,'quote_sha256':byte_digest(needle),
        'unit':'source_utf8_bytes','line_index_rule':'LF_EXACT_UTF8_V1','line_number':raw[:start].count(b'\n')+1},
        origin='TRUSTED_CONTEXT',producer=edition_ref,parents=[edition_ref])
    check_anchor(value,source,edition_ref)
    return value


def check_anchor(value, source, edition_ref=None):
    validate('source-anchor',value)
    raw=source['content_utf8'].encode('utf-8')
    valid=(type(value['byte_start']) is int and type(value['byte_end']) is int
           and 0<=value['byte_start']<value['byte_end']<=len(raw)
           and value['source_sha256']==source['sha256']==byte_digest(raw)
           and raw[value['byte_start']:value['byte_end']]==value['quote_utf8'].encode('utf-8')
           and value['quote_sha256']==byte_digest(value['quote_utf8'].encode('utf-8'))
           and (edition_ref is None or value['edition_ref']==edition_ref))
    if not valid:
        raise AssuranceError('SOURCE_ANCHOR_MISMATCH')
    return True
