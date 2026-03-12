# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Messaging Module

This module provides:
- PII (Personally Identifiable Information) detection in text content
- Text sanitization by replacing detected PII with safe placeholders
- 6 compiled regex patterns: Email, Turkish Phone, TCKN, VKN, Turkish IBAN, URL
- TCKN checksum validation (algorithmic, matching kyc_profile.py)
- Context-aware VKN detection (phone numbers take priority over 10-digit matches)
"""

from tradehub_compliance.tradehub_compliance.messaging.pii_scanner import (
    scan_for_pii,
    sanitize_message,
)

__all__ = [
    'scan_for_pii',
    'sanitize_message',
]
