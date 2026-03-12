# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class BuyBoxTierBonus(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		bonus_score: DF.Float
		is_active: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		seller_tier: DF.Link
		tier_name: DF.Data | None
	# end: auto-generated types

	pass
