# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Transparency Module

This module provides:
- Progressive disclosure stage determination for buyer-seller relationships
- Shared utilities for Tasks 120 (Mutual Transparent Data Sharing)
  and 121 (Asymmetric Visibility)
- Stage-based data visibility: pre_order → active_order → post_delivery
"""

from tradehub_compliance.tradehub_compliance.transparency.utils import (
    get_disclosure_stage,
)

__all__ = [
    'get_disclosure_stage',
]
