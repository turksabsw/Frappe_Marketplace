# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Anonymous Buyer ID Generator

Generates deterministic, non-reversible anonymous buyer IDs for buyer-seller pairs
using HMAC-SHA256 with Base30 encoding. IDs are cached in Redis with TTL=3600s.

Security Properties:
- Deterministic: same buyer-seller pair always gets same ID (within TTL)
- Non-reversible: cannot derive buyer identity from anonymous ID
- Seller-specific: same buyer gets different IDs for different sellers
- Rotatable: secret rotation invalidates all cached IDs (Redis TTL expires naturally)
"""

import hmac
import hashlib
from typing import Optional

import frappe
from frappe import _


# Base30 alphabet excluding I, O, 0, 1, 8, 9 for readability
BASE30_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ234567"
BASE30_SIZE = len(BASE30_ALPHABET)  # 30

# Anonymous ID format: BYR-XXXXXX (6 chars from Base30)
ANON_ID_PREFIX = "BYR-"
ANON_ID_LENGTH = 6

# Redis key patterns
CACHE_KEY_TEMPLATE = "trade_hub:anon_buyer:{buyer}:{seller}"
REVERSE_KEY_TEMPLATE = "trade_hub:anon_id:{anon_id}"

# Redis TTL in seconds (1 hour)
CACHE_TTL = 3600

# Maximum collision retries before raising an error
MAX_COLLISION_RETRIES = 10


def generate_anonymous_buyer_id(buyer_user: str, seller_user: str) -> str:
    """
    Generate a deterministic anonymous buyer ID for a buyer-seller pair.

    The ID is computed via HMAC-SHA256 and encoded using a Base30 alphabet
    to produce a human-readable BYR-XXXXXX identifier. Results are cached
    in Redis with a 3600s TTL.

    Args:
        buyer_user: The buyer's user identifier (e.g. email or user ID)
        seller_user: The seller's user identifier (e.g. email or user ID)

    Returns:
        Anonymous buyer ID in BYR-XXXXXX format

    Raises:
        frappe.ValidationError: If buyer_user or seller_user is empty
        frappe.ValidationError: If anonymous_buyer_id_secret is not configured
        frappe.ValidationError: If collision resolution fails after max retries
    """
    if not buyer_user or not seller_user:
        frappe.throw(_("Both buyer and seller user identifiers are required"))

    # Step 1: Check Redis cache
    cache_key = CACHE_KEY_TEMPLATE.format(buyer=buyer_user, seller=seller_user)
    cached = frappe.cache().get_value(cache_key, expires=True)
    if cached:
        return cached

    # Step 2: Read secret from site config
    secret = _get_hmac_secret()

    # Step 3: Compute HMAC-SHA256 and encode to Base30
    message = f"{buyer_user}:{seller_user}"
    anon_id = _compute_anonymous_id(secret, message)

    # Step 4: Collision detection with counter fallback
    anon_id = _resolve_collisions(
        anon_id, secret, message, buyer_user, seller_user
    )

    # Step 5: Store in Redis with TTL
    _store_in_cache(cache_key, anon_id, buyer_user, seller_user)

    return anon_id


def _get_hmac_secret() -> str:
    """
    Read the HMAC secret from site configuration.

    Returns:
        The HMAC secret string

    Raises:
        frappe.ValidationError: If secret is not configured
    """
    secret = getattr(frappe.conf, "anonymous_buyer_id_secret", None)
    if not secret:
        frappe.throw(
            _("anonymous_buyer_id_secret is not configured in site_config.json")
        )
    return secret


def _compute_hmac_digest(secret: str, message: str) -> bytes:
    """
    Compute HMAC-SHA256 digest.

    Args:
        secret: The HMAC secret key
        message: The message to sign

    Returns:
        Raw HMAC-SHA256 digest bytes
    """
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).digest()


def _encode_base30(digest: bytes, length: int = ANON_ID_LENGTH) -> str:
    """
    Encode raw bytes to Base30 alphabet string.

    Converts the digest bytes to an integer, then repeatedly divides
    by the alphabet size to extract characters.

    Args:
        digest: Raw bytes to encode
        length: Number of characters to produce

    Returns:
        Base30-encoded string of specified length
    """
    # Convert bytes to integer for base conversion
    num = int.from_bytes(digest, byteorder="big")

    chars = []
    for _ in range(length):
        num, remainder = divmod(num, BASE30_SIZE)
        chars.append(BASE30_ALPHABET[remainder])

    return "".join(chars)


def _compute_anonymous_id(secret: str, message: str) -> str:
    """
    Compute the anonymous ID from secret and message.

    Args:
        secret: HMAC secret key
        message: The message to hash (buyer_user:seller_user)

    Returns:
        Anonymous ID in BYR-XXXXXX format
    """
    digest = _compute_hmac_digest(secret, message)
    encoded = _encode_base30(digest)
    return f"{ANON_ID_PREFIX}{encoded}"


def _resolve_collisions(
    anon_id: str,
    secret: str,
    message: str,
    buyer_user: str,
    seller_user: str
) -> str:
    """
    Check for collisions and resolve using counter fallback.

    A collision occurs when a different buyer-seller pair produces the same
    BYR-XXXXXX ID. When detected, a counter suffix is appended to the
    message and re-hashed until a unique ID is found.

    Args:
        anon_id: The initially computed anonymous ID
        secret: HMAC secret key
        message: Original message (buyer_user:seller_user)
        buyer_user: The buyer's user identifier
        seller_user: The seller's user identifier

    Returns:
        A collision-free anonymous ID

    Raises:
        frappe.ValidationError: If collision cannot be resolved within max retries
    """
    for counter in range(MAX_COLLISION_RETRIES):
        # Check if this anonymous ID is already mapped to a different pair
        reverse_key = REVERSE_KEY_TEMPLATE.format(anon_id=anon_id)
        existing_pair = frappe.cache().get_value(reverse_key, expires=True)

        if not existing_pair:
            # No collision — this ID is available
            return anon_id

        # Check if the existing mapping is for the same buyer-seller pair
        expected_pair = f"{buyer_user}:{seller_user}"
        if existing_pair == expected_pair:
            # Same pair, same ID — no collision
            return anon_id

        # Collision detected: different pair has same ID
        frappe.log_error(
            f"Anonymous buyer ID collision detected: {anon_id} "
            f"(counter={counter})",
            "Anonymous Buyer ID Collision"
        )

        # Re-hash with counter suffix
        collision_message = f"{message}:{counter + 1}"
        digest = _compute_hmac_digest(secret, collision_message)
        encoded = _encode_base30(digest)
        anon_id = f"{ANON_ID_PREFIX}{encoded}"

    # Exhausted retries
    frappe.throw(
        _("Failed to generate unique anonymous buyer ID after {0} attempts").format(
            MAX_COLLISION_RETRIES
        )
    )


def _store_in_cache(
    cache_key: str,
    anon_id: str,
    buyer_user: str,
    seller_user: str
) -> None:
    """
    Store the anonymous ID mapping in Redis with TTL.

    Stores both forward (buyer:seller → anon_id) and reverse (anon_id → pair)
    mappings for collision detection.

    Args:
        cache_key: The forward cache key
        anon_id: The anonymous buyer ID
        buyer_user: The buyer's user identifier
        seller_user: The seller's user identifier
    """
    pair_value = f"{buyer_user}:{seller_user}"
    reverse_key = REVERSE_KEY_TEMPLATE.format(anon_id=anon_id)

    # Forward mapping: buyer:seller → anonymous ID
    frappe.cache().set_value(cache_key, anon_id, expires_in_sec=CACHE_TTL)

    # Reverse mapping: anonymous ID → buyer:seller pair (for collision detection)
    frappe.cache().set_value(reverse_key, pair_value, expires_in_sec=CACHE_TTL)
