#!/usr/bin/env python3
"""Offline score of frozen observed old endpoint_equal hypothesis. No server access."""
import json
from pathlib import Path
corpus=[
    ("ABCCBA",True),("ABCBCA",False),("ABCABC",False),
    ("ABBAABBA",True),("AABBAA",True),("ABABBA",False),
    ("BAABAB",False),("AAAAAA",True),("ABABAB",False),
]
observed_old=[True,True,False,True,True,True,True,True,False]
assert len(corpus)==len(observed_old)==9
assert all((w==w[::-1])==truth for w,truth in corpus)
fail=[w for (w,y),p in zip(corpus,observed_old) if p!=y]
report={"test":"heldout_palindrome_9_unique", "correct":len(corpus)-len(fail), "total":len(corpus), "accuracy":(len(corpus)-len(fail))/len(corpus),"false_positive_words":fail,"truth_source":"offline test construction", "prediction_source":"2026-11-05 LivingMath frozen endpoint_equal model"}
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report['correct']==6 and report['total']==9
