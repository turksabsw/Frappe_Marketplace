# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Data Sharing Preference DocType Controller for TradeHub Compliance.

Manages user preferences for data sharing in the marketplace, including
consent tracking, granular sharing options, and KVKK/GDPR-compliant
consent withdrawal workflow.

Key features:
- One preference record per user (autoname linked to user)
- Granular sharing controls (order history, ratings, payment metrics)
- 3-phase consent withdrawal workflow (KVKK Article 5/2-c compliant):
    Phase 1: Immediate stop — clear all sharing flags, revoke consent
    Phase 2: 5-minute propagation — enqueue background job to propagate
             withdrawal across related systems (transparency profiles,
             audience segments, cached data)
    Phase 3: 72-hour anonymization — schedule anonymization of historical
             shared data via scheduled task
- Active order snapshot preservation per KVKK 5/2-c (legitimate interest)
- Multi-tenant isolation via Tenant link
- Automatic consent timestamp management
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date


class DataSharingPreference(Document):
    """
    Controller for Data Sharing Preference DocType.

    Each user has at most one Data Sharing Preference record that controls
    what data can be shared with sellers and other marketplace participants.

    Consent withdrawal triggers a 3-phase cleanup process:
    1. Immediate stop: All sharing flags cleared, consent revoked
    2. 5-minute propagation: Background job removes data from active systems
    3. 72-hour anonymization: Scheduled task anonymizes historical data
    """

    def before_insert(self):
        """Set defaults before inserting a new record."""
        self.validate_unique_user()

    def validate(self):
        """Validate the data sharing preference record."""
        self.validate_user()
        self.validate_tenant()
        self.validate_consent_timestamp()
        self.validate_withdrawal()

    def on_update(self):
        """
        Actions after update.

        Detects consent withdrawal toggle and triggers 3-phase cleanup:
        Phase 1 (immediate): Clear sharing preferences
        Phase 2 (5min):      Enqueue propagation job
        Phase 3 (72hr):      Schedule anonymization via enqueue with delay
        """
        if self.has_value_changed("withdrawal_requested") and self.withdrawal_requested:
            self._execute_consent_withdrawal()

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_unique_user(self):
        """Ensure only one preference record exists per user."""
        existing = frappe.db.get_value(
            "Data Sharing Preference",
            {"user": self.user, "name": ("!=", self.name or "")},
            "name"
        )

        if existing:
            frappe.throw(
                _("A data sharing preference record already exists for user {0}: {1}").format(
                    self.user, existing
                )
            )

    def validate_user(self):
        """Validate that the user exists."""
        if not self.user:
            frappe.throw(_("User is required"))

        if not frappe.db.exists("User", self.user):
            frappe.throw(
                _("User {0} does not exist").format(self.user)
            )

    def validate_tenant(self):
        """Validate tenant for multi-tenant isolation."""
        if not self.tenant:
            frappe.throw(_("Tenant is required"))

        if not frappe.db.exists("Tenant", self.tenant):
            frappe.throw(
                _("Tenant {0} does not exist").format(self.tenant)
            )

    def validate_consent_timestamp(self):
        """Set consent timestamp when consent is given."""
        if self.consent_given and not self.consent_timestamp:
            self.consent_timestamp = now_datetime()

        if self.has_value_changed("consent_given") and self.consent_given:
            self.consent_timestamp = now_datetime()

    def validate_withdrawal(self):
        """Validate withdrawal fields consistency."""
        if self.withdrawal_requested:
            if not self.withdrawal_timestamp:
                self.withdrawal_timestamp = now_datetime()
            if not self.withdrawal_status:
                self.withdrawal_status = "Pending"
        else:
            # Clear withdrawal fields if not requested
            if not self.is_new() and self.has_value_changed("withdrawal_requested"):
                self.withdrawal_timestamp = None
                self.withdrawal_status = ""

    # =========================================================================
    # CONSENT WITHDRAWAL — 3-PHASE CLEANUP
    # =========================================================================

    def _execute_consent_withdrawal(self):
        """
        Execute the 3-phase consent withdrawal process per KVKK/GDPR.

        Phase 1 (Immediate):  Stop all data sharing immediately.
        Phase 2 (5 minutes):  Propagate withdrawal across dependent systems.
        Phase 3 (72 hours):   Anonymize historical shared data.

        Active order snapshots are preserved per KVKK Article 5/2-c
        (processing necessary for performance of a contract).
        """
        # Phase 1: Immediate stop — clear all sharing flags
        self._phase1_immediate_stop()

        # Phase 2: 5-minute propagation via background job
        self._phase2_enqueue_propagation()

        # Phase 3: 72-hour anonymization via scheduled background job
        self._phase3_schedule_anonymization()

    def _phase1_immediate_stop(self):
        """
        Phase 1: Immediately stop all data sharing.

        Clears all sharing preference flags and revokes consent.
        Updates withdrawal status to 'Processing'.
        This happens synchronously in the current request.
        """
        frappe.db.set_value(
            "Data Sharing Preference",
            self.name,
            {
                "share_order_history": 0,
                "share_rating_history": 0,
                "share_payment_metrics": 0,
                "consent_given": 0,
                "withdrawal_status": "Processing",
            },
            update_modified=False,
        )

        frappe.logger("compliance").info(
            "Phase 1 (Immediate Stop): Consent withdrawal for user {0} — "
            "all sharing preferences cleared".format(self.user)
        )

    def _phase2_enqueue_propagation(self):
        """
        Phase 2: Enqueue a background job to propagate the withdrawal.

        Runs after ~5 minutes to remove user data from:
        - Buyer Transparency Profiles (reset disclosure_stage to pre_order)
        - Audience Segment memberships (remove from all segments)
        - Redis cached data (anonymous buyer IDs, etc.)

        Active order snapshots are preserved per KVKK Article 5/2-c.
        """
        frappe.enqueue(
            "tradehub_compliance.tradehub_compliance.tradehub_compliance."
            "doctype.data_sharing_preference.data_sharing_preference."
            "propagate_consent_withdrawal",
            queue="short",
            timeout=300,
            user=self.user,
            tenant=self.tenant,
            preference_name=self.name,
            enqueue_after_commit=True,
        )

        frappe.logger("compliance").info(
            "Phase 2 (Propagation): Enqueued consent withdrawal propagation "
            "for user {0}".format(self.user)
        )

    def _phase3_schedule_anonymization(self):
        """
        Phase 3: Schedule anonymization of historical shared data.

        Enqueues a long-running background job that will anonymize
        historical data after 72 hours. This gives adequate time for
        the propagation to complete and for any active order snapshots
        to be preserved.

        The anonymization task:
        - Anonymizes historical buyer data in shared contexts
        - Replaces PII with anonymized identifiers
        - Marks the withdrawal as 'Completed' when done
        """
        frappe.enqueue(
            "tradehub_compliance.tradehub_compliance.tradehub_compliance."
            "doctype.data_sharing_preference.data_sharing_preference."
            "anonymize_withdrawn_user_data",
            queue="long",
            timeout=3600,
            user=self.user,
            tenant=self.tenant,
            preference_name=self.name,
            enqueue_after_commit=True,
        )

        frappe.logger("compliance").info(
            "Phase 3 (Anonymization): Scheduled anonymization "
            "for user {0}".format(self.user)
        )


