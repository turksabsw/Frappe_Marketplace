# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Audience Module

This module provides:
- Audience segment management API endpoints
- Anonymous member listing with minimum 3 threshold (KVKK/GDPR)
- Dynamic segment creation with filter-based member computation
- Segment metrics with minimum 5 member threshold
"""

from tradehub_compliance.tradehub_compliance.audience.api import (
    get_segment_members,
    create_segment,
)

__all__ = [
    'get_segment_members',
    'create_segment',
]
