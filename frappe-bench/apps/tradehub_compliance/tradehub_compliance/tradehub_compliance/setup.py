# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
TradeHub Compliance Setup Functions

One-time setup and seed functions for the transparency subsystem.
Run via bench execute after installation:

    bench --site [site] execute tradehub_compliance.tradehub_compliance.setup.create_transparency_consent_topics
    bench --site [site] execute tradehub_compliance.tradehub_compliance.setup.seed_default_visibility_rules
    bench --site [site] execute tradehub_compliance.tradehub_compliance.setup.ensure_anonymous_id_secret

Functions:
    create_transparency_consent_topics: Seeds Consent Topic records for transparency features
    seed_default_visibility_rules:     Creates Buyer Visibility Rule defaults per disclosure stage
    ensure_anonymous_id_secret:        Adds anonymous_buyer_id_secret to site_config.json if missing
"""

import secrets
import string

import frappe
from frappe import _


# =============================================================================
# CONSENT TOPIC SEED DATA
# =============================================================================

TRANSPARENCY_CONSENT_TOPICS = [
    {
        "topic_name": "Transparency Profile Sharing",
        "topic_code": "TRANSPARENCY_PROFILE",
        "category": "Data Processing",
        "description": (
            "Allow your aggregated profile metrics (order count, payment reliability, "
            "membership duration) to be shared with sellers through the transparency system. "
            "Data is anonymized and no personal identifiers are revealed."
        ),
        "legal_basis": "Consent",
        "requires_explicit_consent": 1,
        "mandatory": 0,
        "default_enabled": 0,
        "display_order": 10,
        "allow_partial_consent": 0,
        "requires_separate_consent": 0,
    },
    {
        "topic_name": "Order History Sharing",
        "topic_code": "ORDER_HISTORY_SHARING",
        "category": "Data Processing",
        "description": (
            "Allow anonymized order history data to be shared with sellers. "
            "This includes order counts and general purchasing patterns, but never "
            "specific order details or personal information."
        ),
        "legal_basis": "Consent",
        "requires_explicit_consent": 1,
        "mandatory": 0,
        "default_enabled": 0,
        "display_order": 20,
        "allow_partial_consent": 0,
        "requires_separate_consent": 1,
    },
    {
        "topic_name": "Rating History Sharing",
        "topic_code": "RATING_HISTORY_SHARING",
        "category": "Data Processing",
        "description": (
            "Allow your rating and review history to be shared in aggregate form "
            "with sellers. Individual reviews are not disclosed; only aggregated "
            "metrics are shared."
        ),
        "legal_basis": "Consent",
        "requires_explicit_consent": 1,
        "mandatory": 0,
        "default_enabled": 0,
        "display_order": 30,
        "allow_partial_consent": 0,
        "requires_separate_consent": 1,
    },
    {
        "topic_name": "Payment Metrics Sharing",
        "topic_code": "PAYMENT_METRICS_SHARING",
        "category": "Data Processing",
        "description": (
            "Allow payment reliability metrics (on-time payment rate) to be shared "
            "with sellers. This helps build trust in B2B transactions. No specific "
            "payment amounts or bank details are ever disclosed."
        ),
        "legal_basis": "Consent",
        "requires_explicit_consent": 1,
        "mandatory": 0,
        "default_enabled": 0,
        "display_order": 40,
        "allow_partial_consent": 0,
        "requires_separate_consent": 1,
    },
    {
        "topic_name": "Audience Segment Participation",
        "topic_code": "AUDIENCE_SEGMENT",
        "category": "Analytics",
        "description": (
            "Allow your anonymized buyer profile to be included in audience segments "
            "for aggregate analytics. Your identity is never disclosed; only anonymous "
            "buyer IDs (BYR-XXXXXX) are used within segments."
        ),
        "legal_basis": "Consent",
        "requires_explicit_consent": 1,
        "mandatory": 0,
        "default_enabled": 0,
        "display_order": 50,
        "allow_partial_consent": 0,
        "requires_separate_consent": 0,
    },
]


# =============================================================================
# DEFAULT VISIBILITY RULES
# =============================================================================

# Each rule: (rule_name, disclosure_stage, field_name, visibility, applies_to_role, priority)
DEFAULT_VISIBILITY_RULES = [
    # --- pre_order stage: minimal data, most fields hidden/anonymized ---
    (
        "Pre-Order: Buyer Tier Visible",
        "pre_order", "buyer_tier", "visible", "Seller", 10,
    ),
    (
        "Pre-Order: Member Since Anonymized",
        "pre_order", "member_since", "anonymized", "Seller", 10,
    ),
    (
        "Pre-Order: Total Orders Hidden",
        "pre_order", "total_orders", "hidden", "Seller", 10,
    ),
    (
        "Pre-Order: Payment Rate Hidden",
        "pre_order", "payment_on_time_rate", "hidden", "Seller", 10,
    ),
    (
        "Pre-Order: Avg Order Value Hidden",
        "pre_order", "average_order_value", "hidden", "Seller", 10,
    ),

    # --- active_order stage: moderate data revealed ---
    (
        "Active Order: Buyer Tier Visible",
        "active_order", "buyer_tier", "visible", "Seller", 10,
    ),
    (
        "Active Order: Member Since Visible",
        "active_order", "member_since", "visible", "Seller", 10,
    ),
    (
        "Active Order: Total Orders Visible",
        "active_order", "total_orders", "visible", "Seller", 10,
    ),
    (
        "Active Order: Payment Rate Anonymized",
        "active_order", "payment_on_time_rate", "anonymized", "Seller", 10,
    ),
    (
        "Active Order: Avg Order Value Hidden",
        "active_order", "average_order_value", "hidden", "Seller", 10,
    ),

    # --- post_delivery stage: most data visible ---
    (
        "Post-Delivery: Buyer Tier Visible",
        "post_delivery", "buyer_tier", "visible", "Seller", 10,
    ),
    (
        "Post-Delivery: Member Since Visible",
        "post_delivery", "member_since", "visible", "Seller", 10,
    ),
    (
        "Post-Delivery: Total Orders Visible",
        "post_delivery", "total_orders", "visible", "Seller", 10,
    ),
    (
        "Post-Delivery: Payment Rate Visible",
        "post_delivery", "payment_on_time_rate", "visible", "Seller", 10,
    ),
    (
        "Post-Delivery: Avg Order Value Visible",
        "post_delivery", "average_order_value", "visible", "Seller", 10,
    ),
]

# Length of the generated HMAC secret
SECRET_LENGTH = 64


# =============================================================================
# SETUP FUNCTIONS
# =============================================================================

def create_transparency_consent_topics():
    """
    Seed Consent Topic records for the transparency subsystem.

    Creates consent topics required by the transparency and audience
    features (Tasks 120 & 121). Each topic maps to a specific data
    sharing category governed by KVKK/GDPR requirements.

    Topics are only created if they do not already exist (checked by
    topic_code uniqueness). Existing topics are skipped to allow
    re-running safely.
    """
    created = 0
    skipped = 0

    for topic_data in TRANSPARENCY_CONSENT_TOPICS:
        topic_code = topic_data["topic_code"]

        # Skip if topic already exists (idempotent)
        if frappe.db.exists("Consent Topic", {"topic_code": topic_code}):
            skipped += 1
            continue

        doc = frappe.new_doc("Consent Topic")
        doc.update(topic_data)
        doc.enabled = 1

        doc.insert(ignore_permissions=True)
        created += 1

    frappe.db.commit()

    frappe.msgprint(
        _("Transparency Consent Topics: {0} created, {1} already existed").format(
            created, skipped
        )
    )


def seed_default_visibility_rules(tenant=None):
    """
    Create default Buyer Visibility Rule records for each disclosure stage.

    Seeds rules that control what buyer data is visible to sellers at each
    stage of the transaction lifecycle. Rules follow the progressive disclosure
    pattern:

        pre_order:     Only buyer_tier visible; other fields hidden
        active_order:  More fields visible; payment_on_time_rate anonymized
        post_delivery: Most fields visible

    Args:
        tenant: Optional tenant name. If not provided, attempts to resolve
                from session or creates rules without tenant.

    Rules are only created if they do not already exist (checked by rule_name
    uniqueness within the tenant). Existing rules are skipped for idempotency.
    """
    if not tenant:
        tenant = _resolve_default_tenant()

    created = 0
    skipped = 0

    for rule_name, stage, field, visibility, role, priority in DEFAULT_VISIBILITY_RULES:
        # Check if rule already exists for this tenant
        existing_filters = {"rule_name": rule_name}
        if tenant:
            existing_filters["tenant"] = tenant

        if frappe.db.exists("Buyer Visibility Rule", existing_filters):
            skipped += 1
            continue

        doc = frappe.new_doc("Buyer Visibility Rule")
        doc.rule_name = rule_name
        doc.disclosure_stage = stage
        doc.field_name = field
        doc.visibility = visibility
        doc.applies_to_role = role
        doc.is_active = 1
        doc.priority = priority

        if tenant:
            doc.tenant = tenant

        doc.insert(ignore_permissions=True)
        created += 1

    frappe.db.commit()

    frappe.msgprint(
        _("Buyer Visibility Rules: {0} created, {1} already existed").format(
            created, skipped
        )
    )


def ensure_anonymous_id_secret():
    """
    Add anonymous_buyer_id_secret to site_config.json if missing.

    The HMAC secret is used by the anonymous buyer ID generator
    (anonymization/anonymous_buyer.py) to compute deterministic,
    non-reversible BYR-XXXXXX identifiers.

    Security properties of the generated secret:
    - 64-character random string using URL-safe alphabet
    - Generated via secrets module (cryptographically secure)
    - Stored in site_config.json (not in database)

    If the secret already exists, no action is taken (idempotent).
    """
    existing_secret = getattr(frappe.conf, "anonymous_buyer_id_secret", None)

    if existing_secret:
        frappe.msgprint(
            _("anonymous_buyer_id_secret already configured in site_config.json")
        )
        return

    # Generate a cryptographically secure random secret
    secret = _generate_secret(SECRET_LENGTH)

    # Update site_config.json via Frappe's installer utility
    from frappe.installer import update_site_config

    update_site_config("anonymous_buyer_id_secret", secret)

    frappe.msgprint(
        _("anonymous_buyer_id_secret has been added to site_config.json "
          "({0} characters)").format(len(secret))
    )


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _generate_secret(length):
    """
    Generate a cryptographically secure random string.

    Uses the secrets module for security-sensitive random generation.
    The alphabet includes uppercase, lowercase, and digits for URL safety.

    Args:
        length: Desired length of the secret string.

    Returns:
        str: Random secret string of specified length.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _resolve_default_tenant():
    """
    Attempt to resolve a default tenant for seed data.

    Tries to find the first active Tenant record. Returns None if
    no Tenant DocType exists or no tenants are configured.

    Returns:
        str or None: Tenant name, or None if unavailable.
    """
    try:
        if not frappe.db.exists("DocType", "Tenant"):
            return None

        tenant = frappe.db.get_value(
            "Tenant",
            filters={"enabled": 1},
            fieldname="name",
            order_by="creation asc",
        )
        return tenant
    except Exception:
        return None
