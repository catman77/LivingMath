"""Stream the archival Xi JSON: only one edge/origin record is decoded at a time."""
import json


class Reader:
    def __init__(self,stream):
        self.stream=stream;self.buffer='';self.pos=0;self.eof=False;self.decoder=json.JSONDecoder()
    def more(self):
        self.buffer=self.buffer[self.pos:];self.pos=0
        block=self.stream.read(65536);self.buffer+=block;self.eof=not block
    def peek(self):
        while True:
            while self.pos<len(self.buffer) and self.buffer[self.pos].isspace():self.pos+=1
            if self.pos<len(self.buffer):return self.buffer[self.pos]
            if self.eof:return ''
            self.more()
    def take(self,char):
        if self.peek()!=char:raise ValueError('JSON_DELIMITER:'+char)
        self.pos+=1
    def value(self):
        self.peek()
        while True:
            try:
                value,end=self.decoder.raw_decode(self.buffer,self.pos)
                if end==len(self.buffer) and not self.eof:self.more();continue
                self.pos=end;return value
            except json.JSONDecodeError:
                if self.eof:raise
                self.more()
    def array(self):
        self.take('[');index=0
        while self.peek()!=']':
            yield index;index+=1
            if self.peek()==',':self.take(',')
            elif self.peek()!=']':raise ValueError('JSON_ARRAY')
        self.take(']')
    def keys(self):
        self.take('{')
        while self.peek()!='}':
            key=self.value();self.take(':');yield key
            if self.peek()==',':self.take(',')
            elif self.peek()!='}':raise ValueError('JSON_OBJECT')
        self.take('}')


def records(path):
    with open(path,encoding='utf-8') as stream:
        reader=Reader(stream)
        for key in reader.keys():
            if key in {'source_nodes','origins'}:
                for index in reader.array():yield key,index,reader.value()
            elif key=='cases':
                for case in reader.array():
                    for field in reader.keys():
                        if field=='edges':
                            for index in reader.array():yield 'edge',case,reader.value()
                        else:yield 'case_meta',case,(field,reader.value())
            else:yield 'meta',key,reader.value()
