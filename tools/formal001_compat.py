"""Opt-in regression view: retain83 exact legacy schemas, validate8 new names."""

NAMES = {
    "formal_" + n
    for n in [
        "store",
        "synthesize",
        "inspect",
        "verify",
        "contrast",
        "interpret",
        "model_check",
        "replay",
    ]
}


def legacy_view(tools):
    assert NAMES <= tools.keys(), "MISSING_FORMAL_TOOL"
    return {n: v for n, v in tools.items() if n not in NAMES}
