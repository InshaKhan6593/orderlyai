"""Short, customer-facing order codes (e.g. ``K7Q2X9``).

The customer never sees the raw per-business sequence (``orders.order_no``) — a small "#2"
both looks unprofessional and leaks how many orders a business has taken. Instead we show a
6-character code from an unambiguous alphabet (no ``0 O 1 I L``) that a customer can read back
over WhatsApp.

The code is **derived from** the internal counter, not random: ``code = base31((order_no *
MULT + business_salt) mod 31**6)``. Multiplying by a value coprime to ``31**6`` is a bijection,
so within a business distinct ``order_no``s always map to distinct codes — uniqueness is
guaranteed by construction, with **no collision-retry and no race** (the counter is already
assigned atomically). A per-business salt makes two businesses' first orders look different.
The map is one-way for our purposes: we store the code in a column and look orders up by it, so
nothing here needs to be reversed.
"""
from __future__ import annotations

import uuid

# 31 unambiguous characters (dropped 0 O 1 I L). 31 is prime, so any multiplier not divisible
# by 31 is coprime to 31**6 and therefore a bijection modulo the code space.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_BASE = len(ALPHABET)            # 31
_WIDTH = 6
_SPACE = _BASE ** _WIDTH         # 31**6 = 887,503,681 distinct codes per business
_MULT = 387420489                # 3**18 — coprime to 31**6; scatters consecutive order numbers


def business_salt(business_id: uuid.UUID) -> int:
    """A stable per-business offset so different tenants' order #1 don't share a code."""
    return int.from_bytes(business_id.bytes, "big") % _SPACE


def encode_order_code(order_no: int, *, salt: int = 0) -> str:
    """The 6-char code for one order. Unique per business for any ``order_no`` in ``[1, 31**6)``
    (far more than any business will ever reach; beyond that it would wrap and is not supported).
    """
    n = (order_no * _MULT + salt) % _SPACE
    out: list[str] = []
    for _ in range(_WIDTH):
        n, r = divmod(n, _BASE)
        out.append(ALPHABET[r])
    return "".join(reversed(out))
