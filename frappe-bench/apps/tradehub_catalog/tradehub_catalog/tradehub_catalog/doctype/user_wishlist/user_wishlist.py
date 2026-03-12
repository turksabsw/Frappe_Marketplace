# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
User Wishlist DocType for Trade Hub B2B Marketplace.

This module implements named wishlists that users can create to organize
and track products they are interested in purchasing.

Key features:
- Named wishlists with default list support (one default per user)
- Public sharing via auto-generated share tokens and URLs
- Digest mode for batched price change notifications
- Multi-tenant data isolation via tenant field
- Unique constraint on user + list_name combination
- Automatic total_items count maintenance
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime


class UserWishlist(Document):
	"""
	User Wishlist DocType for managing named product wishlists.

	Each wishlist belongs to a user and can contain multiple items
	(products/listings) via the Wishlist Item child table. Users can
	create multiple wishlists but only one can be the default.
	"""

	def before_save(self):
		"""Set defaults and ensure constraints before saving."""
		self.ensure_default_uniqueness()
		self.generate_share_token()
		self.compute_share_url()

	def validate(self):
		"""Validate wishlist data before saving."""
		self.validate_unique_list_name()
		self.validate_tenant_isolation()
		self.recount_total_items()

	def on_trash(self):
		"""Cleanup Wishlist Items and notify on default deletion."""
		self.cleanup_wishlist_items()
		self.notify_default_deletion()

	# =========================================================================
	# BEFORE SAVE METHODS
	# =========================================================================

	def ensure_default_uniqueness(self):
		"""
		Ensure only one default wishlist per user.

		If this wishlist is being set as default, unset any other default
		wishlist for the same user.
		"""
		if not self.is_default:
			return

		existing_default = frappe.db.get_value(
			"User Wishlist",
			{
				"user": self.user,
				"is_default": 1,
				"name": ("!=", self.name or "")
			},
			"name"
		)

		if existing_default:
			frappe.db.set_value(
				"User Wishlist", existing_default, "is_default", 0
			)

	def generate_share_token(self):
		"""Generate a unique share token for public wishlist sharing."""
		if not self.share_token:
			self.share_token = frappe.generate_hash(length=16)

	def compute_share_url(self):
		"""Compute the share URL from the share token."""
		if self.share_token and self.is_public:
			site_url = frappe.utils.get_url()
			self.share_url = f"{site_url}/wishlist/{self.share_token}"
		elif not self.is_public:
			self.share_url = None

	# =========================================================================
	# VALIDATION METHODS
	# =========================================================================

	def validate_unique_list_name(self):
		"""
		Validate that user + list_name combination is unique.

		A user cannot have two wishlists with the same name.
		"""
		existing = frappe.db.get_value(
			"User Wishlist",
			{
				"user": self.user,
				"list_name": self.list_name,
				"name": ("!=", self.name or "")
			},
			"name"
		)

		if existing:
			frappe.throw(
				_("A wishlist with the name '{0}' already exists for this user").format(
					self.list_name
				)
			)

	def validate_tenant_isolation(self):
		"""
		Validate that wishlist belongs to user's tenant.

		Ensures multi-tenant data isolation.
		"""
		if not self.tenant:
			return

		# System Manager can access all tenants
		if "System Manager" in frappe.get_roles():
			return

		from tradehub_core.tradehub_core.utils.tenant import get_current_tenant
		current_tenant = get_current_tenant()

		if current_tenant and self.tenant != current_tenant:
			frappe.throw(
				_("Access denied: You can only access wishlists in your tenant")
			)

	# =========================================================================
	# ITEM COUNT MANAGEMENT
	# =========================================================================

	def recount_total_items(self):
		"""Recount the total_items based on the items child table."""
		self.total_items = len(self.items) if self.items else 0

	# =========================================================================
	# CLEANUP METHODS
	# =========================================================================

	def cleanup_wishlist_items(self):
		"""Delete all Wishlist Item child records linked to this wishlist."""
		frappe.db.delete("Wishlist Item", {"parent": self.name})

	def notify_default_deletion(self):
		"""Notify if a default wishlist is being deleted."""
		if self.is_default:
			frappe.msgprint(
				_("Default wishlist '{0}' has been deleted").format(self.list_name),
				indicator="orange",
				alert=True
			)
