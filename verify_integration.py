#!/usr/bin/env python3
"""
End-to-end integration verification for subtask-9-2.

This script validates the complete implementation of 17 new DocTypes,
field modifications on existing DocTypes, seed scripts, utility modules,
and Buy Box Settings defaults — all without requiring a bench environment.

For the bench-environment steps (migrate, clear-cache, seed execution),
see the BENCH_STEPS section at the bottom or run:

    bench --site [site] migrate
    bench --site [site] clear-cache
    bench --site [site] execute tradehub_compliance.tradehub_compliance.setup.ensure_anonymous_id_secret
    bench --site [site] execute tradehub_compliance.tradehub_compliance.setup.seed_default_visibility_rules
    bench --site [site] execute tradehub_compliance.tradehub_compliance.setup.create_transparency_consent_topics
    bench --site [site] execute tradehub_catalog.tradehub_catalog.wishlist.tasks.reconcile_social_proof_counters
"""

import ast
import json
import os
import sys

BASE = "./frappe-bench/apps"


def check_json_valid(filepath):
    """Return (True, data) or (False, error)."""
    if not os.path.exists(filepath):
        return False, None, "MISSING"
    try:
        with open(filepath) as f:
            data = json.load(f)
        return True, data, "OK"
    except json.JSONDecodeError as e:
        return False, None, str(e)


def check_py_syntax(filepath):
    """Return (True, tree) or (False, error)."""
    if not os.path.exists(filepath):
        return False, None, "MISSING"
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read())
        return True, tree, "OK"
    except SyntaxError as e:
        return False, None, str(e)


def get_functions(tree):
    """Extract function names from AST."""
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def get_field_names(data):
    """Extract fieldnames from DocType JSON."""
    return {f["fieldname"] for f in data.get("fields", [])}


class Verifier:
    def __init__(self):
        self.passes = 0
        self.failures = []

    def check(self, label, condition, detail=""):
        if condition:
            self.passes += 1
        else:
            self.failures.append(f"  FAIL: {label} - {detail}")

    def report(self):
        total = self.passes + len(self.failures)
        print()
        print("=" * 70)
        print(f"RESULTS: {self.passes} passed, {len(self.failures)} failed, {total} total")

        if self.failures:
            print()
            print("FAILURES:")
            for f in self.failures:
                print(f)
            print()
            print("OVERALL: SOME CHECKS FAILED")
        else:
            print()
            print("OVERALL: ALL CHECKS PASSED")
        print("=" * 70)
        return len(self.failures) == 0


