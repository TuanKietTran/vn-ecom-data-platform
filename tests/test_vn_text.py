import unicodedata

import pytest

from vnecom.text import vn


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.299.000₫", 1_299_000),
        ("₫89,000", 89_000),
        ("89.000 đ", 89_000),
        ("159000", 159_000),
        (159000.0, 159_000),
        ("1,2tr", 1_200_000),
        ("250k", 250_000),
        ("2.5 triệu", 2_500_000),
        ("", None),
        (None, None),
        ("liên hệ", None),
        (-5, None),
    ],
)
def test_parse_vnd(raw, expected):
    assert vn.parse_vnd(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Đã bán 1,2k", (1200, True)),
        ("Đã bán 10k+", (10_000, True)),
        ("Đã bán 856", (856, False)),
        ("2,5tr", (2_500_000, True)),
        ("1.234", (1234, False)),
        (42, (42, False)),
        ("sold 3k", (3000, True)),
        ("1.2K sold", (1200, True)),
        ("5,6k lượt bán", (5600, True)),
        (None, (None, False)),
    ],
)
def test_parse_sold(raw, expected):
    assert vn.parse_sold(raw) == expected


def test_diacritics_and_d_bar():
    assert vn.strip_diacritics("Điện thoại Sạc dự phòng đẹp") == "Dien thoai Sac du phong dep"


def test_nfd_and_nfc_normalise_to_same_key():
    title = "Nồi chiên không dầu Sunhouse 5L"
    assert vn.normalize_title(unicodedata.normalize("NFD", title)) == vn.normalize_title(title)


def test_title_norm_strips_promo_noise():
    a = vn.normalize_title("[CHÍNH HÃNG] 【Freeship】 Tai nghe Bluetooth JBL Tune")
    b = vn.normalize_title("(Hàng chính hãng) Tai nghe Bluetooth JBL Tune")
    assert a == b == "tai nghe bluetooth jbl tune"
