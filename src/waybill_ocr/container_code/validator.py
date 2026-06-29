import re


CONTAINER_PATTERN = re.compile(r"^[A-Z]{4}\d{7}$")
CODE10_PATTERN = re.compile(r"^[A-Z]{4}\d{6}$")

LETTER_VALUES = {
    "A": 10,
    "B": 12,
    "C": 13,
    "D": 14,
    "E": 15,
    "F": 16,
    "G": 17,
    "H": 18,
    "I": 19,
    "J": 20,
    "K": 21,
    "L": 23,
    "M": 24,
    "N": 25,
    "O": 26,
    "P": 27,
    "Q": 28,
    "R": 29,
    "S": 30,
    "T": 31,
    "U": 32,
    "V": 34,
    "W": 35,
    "X": 36,
    "Y": 37,
    "Z": 38,
}


def calculate_check_digit(code10: str) -> int:
    """计算 ISO 6346 箱号校验位。"""
    normalized = code10.strip().upper()
    if not CODE10_PATTERN.fullmatch(normalized):
        raise ValueError("箱号前 10 位必须为 4 位大写字母加 6 位数字")

    total = 0
    for index, char in enumerate(normalized):
        value = int(char) if char.isdigit() else LETTER_VALUES[char]
        total += value * (2**index)

    remainder = total % 11
    return 0 if remainder == 10 else remainder


def is_valid_container_code(code: str) -> bool:
    normalized = code.strip().upper()
    if not CONTAINER_PATTERN.fullmatch(normalized):
        return False

    return calculate_check_digit(normalized[:10]) == int(normalized[-1])
