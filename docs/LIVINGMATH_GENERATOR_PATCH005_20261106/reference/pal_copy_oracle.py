"""Independent finite reference for structural PAL/COPY candidate semantics.

NOT the production LivingMath generator, and NOT proof of unique inference.
Operators interpreted: split, reverse, literal word equality, guarded descent.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence, Tuple, Dict, Any

Word = Tuple[str, ...]


def split(w: Word, at: int) -> tuple[Word, Word]:
    if not 0 <= at <= len(w):
        raise ValueError("split out of bounds")
    return (w[:at], w[at:])


def reverse(w: Word) -> Word:
    return tuple(reversed(w))


def literal_word_equality(x: Word, y: Word) -> bool:
    return x == y


def eval_pal_recursive(w: Word, *, max_tokens: int = 8) -> tuple[bool | None, list[dict[str, Any]]]:
    """P(eps)=P(a)=True; P(a u b) = (a==b) AND P(u).
    None = unknown outside bound. Traces re-executable, no hidden predicate.
    """
    if len(w) > max_tokens:
        return None, []
    cur=w; trace=[]
    while len(cur) >= 2:
        first, rest=split(cur,1)
        middle,last=split(rest,len(rest)-1)
        reverse_first, _=split(reverse(cur),1)
        equal=literal_word_equality(first,reverse_first)
        trace.append({"input":list(cur),"first":list(first),"inner":list(middle),
                      "last":list(last),"reversed_first":list(reverse_first),"equal":equal})
        if not equal:
            return False,trace
        if len(middle)!=len(cur)-2:
            raise AssertionError("measure not strictly decreasing")
        cur=middle
    return True,trace


def eval_copy_halves(w: Word, *, max_tokens: int=8) -> tuple[bool | None,dict[str, Any]]:
    if len(w)>max_tokens:
        return None,{}
    if len(w)%2:
        return False,{"input":list(w),"guard":"odd_length"}
    left,right=split(w,len(w)//2)
    return literal_word_equality(left,right),{"input":list(w),"left":list(left),"right":list(right)}


def verify_pal_trace(w: Word, outcome: bool | None, trace: list[dict[str,Any]], *, max_tokens: int=8) -> bool:
    actual, expected_trace=eval_pal_recursive(w,max_tokens=max_tokens)
    return outcome == actual and trace == expected_trace


def words(n: int, alpha: tuple[str,...]=("S","P")):
    import itertools
    return [tuple(xs) for xs in itertools.product(alpha, repeat=n)]


def labelled_data(lengths: Sequence[int], *, task: str="PAL"):
    for n in lengths:
        for w in words(n):
            pred=(w==tuple(reversed(w))) if task=="PAL" else (len(w)%2==0 and w[:n//2]==w[n//2:])
            yield {"word":"".join(w),"length":n,"accepted":pred}


def candidate_ast() -> dict:
    return {"composition":"iterate_on_inner_fragment", "trim_left":1,"trim_right":1,
            "fragment_operations":["SPLIT","SPLIT"],"relation":{
                "composition":"aligned_token_equality", "base_max_tokens":1,
                "left_operations":["SPLIT"],"right_operations":["REVERSE","SPLIT"],
                "offset":0,"expected_equal":True}}


def train_errors(train: list[dict]) -> list[str]:
    wrong=[]
    for row in train:
        answer,_=eval_pal_recursive(tuple(row["word"]))
        if answer!=row["accepted"]:
            wrong.append(row["word"])
    return wrong

if __name__=="__main__":
    for lengths in ([4], [2,4], [1,2,3,4], [1,3,5], [2,4,6]):
        train=list(labelled_data(lengths))
        print(lengths,"samples",len(train),"positive",sum(x["accepted"] for x in train),"errors",len(train_errors(train)))
