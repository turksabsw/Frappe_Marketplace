# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
PII Scanner for TradeHub Messaging

Detects and sanitizes Personally Identifiable Information (PII) in text content.
Used by Masked Message DocType (before_insert) to ensure no PII leaks through
the anonymous messaging system.

Supported PII types:
- Email addresses
- Turkish phone numbers (+90 / 0 5XX formats)
- TCKN (Turkish Citizenship Number, 11-digit with checksum validation)
- VKN (Tax Identification Number, 10-digit, context-aware with phone priority)
- Turkish IBAN (TR + 24 digits)
- URLs (http/https)

All regex patterns are compiled at module level for performance.
"""

import re
from typing import Dict, List


# =============================================================================
# COMPILED REGEX PATTERNS (module-level for performance)
# =============================================================================

# Email: standard email pattern
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
)

# Turkish Phone: +90 or 0 prefix followed by 5XX XXX XX XX
# Supports formats: +905XXXXXXXXX, +90 5XX XXX XX XX, 05XXXXXXXXX, 0 5XX XXX XX XX
# Negative lookbehind/lookahead for digits prevents matching within IBANs or other numbers
PHONE_PATTERN = re.compile(
    r'(?<![a-zA-Z\d])(?:\+90\s*|0\s*)5\d{2}[\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)'
)

# TCKN: exactly 11 consecutive digits at word boundary
# Algorithmic checksum validation is applied separately
TCKN_PATTERN = re.compile(
    r'\b\d{11}\b'
)

# VKN: exactly 10 consecutive digits at word boundary
# Context-aware: phone numbers take priority (handled in scan logic)
VKN_PATTERN = re.compile(
    r'\b\d{10}\b'
)

# Turkish IBAN: TR followed by 24 digits, optional spaces between groups
IBAN_PATTERN = re.compile(
    r'\bTR\s?\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}\b'
)

# URL: http or https URLs
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\')\]}]+'
)


# =============================================================================
# PII REPLACEMENT PLACEHOLDERS
# =============================================================================

REPLACEMENTS = {
    "email": "[EMAIL REMOVED]",
    "phone": "[PHONE REMOVED]",
    "tckn": "[TCKN REMOVED]",
    "vkn": "[VKN REMOVED]",
    "iban": "[IBAN REMOVED]",
    "url": "[URL REMOVED]",
}


# =============================================================================
# TCKN CHECKSUM VALIDATION
# =============================================================================

def _validate_tckn_checksum(tckn):
    """
    Validate Turkish Citizenship Number (TCKN) checksum.

    Algorithm (matching kyc_profile.py):
    - 10th digit = ((sum of 1st,3rd,5th,7th,9th digits) * 7 -
                    (sum of 2nd,4th,6th,8th digits)) % 10
    - 11th digit = (sum of first 10 digits) % 10

    Args:
        tckn: String of exactly 11 digits

    Returns:
        True if checksum is valid, False otherwise
    """
    if len(tckn) != 11:
        return False

    try:
        digits = [int(d) for d in tckn]

        # TCKN cannot start with 0
        if digits[0] == 0:
            return False

        # First check: 10th digit
        odd_sum = sum(digits[i] for i in range(0, 9, 2))  # 1st,3rd,5th,7th,9th
        even_sum = sum(digits[i] for i in range(1, 8, 2))  # 2nd,4th,6th,8th
        check_10 = (odd_sum * 7 - even_sum) % 10

        if check_10 != digits[9]:
            return False

        # Second check: 11th digit
        check_11 = sum(digits[:10]) % 10

        if check_11 != digits[10]:
            return False

        return True
    except (ValueError, IndexError):
        return False


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def scan_for_pii(text):
    """
    Scan text for PII and return a dict of detected items.

    Detects 6 types of PII: emails, phone numbers, TCKN, VKN, IBAN, URLs.
    TCKN matches are validated with checksum algorithm.
    VKN detection is context-aware: phone number substrings take priority.

    Args:
        text: The text content to scan

    Returns:
        dict with keys: emails, phones, tckns, vkns, ibans, urls
        Each value is a list of detected PII strings.
    """
    if not text:
        return {
            "emails": [],
            "phones": [],
            "tckns": [],
            "vkns": [],
            "ibans": [],
            "urls": [],
        }

    result = {
        "emails": [],
        "phones": [],
        "tckns": [],
        "vkns": [],
        "ibans": [],
        "urls": [],
    }

    # Detect emails
    result["emails"] = EMAIL_PATTERN.findall(text)

    # Detect Turkish phone numbers
    result["phones"] = PHONE_PATTERN.findall(text)

    # Detect IBANs
    result["ibans"] = IBAN_PATTERN.findall(text)

    # Detect URLs
    result["urls"] = URL_PATTERN.findall(text)

    # Collect phone number spans to exclude from VKN/TCKN detection
    phone_spans = set()
    for match in PHONE_PATTERN.finditer(text):
        for pos in range(match.start(), match.end()):
            phone_spans.add(pos)

    # Detect TCKN (11-digit with checksum validation)
    # Exclude matches that overlap with phone number spans
    for match in TCKN_PATTERN.finditer(text):
        if any(pos in phone_spans for pos in range(match.start(), match.end())):
            continue
        candidate = match.group()
        if _validate_tckn_checksum(candidate):
            result["tckns"].append(candidate)

    # Collect TCKN spans to exclude from VKN detection
    tckn_values = set(result["tckns"])

    # Detect VKN (10-digit, context-aware: phone priority)
    # Exclude matches that overlap with phone or TCKN spans
    for match in VKN_PATTERN.finditer(text):
        if any(pos in phone_spans for pos in range(match.start(), match.end())):
            continue
        candidate = match.group()
        # Skip if this 10-digit sequence is a substring of a detected TCKN
        is_tckn_substring = False
        for tckn in tckn_values:
            if candidate in tckn:
                is_tckn_substring = True
                break
        if not is_tckn_substring:
            result["vkns"].append(candidate)

    return result


def sanitize_message(text):
    """
    Sanitize text by replacing all detected PII with safe placeholders.

    Replacement order ensures correct handling of overlapping patterns:
    1. IBANs (longest, contains digits that could match other patterns)
    2. URLs (can contain email-like substrings)
    3. Emails
    4. Phone numbers
    5. TCKNs (11-digit, validated)
    6. VKNs (10-digit, context-aware)

    Args:
        text: The text content to sanitize

    Returns:
        Sanitized text with all PII replaced by placeholders
    """
    if not text:
        return text

    sanitized = text

    # Step 1: Replace IBANs first (longest pattern, avoids partial digit matches)
    sanitized = IBAN_PATTERN.sub(REPLACEMENTS["iban"], sanitized)

    # Step 2: Replace URLs (can contain email-like substrings)
    sanitized = URL_PATTERN.sub(REPLACEMENTS["url"], sanitized)

    # Step 3: Replace emails
    sanitized = EMAIL_PATTERN.sub(REPLACEMENTS["email"], sanitized)

    # Step 4: Replace phone numbers
    sanitized = PHONE_PATTERN.sub(REPLACEMENTS["phone"], sanitized)

    # Step 5: Replace TCKNs (11-digit with checksum validation)
    # Use a callback to only replace valid TCKNs
    def _replace_tckn(match):
        candidate = match.group()
        if _validate_tckn_checksum(candidate):
            return REPLACEMENTS["tckn"]
        return candidate

    sanitized = TCKN_PATTERN.sub(_replace_tckn, sanitized)

    # Step 6: Replace VKNs (10-digit, remaining after phone removal)
    sanitized = VKN_PATTERN.sub(REPLACEMENTS["vkn"], sanitized)

    return sanitized