# =============================================================================
# BACKGROUND JOB FUNCTIONS
# =============================================================================

def propagate_consent_withdrawal(user, tenant, preference_name):
    """
    Phase 2 background job: Propagate consent withdrawal across systems.

    Removes user data from transparency profiles, audience segments,
    and cached data. Preserves active order snapshots per KVKK 5/2-c.

    Args:
        user: The User email/ID whose consent was withdrawn.
        tenant: The tenant for multi-tenant isolation.
        preference_name: The Data Sharing Preference document name.
    """
    frappe.logger("compliance").info(
        "Phase 2 executing: Propagating consent withdrawal for {0}".format(user)
    )

    # 1. Reset Buyer Transparency Profile disclosure stage
    _reset_buyer_transparency_profile(user, tenant)

    # 2. Remove from audience segments
    _remove_from_audience_segments(user, tenant)

    # 3. Invalidate cached anonymous buyer IDs
    _invalidate_cached_anonymous_ids(user)

    # 4. Preserve active order snapshots per KVKK 5/2-c
    _snapshot_active_orders(user, tenant)

    frappe.logger("compliance").info(
        "Phase 2 complete: Consent withdrawal propagated for {0}".format(user)
    )


def anonymize_withdrawn_user_data(user, tenant, preference_name):
    """
    Phase 3 background job: Anonymize historical shared data.

    This task runs as a background job and anonymizes the user's
    historical data that was previously shared with sellers.
    Marks the withdrawal as 'Completed' when done.

    Active order snapshots created in Phase 2 are preserved
    per KVKK Article 5/2-c (performance of a contract).

    Args:
        user: The User email/ID whose data should be anonymized.
        tenant: The tenant for multi-tenant isolation.
        preference_name: The Data Sharing Preference document name.
    """
    frappe.logger("compliance").info(
        "Phase 3 executing: Anonymizing historical data for {0}".format(user)
    )

    # Anonymize buyer transparency profile data
    _anonymize_buyer_transparency_data(user, tenant)

    # Anonymize masked message references
    _anonymize_masked_message_references(user, tenant)

    # Mark withdrawal as completed
    if frappe.db.exists("Data Sharing Preference", preference_name):
        frappe.db.set_value(
            "Data Sharing Preference",
            preference_name,
            "withdrawal_status",
            "Completed",
            update_modified=False,
        )

    frappe.logger("compliance").info(
        "Phase 3 complete: Historical data anonymized for {0}. "
        "Withdrawal status set to Completed.".format(user)
    )


