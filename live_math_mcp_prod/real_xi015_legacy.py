"""Actual archived training observations through the unchanged006/007 interface."""
import json
from dataclasses import dataclass
from live_transfer006_source import Frame


class Ledger:
    def __init__(self):self.trace=[];self.counts={};self.stage='training-source-read'
    def charge(self,name,amount=1):
        self.counts[name]=self.counts.get(name,0)+amount
        self.trace.append({'stage':self.stage,'operation':name,'count':amount})
    def summary(self):return {'stage':self.stage,'calls':self.counts}


class TrainingPort:
    def __init__(self,data,ledger):self.data=data;self.ledger=ledger;self.trace=ledger.trace;self.counts=ledger.counts
    def load(self,word):self.ledger.charge('published_anchor_load');return self.data[word[0]]
    def observe(self,state,observer):
        self.ledger.charge('published_anchor_observe');return json.dumps(state['value'],sort_keys=True,separators=(',',':'))
    def admissible(self,state,action):raise ValueError('UNSEALED_NATIVE_QUERY_FORBIDDEN')
    def extend(self,state,action):raise ValueError('UNSEALED_NATIVE_QUERY_FORBIDDEN')


@dataclass
class XiTrainingFrame(Frame):
    data:dict=None
    ledger:object=None
    def port(self,max_calls=2048,seconds=2):return TrainingPort(self.data,self.ledger)
