import pytest

from waybill_ocr.container_code.validator import (
    calculate_check_digit,
    is_valid_container_code,
)


def test_calculate_check_digit_for_known_code():
    assert calculate_check_digit("HNKU633179") == 5


def test_valid_container_code():
    assert is_valid_container_code("HNKU6331795") is True


def test_invalid_check_digit():
    assert is_valid_container_code("HNKU6331794") is False


def test_invalid_format():
    assert is_valid_container_code("HINKU6331795") is False


def test_calculate_check_digit_rejects_invalid_prefix():
    with pytest.raises(ValueError, match="前 10 位"):
        calculate_check_digit("HNKU63317")
