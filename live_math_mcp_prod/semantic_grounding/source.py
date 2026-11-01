"""Reuse frozen raw packets and a source prediction seal; validate disjoint reveal."""
import json
from pathlib import Path

from artifact_genesis.source import SourceVault
from .contract import independent_spans


class GroundingVault(SourceVault):
    def __init__(self, root: Path):
        super().__init__(root)
        self.cases = json.loads((root / 'frozen/decisions.json').read_text())
        self.criteria = json.loads((root / 'frozen/criteria.json').read_text())

    def reveal(self, case: dict, seal: dict, train):
        registered = next(c for c in self.cases if c['id'] == case['id'])
        if registered != case or train.id != case['train_packet']:
            raise ValueError('CASE_SOURCE_BINDING_MISMATCH')
        packet = self.packet(case['challenge_packet'], seal=seal)
        independent_spans(train, packet)
        return packet
