"""Roman numeral parsing/conversion for unit numbering (e.g. syllabus "UNIT IV")."""
import re

_ROMAN_MAP = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_RE = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def is_roman_numeral(text: str) -> bool:
    text = text.strip().upper()
    return bool(text) and bool(_ROMAN_RE.match(text))


def roman_to_int(text: str) -> int:
    text = text.strip().upper()
    if not is_roman_numeral(text):
        raise ValueError(f"Not a valid roman numeral: {text!r}")
    total = 0
    prev = 0
    for ch in reversed(text):
        value = _ROMAN_MAP[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def int_to_roman(number: int) -> str:
    if not (0 < number < 4000):
        raise ValueError("int_to_roman only supports 1-3999")
    values = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    result = []
    for value, symbol in values:
        count, number = divmod(number, value)
        result.append(symbol * count)
    return "".join(result)


def parse_unit_number(label: str) -> "int | None":
    """Extract a unit number from labels like 'UNIT IV', 'Unit 4', 'UNIT-III'."""
    match = re.search(r"UNIT\s*[-:]?\s*([IVXLCDM]+|\d+)", label, re.IGNORECASE)
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        return int(token)
    if is_roman_numeral(token):
        return roman_to_int(token)
    return None
