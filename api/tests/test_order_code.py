"""Customer-facing order codes: short, unambiguous, and unique per business by construction."""
from __future__ import annotations

import uuid

from app.core.order_code import ALPHABET, business_salt, encode_order_code


def test_alphabet_is_unambiguous_and_prime_length():
    assert len(ALPHABET) == 31  # prime → any non-multiple-of-31 multiplier is a bijection
    for bad in "01OIL":
        assert bad not in ALPHABET  # the look-alikes a customer would mistype are excluded
    assert len(set(ALPHABET)) == len(ALPHABET)  # no duplicates


def test_code_is_six_chars_from_the_alphabet():
    code = encode_order_code(1, salt=business_salt(uuid.uuid4()))
    assert len(code) == 6
    assert all(c in ALPHABET for c in code)


def test_codes_are_unique_within_a_business():
    # The whole point: consecutive order numbers never collide for one business.
    salt = business_salt(uuid.uuid4())
    codes = {encode_order_code(n, salt=salt) for n in range(1, 5001)}
    assert len(codes) == 5000


def test_consecutive_orders_do_not_look_sequential():
    salt = business_salt(uuid.uuid4())
    assert encode_order_code(1, salt=salt) != encode_order_code(2, salt=salt)
    # The derivation scatters, so #1 and #2 don't share a long common prefix.
    a, b = encode_order_code(1, salt=salt), encode_order_code(2, salt=salt)
    assert a[:3] != b[:3]


def test_same_order_number_differs_across_businesses():
    a = encode_order_code(1, salt=business_salt(uuid.uuid4()))
    b = encode_order_code(1, salt=business_salt(uuid.uuid4()))
    # Two different businesses' first orders almost certainly differ (per-business salt).
    assert a != b


def test_encoding_is_deterministic():
    bid = uuid.uuid4()
    assert encode_order_code(7, salt=business_salt(bid)) == encode_order_code(7, salt=business_salt(bid))
