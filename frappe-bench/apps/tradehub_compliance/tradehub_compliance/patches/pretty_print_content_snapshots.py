# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Migration Patch: Pretty-Print Content Snapshots on Moderation Cases.

This patch iterates all Moderation Case records that have a content_snapshot
JSON blob and re-serializes the value with indent=2 and ensure_ascii=False
so that stored snapshots are human-readable and Unicode characters are
preserved verbatim.

IMPORTANT: This patch is idempotent. Re-running it on already pretty-printed
JSON will produce the same output.
"""

import json

import frappe
from frappe import _


def execute():
    """
    Main entry point for the migration patch.

    Parses each Moderation Case content_snapshot JSON string and
    re-serializes it with indent=2 and ensure_ascii=False.
    """
    frappe.reload_doc("tradehub_compliance", "doctype", "moderation_case")

    if not frappe.db.table_exists("tabModeration Case"):
        return

    if not frappe.db.has_column("Moderation Case", "content_snapshot"):
        return

    records = frappe.db.sql(
        """
        SELECT name, content_snapshot
        FROM `tabModeration Case`
        WHERE content_snapshot IS NOT NULL
            AND content_snapshot != ''
            AND content_snapshot != 'null'
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

            pretty = json.dumps(data, indent=2, ensure_ascii=False, default=str)

            # Skip if already formatted identically
            if pretty == raw:
                skipped += 1
                continue

            frappe.db.set_value(
                "Moderation Case",
                record.name,
                "content_snapshot",
                pretty,
                update_modified=False,
            )
            updated += 1

        except Exception as e:
            frappe.log_error(
                title=_("Pretty Print Snapshot Error"),
                message=_("Error pretty-printing content_snapshot for Moderation Case {0}: {1}").format(
                    record.name, str(e)
                ),
            )
            errors += 1

    if updated > 0:
        frappe.db.commit()

    frappe.log_error(
        title=_("Pretty Print Snapshots Complete"),
        message=_("Updated: {0}, Skipped: {1}, Errors: {2}").format(
            updated, skipped, errors
        ),
    )
