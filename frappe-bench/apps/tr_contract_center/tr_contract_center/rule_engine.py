# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
Dynamic Contract Rule Engine for TR Contract Center (TASK-146).

Implements the rule-based contract compilation pipeline:
    1. Collect seller attributes from Seller Profile and related docs
    2. Evaluate condition rules against seller attributes
    3. Apply matching rules to base text (add/remove/replace clauses)
    4. Save compiled output as immutable Contract Compiled Output
    5. Validate markers and analyze rule impact

The engine supports 8 condition operators:
    equals, not_equals, in, not_in, greater_than, less_than, between, contains

And 3 clause actions:
    add_clause    — Append clause text at the specified position
    remove_clause — Remove marker block from compiled content
    replace_clause — Replace marker with clause text

Conflict resolution strategies:
    first_match    — Only the first matching rule per marker is applied
    all_matching   — All matching rules are applied in sequence
    priority_based — Rules are grouped by priority, highest priority wins

Usage:
    from tr_contract_center.rule_engine import compile_contract

    result = compile_contract("SELLER-AGREEMENT-001", "SP-00001")
    # result = {"compiled_content": "...", "compilation_log": [...], ...}
"""

import hashlib
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, date_diff


# ---------------------------------------------------------------------------
# Condition type → Seller Profile field mapping
# ---------------------------------------------------------------------------
CONDITION_TYPE_FIELD_MAP = {
    "package": "package",
    "category": "category",
    "revenue_range": "revenue",
    "seller_type": "seller_type",
    "location": "location",
    "registration_age": "registration_age",
    "custom": None,  # Custom conditions use condition_value as field name
}

# Marker pattern: {{MARKER_NAME}} in base_text
MARKER_PATTERN = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")


# ===========================================================================
# Public API — 5 core functions
# ===========================================================================


def get_seller_attributes(seller_name):
    """
    Fetch seller attributes from Seller Profile and related documents.

    Gathers package, category, revenue, seller_type, location, and
    registration_age information used for contract condition evaluation.

    Args:
        seller_name: Name (ID) of the Seller Profile document.

    Returns:
        dict: Seller attributes with keys:
            - package (str): Active subscription package name or empty string
            - category (str): Seller's primary category or empty string
            - revenue (float): Total sales amount
            - seller_type (str): Individual/Business/Enterprise
            - location (str): City from seller profile
            - registration_age (int): Days since seller registration
            - seller_name (str): Seller display name
            - seller_tier (str): Seller tier name
            - status (str): Seller profile status

    Raises:
        frappe.DoesNotExistError: If seller_name does not exist.
    """
    if not seller_name:
        frappe.throw(_("Seller name is required"))

    if not frappe.db.exists("Seller Profile", seller_name):
        frappe.throw(
            _("Seller Profile '{0}' does not exist").format(seller_name),
            frappe.DoesNotExistError,
        )

    seller = frappe.db.get_value(
        "Seller Profile",
        seller_name,
        [
            "seller_name",
            "seller_type",
            "city",
            "state",
            "total_sales_amount",
            "seller_tier",
            "status",
            "organization",
            "creation",
        ],
        as_dict=True,
    )

    # Calculate registration age in days
    registration_age = 0
    if seller.get("creation"):
        registration_age = date_diff(getdate(), getdate(seller.creation))

    # Get active subscription package
    package = _get_seller_package(seller_name)

    # Get seller category from organization or seller tier
    category = _get_seller_category(seller_name, seller)

    attrs = {
        "package": package or "",
        "category": category or "",
        "revenue": flt(seller.get("total_sales_amount", 0)),
        "seller_type": seller.get("seller_type") or "",
        "location": seller.get("city") or "",
        "registration_age": cint(registration_age),
        "seller_name": seller.get("seller_name") or "",
        "seller_tier": seller.get("seller_tier") or "",
        "status": seller.get("status") or "",
    }

    frappe.logger("rule_engine").debug(
        f"Seller attributes for {seller_name}: {attrs}"
    )

    return attrs


def evaluate_condition(rule, seller_attrs):
    """
    Evaluate a single Contract Condition Rule against seller attributes.

    Supports all 8 operators: equals, not_equals, in, not_in,
    greater_than, less_than, between, contains.

    Args:
        rule: A Contract Condition Rule document or dict with:
            - condition_type (str): Type of condition to evaluate
            - condition_operator (str): Comparison operator
            - condition_value (str): Expected value(s) to compare against
            - is_active (bool/int): Whether rule is active
        seller_attrs: Dict of seller attributes from get_seller_attributes().

    Returns:
        bool: True if condition matches, False otherwise.
    """
    # Inactive rules never match
    is_active = rule.get("is_active") if isinstance(rule, dict) else getattr(rule, "is_active", 1)
    if not cint(is_active):
        return False

    condition_type = rule.get("condition_type") if isinstance(rule, dict) else getattr(rule, "condition_type", None)
    operator = rule.get("condition_operator") if isinstance(rule, dict) else getattr(rule, "condition_operator", None)
    expected = rule.get("condition_value") if isinstance(rule, dict) else getattr(rule, "condition_value", None)

    if not condition_type or not operator or not expected:
        return False

    # Get the actual value from seller attributes
    if condition_type == "custom":
        # For custom conditions, condition_value format: "field_name:expected_value"
        # But we still use condition_value as the expected value and
        # the actual field is derived from the type mapping
        actual_value = seller_attrs.get(condition_type)
    else:
        actual_value = seller_attrs.get(
            CONDITION_TYPE_FIELD_MAP.get(condition_type, condition_type)
        )

    if actual_value is None:
        return False

    return _apply_operator(operator, actual_value, expected)


def compile_contract(template_name, seller_name):
    """
    Compile a contract template for a specific seller.

    Loads the template's base_text, evaluates all active condition_rules
    against the seller's attributes, applies matching rules in sequence
    (priority/clause_order), and saves the result as a Contract Compiled
    Output record.

    The compilation pipeline:
        1. Load template and validate dynamic rules are enabled
        2. Fetch seller attributes
        3. Evaluate each active condition rule
        4. Sort matching rules by evaluation order
        5. Apply conflict resolution strategy
        6. Execute clause actions (add/remove/replace)
        7. Generate content hash
        8. Save Contract Compiled Output
        9. Return result with compilation log

    Args:
        template_name: Name (ID) of the Contract Template document.
        seller_name: Name (ID) of the Seller Profile document.

    Returns:
        dict: {
            "compiled_content": str (the final compiled contract text),
            "compilation_log": list (step-by-step log of compilation),
            "rules_applied": int (count of rules that were applied),
            "rules_skipped": int (count of rules that did not match),
            "content_hash": str (SHA256 hash of compiled content),
            "compiled_output_name": str (name of saved Compiled Output doc),
        }
    """
    compilation_log = []

    # Step 1: Load template
    template = frappe.get_doc("Contract Template", template_name)
    base_text = getattr(template, "base_text", None) or template.content or ""
    dynamic_enabled = cint(getattr(template, "dynamic_rules_enabled", 0))

    if not dynamic_enabled:
        compilation_log.append({
            "step": "init",
            "message": "Dynamic rules not enabled, using static content",
            "timestamp": str(now_datetime()),
        })
        content_hash = _calculate_hash(base_text)
        return {
            "compiled_content": base_text,
            "compilation_log": compilation_log,
            "rules_applied": 0,
            "rules_skipped": 0,
            "content_hash": content_hash,
            "compiled_output_name": None,
        }

    compilation_log.append({
        "step": "init",
        "message": f"Starting compilation for template '{template_name}' and seller '{seller_name}'",
        "timestamp": str(now_datetime()),
    })

    # Step 2: Fetch seller attributes
    seller_attrs = get_seller_attributes(seller_name)
    compilation_log.append({
        "step": "seller_attributes",
        "message": f"Fetched seller attributes: {seller_attrs}",
        "timestamp": str(now_datetime()),
    })

    # Step 3: Get active condition rules from template
    condition_rules = getattr(template, "condition_rules", None) or []
    active_rules = [r for r in condition_rules if cint(r.get("is_active") if isinstance(r, dict) else r.is_active)]

    if not active_rules:
        compilation_log.append({
            "step": "evaluation",
            "message": "No active condition rules found",
            "timestamp": str(now_datetime()),
        })
        content_hash = _calculate_hash(base_text)
        return {
            "compiled_content": base_text,
            "compilation_log": compilation_log,
            "rules_applied": 0,
            "rules_skipped": 0,
            "content_hash": content_hash,
            "compiled_output_name": None,
        }

    # Step 4: Evaluate conditions and collect matching rules
    matching_rules = []
    skipped_rules = []

    for rule in active_rules:
        rule_name = rule.get("rule_name") if isinstance(rule, dict) else rule.rule_name
        if evaluate_condition(rule, seller_attrs):
            matching_rules.append(rule)
            compilation_log.append({
                "step": "evaluation",
                "rule": rule_name,
                "result": "matched",
                "timestamp": str(now_datetime()),
            })
        else:
            skipped_rules.append(rule)
            compilation_log.append({
                "step": "evaluation",
                "rule": rule_name,
                "result": "skipped",
                "timestamp": str(now_datetime()),
            })

    # Step 5: Sort matching rules by evaluation order
    evaluation_order = getattr(template, "rule_evaluation_order", "priority_first") or "priority_first"
    matching_rules = _sort_rules(matching_rules, evaluation_order)

    # Step 6: Apply conflict resolution strategy
    conflict_resolution = getattr(template, "conflict_resolution", "all_matching") or "all_matching"
    rules_to_apply = _resolve_conflicts(matching_rules, conflict_resolution)

    compilation_log.append({
        "step": "conflict_resolution",
        "strategy": conflict_resolution,
        "evaluation_order": evaluation_order,
        "rules_to_apply": len(rules_to_apply),
        "rules_filtered": len(matching_rules) - len(rules_to_apply),
        "timestamp": str(now_datetime()),
    })

    # Step 7: Execute clause actions on base_text
    compiled_content = base_text
    applied_count = 0

    for rule in rules_to_apply:
        rule_name = rule.get("rule_name") if isinstance(rule, dict) else rule.rule_name
        action = rule.get("action") if isinstance(rule, dict) else rule.action
        clause_text = rule.get("clause_text") if isinstance(rule, dict) else rule.clause_text
        clause_marker = rule.get("clause_marker") if isinstance(rule, dict) else rule.clause_marker

        before_content = compiled_content

        if action == "add_clause":
            compiled_content = _action_add_clause(compiled_content, clause_text, clause_marker)
        elif action == "remove_clause":
            compiled_content = _action_remove_clause(compiled_content, clause_marker)
        elif action == "replace_clause":
            compiled_content = _action_replace_clause(compiled_content, clause_text, clause_marker)

        if compiled_content != before_content:
            applied_count += 1
            compilation_log.append({
                "step": "apply",
                "rule": rule_name,
                "action": action,
                "marker": clause_marker or "(none)",
                "result": "applied",
                "timestamp": str(now_datetime()),
            })
        else:
            compilation_log.append({
                "step": "apply",
                "rule": rule_name,
                "action": action,
                "marker": clause_marker or "(none)",
                "result": "no_change",
                "timestamp": str(now_datetime()),
            })

    # Step 8: Generate content hash
    content_hash = _calculate_hash(compiled_content)

    # Step 9: Save Contract Compiled Output
    compiled_output_name = _save_compiled_output(
        template_name=template_name,
        seller_name=seller_name,
        compiled_content=compiled_content,
        compilation_log=compilation_log,
        rules_applied=applied_count,
        rules_skipped=len(skipped_rules),
        content_hash=content_hash,
    )

    compilation_log.append({
        "step": "finalize",
        "message": f"Compilation complete. Applied {applied_count} rules, skipped {len(skipped_rules)}",
        "compiled_output": compiled_output_name,
        "content_hash": content_hash,
        "timestamp": str(now_datetime()),
    })

    frappe.logger("rule_engine").info(
        f"Contract compiled: template={template_name}, seller={seller_name}, "
        f"applied={applied_count}, skipped={len(skipped_rules)}"
    )

    return {
        "compiled_content": compiled_content,
        "compilation_log": compilation_log,
        "rules_applied": applied_count,
        "rules_skipped": len(skipped_rules),
        "content_hash": content_hash,
        "compiled_output_name": compiled_output_name,
    }


def validate_markers(template):
    """
    Compare markers in base_text with markers referenced in condition rules.

    Checks for:
        - Missing markers: Referenced in rules but not found in base_text
        - Orphaned markers: Present in base_text but not referenced by any rule

    Issues warnings via frappe.msgprint with orange indicator for any
    discrepancies found.

    Args:
        template: A Contract Template document (or any object with
            base_text/content and condition_rules attributes).
    """
    base_text = getattr(template, "base_text", None) or getattr(template, "content", "") or ""
    condition_rules = getattr(template, "condition_rules", None) or []

    # Extract markers from base_text
    text_markers = set(MARKER_PATTERN.findall(base_text))

    # Extract markers from rules
    rule_markers = set()
    for rule in condition_rules:
        marker = rule.get("clause_marker") if isinstance(rule, dict) else getattr(rule, "clause_marker", None)
        if marker:
            # Strip {{ }} if present
            clean_marker = marker.strip().strip("{}").strip()
            if clean_marker:
                rule_markers.add(clean_marker)

    # Find discrepancies
    missing_markers = rule_markers - text_markers
    orphaned_markers = text_markers - rule_markers

    if missing_markers:
        frappe.msgprint(
            _("The following markers are referenced in rules but not found in base text: {0}").format(
                ", ".join(sorted(missing_markers))
            ),
            title=_("Missing Markers"),
            indicator="orange",
        )

    if orphaned_markers:
        frappe.msgprint(
            _("The following markers are in base text but not referenced by any rule: {0}").format(
                ", ".join(sorted(orphaned_markers))
            ),
            title=_("Orphaned Markers"),
            indicator="orange",
        )


def analyze_rule_impact(rule_name):
    """
    Analyze which active sellers would be affected by a specific rule.

    Queries all active Seller Profiles, evaluates the given condition
    rule against each seller's attributes, and returns a list of
    affected seller names.

    Args:
        rule_name: The rule_name value of the Contract Condition Rule
            to analyze. This searches across all Contract Templates'
            condition_rules child tables.

    Returns:
        list: List of affected seller names (Seller Profile IDs).
            Empty list if no sellers are affected or rule not found.
    """
    # Find the rule across all templates' condition_rules
    rule = _find_rule_by_name(rule_name)

    if not rule:
        frappe.logger("rule_engine").warning(
            f"Rule '{rule_name}' not found in any Contract Template"
        )
        return []

    # Get all active sellers
    active_sellers = frappe.get_all(
        "Seller Profile",
        filters={"status": "Active"},
        pluck="name",
    )

    if not active_sellers:
        return []

    affected = []
    for seller_name in active_sellers:
        try:
            seller_attrs = get_seller_attributes(seller_name)
            if evaluate_condition(rule, seller_attrs):
                affected.append(seller_name)
        except Exception:
            # Skip sellers that fail attribute fetch
            frappe.logger("rule_engine").warning(
                f"Failed to evaluate rule for seller {seller_name}"
            )

    frappe.logger("rule_engine").info(
        f"Rule impact analysis for '{rule_name}': {len(affected)}/{len(active_sellers)} sellers affected"
    )

    return affected


# ===========================================================================
# Private helpers
# ===========================================================================


def _get_seller_package(seller_name):
    """
    Get the active subscription package name for a seller.

    Args:
        seller_name: Seller Profile name.

    Returns:
        str: Package name or empty string if no active subscription.
    """
    package = frappe.db.get_value(
        "Subscription",
        {
            "seller_profile": seller_name,
            "subscriber_type": "Seller",
            "status": ["in", ["Active", "Pending Payment", "Grace Period"]],
        },
        "subscription_package",
    )
    return package or ""


def _get_seller_category(seller_name, seller_data):
    """
    Get the seller's primary category.

    Attempts to derive from organization or seller tier.

    Args:
        seller_name: Seller Profile name.
        seller_data: Dict of seller profile data.

    Returns:
        str: Category name or empty string.
    """
    # Try to get category from organization
    if seller_data.get("organization"):
        category = frappe.db.get_value(
            "Organization",
            seller_data["organization"],
            "category",
        )
        if category:
            return category

    # Fall back to seller tier as category proxy
    return seller_data.get("seller_tier") or ""


def _apply_operator(operator, actual_value, expected_value):
    """
    Apply a comparison operator between actual and expected values.

    Args:
        operator: One of the 8 supported operators.
        actual_value: The actual value from seller attributes.
        expected_value: The expected value from the condition rule.

    Returns:
        bool: True if comparison matches, False otherwise.
    """
    if operator == "equals":
        return str(actual_value).lower() == str(expected_value).lower()

    elif operator == "not_equals":
        return str(actual_value).lower() != str(expected_value).lower()

    elif operator == "in":
        values = [v.strip().lower() for v in expected_value.split(",")]
        return str(actual_value).lower() in values

    elif operator == "not_in":
        values = [v.strip().lower() for v in expected_value.split(",")]
        return str(actual_value).lower() not in values

    elif operator == "greater_than":
        try:
            return flt(actual_value) > flt(expected_value)
        except (ValueError, TypeError):
            return False

    elif operator == "less_than":
        try:
            return flt(actual_value) < flt(expected_value)
        except (ValueError, TypeError):
            return False

    elif operator == "between":
        try:
            values = [v.strip() for v in expected_value.split(",")]
            if len(values) != 2:
                return False
            return flt(values[0]) <= flt(actual_value) <= flt(values[1])
        except (ValueError, TypeError):
            return False

    elif operator == "contains":
        return str(expected_value).lower() in str(actual_value).lower()

    return False


def _sort_rules(rules, evaluation_order):
    """
    Sort matching rules by the specified evaluation order.

    Args:
        rules: List of matching rule documents/dicts.
        evaluation_order: "priority_first" or "clause_order_first".

    Returns:
        list: Sorted rules.
    """
    def _get_field(rule, field, default=0):
        if isinstance(rule, dict):
            return rule.get(field, default)
        return getattr(rule, field, default)

    if evaluation_order == "clause_order_first":
        return sorted(
            rules,
            key=lambda r: (cint(_get_field(r, "clause_order")), cint(_get_field(r, "priority", 10))),
        )
    else:
        # priority_first (default) — lower priority number = higher priority
        return sorted(
            rules,
            key=lambda r: (cint(_get_field(r, "priority", 10)), cint(_get_field(r, "clause_order"))),
        )


def _resolve_conflicts(matching_rules, strategy):
    """
    Apply conflict resolution strategy to matching rules.

    Strategies:
        first_match    — Only the first matching rule per marker is kept
        all_matching   — All matching rules are applied (no filtering)
        priority_based — For each marker, only the highest-priority
                         (lowest priority number) rule is kept

    Args:
        matching_rules: List of sorted matching rule documents/dicts.
        strategy: One of "first_match", "all_matching", "priority_based".

    Returns:
        list: Filtered rules to apply.
    """
    if strategy == "all_matching" or not matching_rules:
        return list(matching_rules)

    def _get_field(rule, field, default=None):
        if isinstance(rule, dict):
            return rule.get(field, default)
        return getattr(rule, field, default)

    if strategy == "first_match":
        seen_markers = set()
        result = []
        for rule in matching_rules:
            marker = _get_field(rule, "clause_marker")
            action = _get_field(rule, "action")
            # Group key: marker + action combination
            key = f"{marker or ''}:{action or ''}"
            if key not in seen_markers:
                seen_markers.add(key)
                result.append(rule)
        return result

    elif strategy == "priority_based":
        # Group rules by marker, keep only highest priority per marker
        marker_groups = {}
        for rule in matching_rules:
            marker = _get_field(rule, "clause_marker") or ""
            action = _get_field(rule, "action") or ""
            key = f"{marker}:{action}"
            priority = cint(_get_field(rule, "priority", 10))

            if key not in marker_groups or priority < marker_groups[key]["priority"]:
                marker_groups[key] = {"rule": rule, "priority": priority}

        return [entry["rule"] for entry in marker_groups.values()]

    # Fallback to all_matching
    return list(matching_rules)


def _action_add_clause(content, clause_text, marker=None):
    """
    Add (append) clause text to content.

    If marker is specified, appends after the marker position.
    Otherwise, appends at the end of the content.

    Args:
        content: Current compiled content.
        clause_text: Text to add.
        marker: Optional marker to insert after.

    Returns:
        str: Updated content.
    """
    if not clause_text:
        return content

    if marker:
        marker_tag = "{{" + marker.strip().strip("{}").strip() + "}}"
        marker_pos = content.find(marker_tag)
        if marker_pos >= 0:
            insert_pos = marker_pos + len(marker_tag)
            return content[:insert_pos] + "\n" + clause_text + content[insert_pos:]

    # No marker or marker not found — append at end
    return content + "\n" + clause_text


def _action_remove_clause(content, marker):
    """
    Remove a marker block from content.

    Removes the marker tag and any content between matching
    start/end markers ({{MARKER}} ... {{/MARKER}}) or just the
    single marker tag if no end marker exists.

    Args:
        content: Current compiled content.
        marker: Marker name to remove.

    Returns:
        str: Updated content with marker block removed.
    """
    if not marker:
        return content

    clean_marker = marker.strip().strip("{}").strip()

    # Try to remove block: {{MARKER}}...{{/MARKER}}
    block_pattern = re.compile(
        r"\{\{" + re.escape(clean_marker) + r"\}\}.*?\{\{/" + re.escape(clean_marker) + r"\}\}",
        re.DOTALL,
    )
    result = block_pattern.sub("", content)

    if result != content:
        return result.strip()

    # Fallback: remove just the marker tag
    marker_tag = "{{" + clean_marker + "}}"
    return content.replace(marker_tag, "").strip()


def _action_replace_clause(content, clause_text, marker):
    """
    Replace a marker with clause text.

    Replaces {{MARKER}} with the clause text. If the marker uses
    block syntax ({{MARKER}}...{{/MARKER}}), replaces the entire block.

    Args:
        content: Current compiled content.
        clause_text: Replacement text.
        marker: Marker name to replace.

    Returns:
        str: Updated content with marker replaced.
    """
    if not marker:
        return content

    clean_marker = marker.strip().strip("{}").strip()

    # Try to replace block: {{MARKER}}...{{/MARKER}}
    block_pattern = re.compile(
        r"\{\{" + re.escape(clean_marker) + r"\}\}.*?\{\{/" + re.escape(clean_marker) + r"\}\}",
        re.DOTALL,
    )
    result = block_pattern.sub(clause_text or "", content)

    if result != content:
        return result

    # Fallback: replace just the marker tag
    marker_tag = "{{" + clean_marker + "}}"
    return content.replace(marker_tag, clause_text or "")


def _calculate_hash(content):
    """
    Calculate SHA256 hash of content.

    Args:
        content: Text content to hash.

    Returns:
        str: Hexadecimal SHA256 hash, or None if content is empty.
    """
    if not content:
        return None
    normalized = content.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _save_compiled_output(
    template_name,
    seller_name,
    compiled_content,
    compilation_log,
    rules_applied,
    rules_skipped,
    content_hash,
):
    """
    Save the compiled contract as a Contract Compiled Output record.

    Args:
        template_name: Contract Template name.
        seller_name: Seller Profile name.
        compiled_content: The compiled content text.
        compilation_log: List of compilation log entries.
        rules_applied: Number of rules applied.
        rules_skipped: Number of rules skipped.
        content_hash: SHA256 hash of compiled content.

    Returns:
        str: Name of the created Contract Compiled Output doc.
    """
    import json

    doc = frappe.get_doc({
        "doctype": "Contract Compiled Output",
        "contract_template": template_name,
        "seller": seller_name,
        "compiled_content": compiled_content,
        "compilation_log": json.dumps(compilation_log, ensure_ascii=False, indent=2),
        "rules_applied": cint(rules_applied),
        "rules_skipped": cint(rules_skipped),
        "content_hash": content_hash,
        "compiled_at": now_datetime(),
        "compiled_by": frappe.session.user,
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


def _find_rule_by_name(rule_name):
    """
    Find a Contract Condition Rule by its rule_name across all templates.

    Searches all Contract Template documents' condition_rules child tables
    for a matching rule_name.

    Args:
        rule_name: The rule_name to search for.

    Returns:
        dict or None: The matching rule as a dict, or None if not found.
    """
    # Query the child table directly for efficiency
    rules = frappe.get_all(
        "Contract Condition Rule",
        filters={"rule_name": rule_name, "is_active": 1},
        fields=[
            "rule_name",
            "condition_type",
            "condition_operator",
            "condition_value",
            "action",
            "clause_text",
            "clause_marker",
            "clause_order",
            "priority",
            "is_active",
        ],
        limit=1,
    )

    return rules[0] if rules else None
