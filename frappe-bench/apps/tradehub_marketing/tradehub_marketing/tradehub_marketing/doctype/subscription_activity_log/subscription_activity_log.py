# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
Subscription Activity Log DocType Controller

Immutable audit log for all subscription-related activity events.
Records cannot be modified or deleted after creation.

IMMUTABILITY RULES:
- Records can ONLY be created, NEVER modified or deleted
- All fields are read-only after creation
- before_save() throws an error on modification attempts
- on_trash() throws an error to prevent deletion
- db_update() throws an error as additional protection
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class SubscriptionActivityLog(Document):
	"""
	Controller for Subscription Activity Log DocType.

	This DocType is IMMUTABLE - records cannot be modified or deleted.
	DB Indexes:
	- idx_subscription_timestamp (subscription, timestamp)
	- idx_event_type (event_type, timestamp)
	"""

	def before_insert(self):
		"""Set default values before inserting."""
		if not self.timestamp:
			self.timestamp = now_datetime()

	def before_save(self):
		"""
		IMMUTABILITY: Prevent any modifications to existing records.

		New documents are allowed through; existing documents cannot be saved.
		"""
		if not self.is_new():
			frappe.throw(
				_("Subscription Activity Logs are immutable and cannot be modified. "
				  "Activity logs must be retained for audit purposes.")
			)

	def on_trash(self):
		"""
		BLOCK ALL DELETIONS.

		Subscription activity logs must be retained for audit and compliance
		purposes. Deletion is never allowed.
		"""
		frappe.throw(
			_("Subscription Activity Logs cannot be deleted. "
			  "Activity logs must be retained for audit purposes.")
		)

	def db_update(self):
		"""
		Override db_update to prevent updates.

		Additional protection layer against modifications.
		"""
		frappe.throw(
			_("Subscription Activity Logs are immutable and cannot be updated.")
		)


def create_activity_log(subscription, event_type, triggered_by,
						old_status=None, new_status=None, details=None):
	"""
	Create a subscription activity log entry.

	Args:
		subscription: Name of the subscription
		event_type: Type of event (status_change/payment/notification/admin_action)
		triggered_by: What triggered the event (scheduler/manual/payment)
		old_status: Previous subscription status (optional)
		new_status: New subscription status (optional)
		details: Additional details about the event (optional)

	Returns:
		Document: The created activity log
	"""
	doc = frappe.get_doc({
		"doctype": "Subscription Activity Log",
		"subscription": subscription,
		"event_type": event_type,
		"triggered_by": triggered_by,
		"old_status": old_status,
		"new_status": new_status,
		"details": details,
		"timestamp": now_datetime(),
	})

	doc.insert(ignore_permissions=True)
	return doc


def get_activity_trail(subscription):
	"""
	Get the complete activity trail for a subscription.

	Args:
		subscription: Name of the subscription

	Returns:
		list: List of activity log entries in chronological order
	"""
	return frappe.get_all(
		"Subscription Activity Log",
		filters={"subscription": subscription},
		fields=["name", "event_type", "triggered_by", "timestamp",
				"old_status", "new_status", "details"],
		order_by="timestamp asc"
	)


def get_activity_stats(filters=None):
	"""
	Get activity statistics for reporting.

	Args:
		filters: Optional filters for date range, etc.

	Returns:
		dict: Statistics about activity log entries
	"""
	base_filters = filters or {}

	stats = {
		"total_entries": frappe.db.count("Subscription Activity Log", base_filters),
		"by_event_type": {},
		"by_triggered_by": {}
	}

	# Count by event type
	event_types = ["status_change", "payment", "notification", "admin_action"]
	for event_type in event_types:
		event_filters = dict(base_filters)
		event_filters["event_type"] = event_type
		stats["by_event_type"][event_type] = frappe.db.count(
			"Subscription Activity Log", event_filters
		)

	# Count by trigger source
	trigger_sources = ["scheduler", "manual", "payment"]
	for source in trigger_sources:
		source_filters = dict(base_filters)
		source_filters["triggered_by"] = source
		stats["by_triggered_by"][source] = frappe.db.count(
			"Subscription Activity Log", source_filters
		)

	return stats