def main():
    v = Verifier()

    print("=" * 70)
    print("END-TO-END INTEGRATION VERIFICATION — Subtask 9-2")
    print("=" * 70)

    # ======================================================================
    # 1. ALL 15 NEW DOCTYPES
    # ======================================================================
    print("\n--- 1. ALL 15 NEW DOCTYPES (JSON + Python + __init__.py) ---")

    NEW_DOCTYPES = {
        # 5 child tables
        "wishlist_item": f"{BASE}/tradehub_catalog/tradehub_catalog/tradehub_catalog/doctype/wishlist_item",
        "seller_certificate": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/seller_certificate",
        "seller_audit_report": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/seller_audit_report",
        "audience_segment_member": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/audience_segment_member",
        "buy_box_tier_bonus": f"{BASE}/tradehub_seller/tradehub_seller/tradehub_seller/doctype/buy_box_tier_bonus",
        # 10 parent / single / independent
        "user_wishlist": f"{BASE}/tradehub_catalog/tradehub_catalog/tradehub_catalog/doctype/user_wishlist",
        "quick_favorite": f"{BASE}/tradehub_catalog/tradehub_catalog/tradehub_catalog/doctype/quick_favorite",
        "seller_transparency_profile": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/seller_transparency_profile",
        "buyer_transparency_profile": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/buyer_transparency_profile",
        "data_sharing_preference": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/data_sharing_preference",
        "buyer_visibility_rule": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/buyer_visibility_rule",
        "audience_segment": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/audience_segment",
        "masked_message": f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/doctype/masked_message",
        "buy_box_settings": f"{BASE}/tradehub_seller/tradehub_seller/tradehub_seller/doctype/buy_box_settings",
        "buy_box_log": f"{BASE}/tradehub_seller/tradehub_seller/tradehub_seller/doctype/buy_box_log",
    }

    CHILD_TABLES = [
        "wishlist_item", "seller_certificate", "seller_audit_report",
        "audience_segment_member", "buy_box_tier_bonus",
    ]

    doctype_count = 0
    for name, path in NEW_DOCTYPES.items():
        json_file = f"{path}/{name}.json"
        py_file = f"{path}/{name}.py"
        init_file = f"{path}/__init__.py"

        ok, data, msg = check_json_valid(json_file)
        v.check(f"{name}.json valid", ok, msg)
        if ok:
            doctype_count += 1
            v.check(f"{name} has fields", len(data.get("fields", [])) > 0)

            if name in CHILD_TABLES:
                v.check(f"{name} istable=1", data.get("istable") == 1,
                        f"istable={data.get('istable')}")

            if name == "buy_box_settings":
                v.check(f"{name} issingle=1", data.get("issingle") == 1,
                        f"issingle={data.get('issingle')}")

        ok, _, msg = check_py_syntax(py_file)
        v.check(f"{name}.py syntax", ok, msg)

        v.check(f"{name}/__init__.py", os.path.exists(init_file),
                "MISSING" if not os.path.exists(init_file) else "")

    print(f"  DocTypes found: {doctype_count}/15")

    # ======================================================================
    # 2. BUY BOX SETTINGS WEIGHT DEFAULTS
    # ======================================================================
    print("\n--- 2. BUY BOX SETTINGS WEIGHT DEFAULTS ---")

    bbs_path = f"{BASE}/tradehub_seller/tradehub_seller/tradehub_seller/doctype/buy_box_settings/buy_box_settings.json"
    _, bbs_data, _ = check_json_valid(bbs_path)

    expected_weights = {
        "price_weight": "0.35",
        "delivery_weight": "0.20",
        "rating_weight": "0.20",
        "stock_weight": "0.15",
        "service_weight": "0.05",
        "tier_weight": "0.05",
    }

    total_weight = 0.0
    if bbs_data:
        for fieldname, expected_default in expected_weights.items():
            for field in bbs_data.get("fields", []):
                if field.get("fieldname") == fieldname:
                    actual = str(field.get("default", ""))
                    v.check(f"{fieldname}={expected_default}",
                            actual == expected_default, f"actual={actual}")
                    total_weight += float(actual or 0)
                    break
            else:
                v.check(f"{fieldname} exists", False, "field not found")

    v.check("Total weights sum = 1.0", abs(total_weight - 1.0) < 0.001,
            f"actual sum={total_weight}")
    print(f"  Weight sum: {total_weight}")

    # ======================================================================
    # 3. MODIFIED DOCTYPES — SOCIAL PROOF COUNTERS
    # ======================================================================
    print("\n--- 3. MODIFIED DOCTYPES (social proof + Buy Box Entry + Notification) ---")

    # Product: wishlist_count + favorite_count
    _, pdata, _ = check_json_valid(
        f"{BASE}/tradehub_catalog/tradehub_catalog/tradehub_catalog/doctype/product/product.json")
    if pdata:
        pfields = get_field_names(pdata)
        v.check("Product.wishlist_count", "wishlist_count" in pfields)
        v.check("Product.favorite_count", "favorite_count" in pfields)

    # Seller Profile: favorite_count + total_wishlist_count
    _, spdata, _ = check_json_valid(
        f"{BASE}/tradehub_seller/tradehub_seller/tradehub_seller/doctype/seller_profile/seller_profile.json")
    if spdata:
        spfields = get_field_names(spdata)
        v.check("SellerProfile.favorite_count", "favorite_count" in spfields)
        v.check("SellerProfile.total_wishlist_count", "total_wishlist_count" in spfields)

    # Seller Store: favorite_count
    _, ssdata, _ = check_json_valid(
        f"{BASE}/tradehub_seller/tradehub_seller/tradehub_seller/doctype/seller_store/seller_store.json")
    if ssdata:
        ssfields = get_field_names(ssdata)
        v.check("SellerStore.favorite_count", "favorite_count" in ssfields)

    # Buy Box Entry: 9 new fields
    _, bbedata, _ = check_json_valid(
        f"{BASE}/tradehub_seller/tradehub_seller/tradehub_seller/doctype/buy_box_entry/buy_box_entry.json")
    if bbedata:
        bbefields = get_field_names(bbedata)
        for fname in ["service_score", "seller_tier_bonus", "rank",
                       "total_competitors", "is_disqualified",
                       "disqualification_reason", "score_breakdown_json",
                       "improvement_suggestions", "last_winner_change"]:
            v.check(f"BuyBoxEntry.{fname}", fname in bbefields)

    # Notification Template: 3 new event types
    _, ntdata, _ = check_json_valid(
        f"{BASE}/tradehub_core/tradehub_core/tradehub_core/doctype/notification_template/notification_template.json")
    if ntdata:
        for field in ntdata.get("fields", []):
            if field.get("fieldname") == "event_type":
                opts = field.get("options", "")
                for evt in ["Back In Stock", "Wishlist Share", "Wishlist Digest"]:
                    v.check(f'NotificationTemplate event_type has "{evt}"',
                            evt in opts)
                break

    # RFQ Quote: items Table field + field_order completeness
    _, rqdata, _ = check_json_valid(
        f"{BASE}/tradehub_commerce/tradehub_commerce/tradehub_commerce/doctype/rfq_quote/rfq_quote.json")
    if rqdata:
        rqfields = get_field_names(rqdata)
        v.check("RFQQuote.items (Table)", "items" in rqfields)
        all_fnames = [f["fieldname"] for f in rqdata.get("fields", [])]
        field_order = rqdata.get("field_order", [])
        missing = [fn for fn in all_fnames if fn not in field_order]
        v.check("RFQQuote field_order complete", len(missing) == 0,
                f"missing: {missing}")

    # RFQ Quote Item: field_order completeness
    _, rqidata, _ = check_json_valid(
        f"{BASE}/tradehub_commerce/tradehub_commerce/tradehub_commerce/doctype/rfq_quote_item/rfq_quote_item.json")
    if rqidata:
        all_fnames = [f["fieldname"] for f in rqidata.get("fields", [])]
        field_order = rqidata.get("field_order", [])
        missing = [fn for fn in all_fnames if fn not in field_order]
        v.check("RFQQuoteItem field_order complete", len(missing) == 0,
                f"missing: {missing}")

    # ======================================================================
    # 4. SEED / SETUP SCRIPTS
    # ======================================================================
    print("\n--- 4. SEED / SETUP SCRIPTS ---")

    setup_py = f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/setup.py"
    ok, tree, msg = check_py_syntax(setup_py)
    v.check("compliance setup.py exists + valid", ok, msg)

    if tree:
        funcs = get_functions(tree)
        for fn in ["ensure_anonymous_id_secret", "seed_default_visibility_rules",
                    "create_transparency_consent_topics"]:
            v.check(f"setup.{fn}()", fn in funcs)

    tasks_py = f"{BASE}/tradehub_catalog/tradehub_catalog/tradehub_catalog/wishlist/tasks.py"
    ok, tree, msg = check_py_syntax(tasks_py)
    v.check("wishlist/tasks.py exists + valid", ok, msg)

    if tree:
        funcs = get_functions(tree)
        v.check("reconcile_social_proof_counters()",
                "reconcile_social_proof_counters" in funcs)

    # ======================================================================
    # 5. CORE UTILITY MODULES
    # ======================================================================
    print("\n--- 5. CORE UTILITY MODULES ---")

    # Anonymous buyer ID generator
    anon_py = f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/anonymization/anonymous_buyer.py"
    ok, tree, _ = check_py_syntax(anon_py)
    v.check("anonymous_buyer.py exists + valid", ok)
    if tree:
        funcs = get_functions(tree)
        v.check("generate_anonymous_buyer_id()",
                "generate_anonymous_buyer_id" in funcs)

    # PII Scanner
    pii_py = f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/messaging/pii_scanner.py"
    ok, tree, _ = check_py_syntax(pii_py)
    v.check("pii_scanner.py exists + valid", ok)
    if tree:
        funcs = get_functions(tree)
        for fn in ["scan_for_pii", "sanitize_message"]:
            v.check(f"pii_scanner.{fn}()", fn in funcs)

    # Transparency utils
    trans_py = f"{BASE}/tradehub_compliance/tradehub_compliance/tradehub_compliance/transparency/utils.py"
    ok, tree, _ = check_py_syntax(trans_py)
    v.check("transparency/utils.py exists + valid", ok)
    if tree:
        funcs = get_functions(tree)
        v.check("get_disclosure_stage()", "get_disclosure_stage" in funcs)

    # ======================================================================
    # 6. HOOKS.PY SYNTAX VERIFICATION
    # ======================================================================
    print("\n--- 6. HOOKS.PY FILES ---")

    for app_name in ["tradehub_catalog", "tradehub_compliance",
                      "tradehub_seller", "tradehub_commerce"]:
        hooks_py = f"{BASE}/{app_name}/{app_name}/hooks.py"
        ok, _, msg = check_py_syntax(hooks_py)
        v.check(f"{app_name}/hooks.py syntax", ok, msg)

    # ======================================================================
    # 7. ALL DOCTYPE JSON FILES VALID
    # ======================================================================
    print("\n--- 7. GLOBAL JSON VALIDITY ---")

    json_errors = 0
    json_count = 0
    for root, _, files in os.walk(BASE):
        for fname in files:
            if fname.endswith(".json") and "/doctype/" in os.path.join(root, fname):
                json_count += 1
                fp = os.path.join(root, fname)
                try:
                    with open(fp) as fh:
                        json.load(fh)
                except json.JSONDecodeError:
                    json_errors += 1

    v.check(f"All {json_count} DocType JSONs valid", json_errors == 0,
            f"{json_errors} errors")

    # ======================================================================
    # 8. BENCH-ENVIRONMENT STEPS DOCUMENTATION
    # ======================================================================
    print("\n--- 8. BENCH-ENVIRONMENT STEPS (manual) ---")
    print("  The following must be run in the bench environment:")
    print("  1. bench --site [site] migrate")
    print("  2. bench --site [site] clear-cache")
    print("  3. bench --site [site] execute "
          "tradehub_compliance.tradehub_compliance.setup.ensure_anonymous_id_secret")
    print("  4. bench --site [site] execute "
          "tradehub_compliance.tradehub_compliance.setup.seed_default_visibility_rules")
    print("  5. bench --site [site] execute "
          "tradehub_compliance.tradehub_compliance.setup.create_transparency_consent_topics")
    print("  6. bench --site [site] execute "
          "tradehub_catalog.tradehub_catalog.wishlist.tasks.reconcile_social_proof_counters")
    print("  7. Verify all 15 new DocTypes listed via frappe.get_meta()")
    print("  8. Verify Buy Box Settings defaults (weights sum = 1.0)")
    print("  9. Verify no Python exceptions in error log")

    # ======================================================================
    # FINAL RESULT
    # ======================================================================
    success = v.report()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