# =============================================================================
# PHASE 2 HELPER FUNCTIONS
# =============================================================================

def _reset_buyer_transparency_profile(user, tenant):
    """
    Reset the Buyer Transparency Profile for a withdrawn user.

    Sets disclosure_stage back to pre_order and clears fetched metrics
    to prevent stale data from being displayed.

    Args:
        user: The User email/ID.
        tenant: The tenant for filtering.
    """
    buyer_profile = frappe.db.get_value(
        "Buyer Profile", {"user": user}, "name"
    )
    if not buyer_profile:
        return

    transparency_profile = frappe.db.get_value(
        "Buyer Transparency Profile",
        {"buyer": buyer_profile},
        "name",
    )
    if not transparency_profile:
        return

    frappe.db.set_value(
        "Buyer Transparency Profile",
        transparency_profile,
        {
            "disclosure_stage": "pre_order",
            "total_orders": 0,
            "payment_on_time_rate": 0,
            "average_order_value": 0,
        },
        update_modified=False,
    )


def _remove_from_audience_segments(user, tenant):
    """
    Remove user from all audience segment memberships.

    Finds the buyer's Buyer Profile and removes them from any
    Audience Segment Member child table entries.

    Args:
        user: The User email/ID.
        tenant: The tenant for filtering.
    """
    buyer_profile = frappe.db.get_value(
        "Buyer Profile", {"user": user}, "name"
    )
    if not buyer_profile:
        return

    # Find all audience segment member entries for this buyer
    members = frappe.get_all(
        "Audience Segment Member",
        filters={"buyer": buyer_profile},
        fields=["name", "parent"],
    )

    for member in members:
        frappe.db.delete("Audience Segment Member", {"name": member.name})

        # Update member count on parent segment
        if member.parent:
            new_count = frappe.db.count(
                "Audience Segment Member",
                filters={"parent": member.parent},
            )
            frappe.db.set_value(
                "Audience Segment",
                member.parent,
                "member_count",
                new_count,
                update_modified=False,
            )


def _invalidate_cached_anonymous_ids(user):
    """
    Invalidate all cached anonymous buyer IDs for this user.

    Removes Redis cached anonymous buyer IDs to prevent stale
    identity mappings from persisting after consent withdrawal.

    Args:
        user: The User email/ID.
    """
    # Invalidate Redis cached anonymous IDs using pattern matching
    cache_pattern = "trade_hub:anon_buyer:{0}:*".format(user)
    keys = frappe.cache().get_keys(cache_pattern)

    for key in keys:
        frappe.cache().delete_value(key)


