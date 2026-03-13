# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
Marketplace Settings Singleton DocType Controller

Global configuration for the TradeHub B2B marketplace platform.
Includes PPR (Platform Purchase Request) scoring weight configuration
that determines how seller offers are automatically scored.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MarketplaceSettings(Document):
    """
    Controller for Marketplace Settings singleton DocType.

    Validates that PPR scoring weights sum to exactly 100%.
    """

    def validate(self):
        """Validate settings values."""
        self.validate_scoring_weights()

    def validate_scoring_weights(self):
        """Ensure PPR scoring weights sum to exactly 100.

        The four weight fields (price_weight, delivery_weight,
        rating_weight, payment_weight) must sum to 100 so that
        the auto-scoring algorithm produces a normalized [0, 100] score.

        Raises:
            frappe.ValidationError: If weights do not sum to 100.
        """
        weight_fields = [
            "price_weight",
            "delivery_weight",
            "rating_weight",
            "payment_weight",
        ]

        total = 0
        for field in weight_fields:
            value = flt(self.get(field), 2)
            if value < 0:
                frappe.throw(
                    _("{0} must be a non-negative value.").format(
                        self.meta.get_label(field)
                    )
                )
            total += value

        total = flt(total, 2)

        if abs(total - 100) > 0.01:
            frappe.throw(
                _("PPR scoring weights must sum to 100. Current total: {0}").format(
                    total
                )
            )
