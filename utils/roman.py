"""
Roman numeral helpers, used because syllabus TOCs and chapter headings
mix 'UNIT I', 'UNIT 1', 'Chapter IV', etc.
"""

_ROMAN_MAP = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]

_ROMAN_RE_CHARS = set("IVXLCDM")


def is_roman_numeral(token: str) -> bool:
    token = token.strip().upper()
    if not token:
        return False
    if any(ch not in _ROMAN_RE_CHARS for ch in token):
        return False
    try:
        roman_to_int(token)
        return True
    except ValueError:
        return False


def roman_to_int(s: str) -> int:
    s = s.strip().upper()
    if not s:
        raise ValueError("empty roman numeral")
    i = 0
    result = 0
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    prev = 0
    for ch in reversed(s):
        if ch not in values:
            raise ValueError(f"invalid roman numeral char: {ch}")
        val = values[ch]
        if val < prev:
            result -= val
        else:
            result += val
            prev = val
    if result <= 0:
        raise ValueError("invalid roman numeral")
    return result


def int_to_roman(num: int) -> str:
    result = []
    for value, symbol in _ROMAN_MAP:
        while num >= value:
            result.append(symbol)
            num -= value
    return "".join(result)


def normalize_unit_number(token: str):
    """Return an int for tokens like 'I', 'IV', '1', '12' else None."""
    token = token.strip().upper().rstrip(".")
    if token.isdigit():
        return int(token)
    if is_roman_numeral(token):
        return roman_to_int(token)
    return None
