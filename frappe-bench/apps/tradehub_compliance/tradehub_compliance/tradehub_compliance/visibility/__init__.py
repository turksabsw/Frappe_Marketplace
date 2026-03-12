# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Visibility Module

This module provides:
- Buyer visibility API for sellers (anonymized buyer profile view)
- Stage-based field filtering using Buyer Visibility Rules
- Integration with anonymous buyer ID system (HMAC-SHA256 BYR-XXXXXX)
- Progressive disclosure stage support (pre_order, active_order, post_delivery)
"""

from tradehub_compliance.tradehub_compliance.visibility.api import (
    get_seller_view,
)

__all__ = [
    'get_seller_view',
]
