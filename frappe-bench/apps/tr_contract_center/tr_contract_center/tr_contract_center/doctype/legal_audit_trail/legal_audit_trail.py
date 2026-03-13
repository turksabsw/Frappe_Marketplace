# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class LegalAuditTrail(Document):
	"""
	Legal Audit Trail DocType for TR-TradeHub.

	Provides an immutable audit trail for all contract and consent-related
	legal events. Once created, records cannot be modified or deleted to
	preserve legal compliance and audit integrity.
	"""

	def before_insert(self):
		"""Generate unique trail_id hash before inserting a new record."""
		if not self.trail_id:
			self.trail_id = self._generate_trail_id()

		if not self.user_id:
			self.user_id = frappe.session.user

		if not self.timestamp:
			self.timestamp = now_datetime()

	def validate(self):
		"""Enforce immutability — prevent edits on saved documents."""
		if not self.is_new():
			frappe.throw(
				_("Legal Audit Trail records are immutable and cannot be modified.")
			)

	def before_save(self):
		"""Enforce immutability — only new documents may be saved."""
		if not self.is_new():
			frappe.throw(
				_("Legal Audit Trail records are immutable and cannot be modified.")
			)

	def on_trash(self):
		"""Prevent deletion of audit trail records."""
		frappe.throw(
			_("Legal Audit Trail records cannot be deleted.")
		)

	def on_doctype_update(self):
		"""Create custom database indexes for efficient querying."""
		frappe.db.add_index(
			"Legal Audit Trail",
			fields=["user_id", "timestamp"],
			index_name="idx_user_timestamp",
		)
		frappe.db.add_index(
			"Legal Audit Trail",
			fields=["document_type", "document_name"],
			index_name="idx_document",
		)
		frappe.db.add_index(
			"Legal Audit Trail",
			fields=["event_type", "timestamp"],
			index_name="idx_event_type",
		)

	def _generate_trail_id(self):
		"""Generate a unique trail_id based on event data and timestamp."""
		raw = f"{self.event_type}|{self.document_type}|{self.document_name}|{now_datetime()}|{frappe.generate_hash(length=8)}"
		return hashlib.sha256(raw.encode()).hexdigest()[:32]


def create_legal_audit_log(event_type, doc_type, doc_name, **kwargs):
	"""
	Module-level helper to create and insert a Legal Audit Trail record.

	Args:
		event_type (str): Type of event (e.g., 'contract_created', 'consent_granted').
		doc_type (str): The DocType of the related document.
		doc_name (str): The name of the related document.
		**kwargs: Additional optional fields:
			- user_id (str): User who performed the action.
			- ip_address (str): IP address of the user.
			- user_agent (str): User agent string.
			- session_id (str): Session identifier.
			- document_version (int): Version of the document.
			- content_hash (str): Hash of the document content.
			- old_status (str): Previous status of the document.
			- new_status (str): New status of the document.
			- details (str): Additional details about the event.
			- consent_text_snapshot (str): Snapshot of consent text.
			- legal_reference (str): Legal reference identifier.

	Returns:
		Document: The created Legal Audit Trail document.
	"""
	doc = frappe.new_doc("Legal Audit Trail")
	doc.event_type = event_type
	doc.document_type = doc_type
	doc.document_name = doc_name

	# Set optional fields from kwargs
	allowed_fields = [
		"user_id", "ip_address", "user_agent", "session_id",
		"document_version", "content_hash", "old_status", "new_status",
		"details", "consent_text_snapshot", "legal_reference", "timestamp",
	]

	for field in allowed_fields:
		if field in kwargs:
			doc.set(field, kwargs[field])

	doc.insert(ignore_permissions=True)
	return doc
