# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Anonymization Module

This module provides:
- HMAC-SHA256 anonymous buyer ID generation
- Redis-cached deterministic buyer-seller pair identifiers
- Collision detection with counter fallback
- Base30 encoding for human-readable anonymous IDs (BYR-XXXXXX)
"""

from tradehub_compliance.tradehub_compliance.anonymization.anonymous_buyer import (
    generate_anonymous_buyer_id,
)

__all__ = [
    'generate_anonymous_buyer_id',
]