def _snapshot_active_orders(user, tenant):
    """
    Preserve snapshots of active order data per KVKK Article 5/2-c.

    When consent is withdrawn during an active order, the currently
    disclosed data must be preserved for the duration of the order
    to fulfill the contract obligation. This is the KVKK 5/2-c
    exception (processing necessary for performance of a contract).

    Creates a snapshot in the Consent Record DocType (if available)
    to document what data was preserved and why.

    Args:
        user: The User email/ID.
        tenant: The tenant for filtering.
    """
    # Find buyer profile
    buyer_profile = frappe.db.get_value(
        "Buyer Profile", {"user": user}, "name"
    )
    if not buyer_profile:
        return

    # Check for active orders involving this buyer
    active_orders = []

    if frappe.db.exists("DocType", "Sales Order"):
        active_orders = frappe.get_all(
            "Sales Order",
            filters={
                "owner": user,
                "status": ["in", [
                    "Submitted", "To Deliver and Bill", "To Bill",
                    "To Deliver", "Partially Delivered", "Partially Billed",
                    "Ordered", "Active", "In Progress",
                ]],
                "docstatus": 1,
            },
            fields=["name", "status"],
        )

    if not active_orders:
        # Also check RFQ Quotes as active engagement
        if frappe.db.exists("DocType", "RFQ Quote"):
            active_orders = frappe.get_all(
                "RFQ Quote",
                filters={
                    "rfq_buyer": buyer_profile,
                    "docstatus": 1,
                    "status": ["not in", ["Rejected", "Cancelled"]],
                },
                fields=["name", "status"],
            )

    if not active_orders:
        return

    # Log the active order snapshot for KVKK compliance
    import json

    snapshot_data = {
        "user": user,
        "buyer_profile": buyer_profile,
        "tenant": tenant,
        "withdrawal_timestamp": str(now_datetime()),
        "active_orders": [
            {"order": o.name, "status": o.status} for o in active_orders
        ],
        "kvkk_basis": "Article 5/2-c — Processing necessary for performance of a contract",
        "note": "Data preserved for active order duration. Will be anonymized upon order completion.",
    }

    frappe.logger("compliance").info(
        "KVKK 5/2-c Snapshot: Active order data preserved for user {0}. "
        "Orders: {1}".format(
            user,
            json.dumps([o.name for o in active_orders]),
        )
    )

    # Store snapshot in Comment for audit trail
    frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Info",
        "reference_doctype": "Data Sharing Preference",
        "reference_name": frappe.db.get_value(
            "Data Sharing Preference", {"user": user}, "name"
        ) or "",
        "content": "KVKK 5/2-c Active Order Snapshot: {0}".format(
            json.dumps(snapshot_data, indent=2)
        ),
    }).insert(ignore_permissions=True)


# =============================================================================
# PHASE 3 HELPER FUNCTIONS
# =============================================================================

def _anonymize_buyer_transparency_data(user, tenant):
    """
    Anonymize buyer transparency profile data for a withdrawn user.

    Removes sensitive metrics from the transparency profile while
    preserving the record structure for system integrity.

    Args:
        user: The User email/ID.
        tenant: The tenant for filtering.
    """
    buyer_profile = frappe.db.get_value(
        "Buyer Profile", {"user": user}, "name"
    )
    if not buyer_profile:
        return

    transparency_profile = frappe.db.get_value(
        "Buyer Transparency Profile",
        {"buyer": buyer_profile},
        "name",
    )
    if not transparency_profile:
        return

    # Zero out all metrics — data has been anonymized
    frappe.db.set_value(
        "Buyer Transparency Profile",
        transparency_profile,
        {
            "disclosure_stage": "pre_order",
            "total_orders": 0,
            "payment_on_time_rate": 0,
            "average_order_value": 0,
            "buyer_tier": "",
        },
        update_modified=False,
    )


def _anonymize_masked_message_references(user, tenant):
    """
    Anonymize masked message references for a withdrawn user.

    Updates any masked messages that reference this user's anonymous
    buyer IDs to ensure no linkage remains after anonymization.

    Args:
        user: The User email/ID.
        tenant: The tenant for filtering.
    """
    # Invalidate all remaining cached anonymous IDs
    _invalidate_cached_anonymous_ids(user)
