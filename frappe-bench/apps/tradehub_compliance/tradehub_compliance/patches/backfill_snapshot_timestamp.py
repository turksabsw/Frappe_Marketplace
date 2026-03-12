# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Migration Patch: Backfill snapshot_timestamp from Content Snapshot JSON.

This patch iterates all Moderation Case records that have a content_snapshot
JSON blob but no snapshot_timestamp value. It extracts the "captured_at"
key from the JSON and writes it to the snapshot_timestamp Datetime field.

IMPORTANT: This patch is idempotent. It only updates records where
snapshot_timestamp is NULL or empty.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_datetime


def execute():
    """
    Main entry point for the migration patch.

    Extracts captured_at from each Moderation Case content_snapshot JSON
    and sets the snapshot_timestamp Datetime field.
    """
    frappe.reload_doc("tradehub_compliance", "doctype", "moderation_case")

    if not frappe.db.table_exists("tabModeration Case"):
        return

    if not frappe.db.has_column("Moderation Case", "content_snapshot"):
        return

    if not frappe.db.has_column("Moderation Case", "snapshot_timestamp"):
        return

    records = frappe.db.sql(
        """
        SELECT name, content_snapshot
        FROM `tabModeration Case`
        WHERE content_snapshot IS NOT NULL
            AND content_snapshot != ''
            AND content_snapshot != 'null'
            AND (snapshot_timestamp IS NULL OR snapshot_timestamp = '')
        """,
        as_dict=True,
    )

    updated = 0
    skipped = 0
    errors = 0

    for record in records:
        try:
            raw = record.content_snapshot
            if not raw or not isinstance(raw, str):
                skipped += 1
                continue

            raw = raw.strip()
            if not raw or raw in ("null", "None", "{}", "[]"):
                skipped += 1
                continue

            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                skipped += 1
                continue

            if not isinstance(data, dict):
                skipped += 1
                continue

            captured_at = data.get("captured_at", "")
            if not captured_at:
                skipped += 1
                continue

            try:
                dt_value = get_datetime(captured_at)
            except Exception:
                skipped += 1
                continue

            frappe.db.set_value(
                "Moderation Case",
                record.name,
                "snapshot_timestamp",
                dt_value,
                update_modified=False,
            )
            updated += 1

        except Exception as e:
            frappe.log_error(
                title=_("Backfill Snapshot Timestamp Error"),
                message=_("Error backfilling snapshot_timestamp for Moderation Case {0}: {1}").format(
                    record.name, str(e)
                ),
            )
            errors += 1

    if updated > 0:
        frappe.db.commit()

    frappe.log_error(
        title=_("Backfill Snapshot Timestamp Complete"),
        message=_("Updated: {0}, Skipped: {1}, Errors: {2}").format(
            updated, skipped, errors
        ),
    )
