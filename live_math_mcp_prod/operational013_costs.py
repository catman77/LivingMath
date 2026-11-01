"""Optional operator-local accounting of every typed-controller native query."""
import itertools
import json
import os
from pathlib import Path
import time
from operational013_native import Ledger

_IDS=itertools.count()


class AuditedLedger(Ledger):
    def __init__(self,limit=20000):
        super().__init__(limit);self.identifier=next(_IDS)

    def charge(self,operation,**fields):
        super().charge(operation,**fields)
        filename=os.environ.get('LM013_COST_LEDGER')
        if filename:
            row={'process':os.getpid(),'ledger':self.identifier,'monotonic_ns':time.monotonic_ns(),**self.rows[-1]}
            with Path(filename).open('a') as stream:stream.write(json.dumps(row,separators=(',',':'))+'\n')
