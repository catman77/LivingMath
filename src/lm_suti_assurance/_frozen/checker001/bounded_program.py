"""Reviewed QA program: rotate a four-bit word left by one. Domain 0..15."""

def rotate_left(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 15:
        raise ValueError('FOUR_BIT_DOMAIN')
    return ((value << 1) & 15) | (value >> 3)
