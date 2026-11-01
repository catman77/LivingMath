"""Narrow014 extension of011: real singleton prediction, explicit purpose, ≤4 actions."""
from typing import Literal
from pydantic import Field
from native_preview008_contract import NativeQuestion,NativeRequest,Checksum
from typed_cycle011_contract import CyclePrecommit,MeasurementEnvelope,Text
from typed_cycle011_contract import ReceiptRequest
from research_engine010_contract import Readout

ADAPTER='source014-native/v1'


class Readout014(Readout):
    admissibility:list[bool]=Field(max_length=4)


class ReceiptRequest014(ReceiptRequest):
    observed:Readout014


class Question014(NativeQuestion):
    max_suffix_length:Literal[4]=4


class Request014(NativeRequest):
    question:Question014


class Precommit014(CyclePrecommit):
    schema_version:Literal['cycle-precommit014/v1']='cycle-precommit014/v1'
    native_request:Request014
    expected_readout:Readout014
    alternatives:list[dict]=Field(min_length=1,max_length=32)
    suffix:list[Text]=Field(min_length=1,max_length=4)
    suffix_ordinals:list[int]=Field(min_length=1,max_length=4)
    admissibility_guard:list[bool]=Field(min_length=1,max_length=4)
    purpose:Literal['DISCRIMINATE','VALIDATE_TRANSFER']
    law_fingerprint:Checksum
    context_word:list[int]=Field(max_length=3)
    expected_coordinate:list[int]|None=None


class Envelope014(MeasurementEnvelope):
    schema_version:Literal['bound-measurement014/v1']='bound-measurement014/v1'
    predictions:list[dict]=Field(min_length=1,max_length=32)
    observed:Readout014
    suffix:list[Text]=Field(min_length=1,max_length=4)
    suffix_ordinals:list[int]=Field(min_length=1,max_length=4)
    purpose:Literal['DISCRIMINATE','VALIDATE_TRANSFER']
    law_fingerprint:Checksum
    context_word:list[int]=Field(max_length=3)
    observed_coordinate:list[int]
