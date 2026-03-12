#!/usr/bin/env bash
# =============================================================================
# TradeHub Translation CI Linting Script
# =============================================================================
# Performs 4 checks to ensure i18n compliance across all TradeHub apps:
#   1. No unwrapped Python strings in frappe.throw/frappe.msgprint
#   2. No unwrapped JS strings in frappe.show_alert/frappe.msgprint/frappe.throw
#   3. No frappe._() usage (should use: from frappe import _ then _())
#   4. All translation CSV files (tr.csv) exist for every app
#
# Usage:
#   bash scripts/check_translations.sh
#
# Exit code:
#   0 - All checks passed
#   1 - One or more checks failed
# =============================================================================

set -euo pipefail

APPS_DIR="frappe-bench/apps"
ERRORS=0

# List of all TradeHub apps that require translations
APPS=(
    "tradehub_core"
    "tradehub_catalog"
    "tradehub_seller"
    "tradehub_commerce"
    "tradehub_compliance"
    "tradehub_logistics"
    "tradehub_marketing"
    "tr_tradehub"
)

echo "========================================"
echo " TradeHub Translation Linting"
echo "========================================"
echo ""

# --------------------------------------------------------------------------
# Check 1: No unwrapped Python strings in frappe.throw / frappe.msgprint
# --------------------------------------------------------------------------
echo "Check 1: Unwrapped Python strings in frappe.throw/frappe.msgprint..."

# Find frappe.throw("...") or frappe.msgprint("...") that are NOT wrapped with _()
# Correct patterns: frappe.throw(_("...")), frappe.msgprint(_("..."))
# Incorrect patterns: frappe.throw("..."), frappe.msgprint("...")
UNWRAPPED_PY=$(grep -rn \
    --include="*.py" \
    -E 'frappe\.(throw|msgprint)\s*\(\s*["\x27]' \
    "$APPS_DIR"/tradehub_*/  "$APPS_DIR"/tr_tradehub/ 2>/dev/null \
    | grep -v '_(' \
    | grep -v '#' \
    | grep -v 'test_' \
    | grep -v '__pycache__' \
    || true)

if [ -n "$UNWRAPPED_PY" ]; then
    echo "  FAIL: Found unwrapped Python strings:"
    echo "$UNWRAPPED_PY" | head -20
    COUNT=$(echo "$UNWRAPPED_PY" | wc -l)
    echo "  ... ($COUNT total occurrences)"
    ERRORS=$((ERRORS + 1))
else
    echo "  PASS: All frappe.throw/frappe.msgprint strings are wrapped with _()"
fi
echo ""

# --------------------------------------------------------------------------
# Check 2: No unwrapped JS strings in frappe.show_alert/msgprint/throw
# --------------------------------------------------------------------------
echo "Check 2: Unwrapped JavaScript strings in frappe.show_alert/msgprint/throw..."

# Find frappe.show_alert("..."), frappe.msgprint("..."), frappe.throw("...")
# that are NOT wrapped with __()
UNWRAPPED_JS=$(grep -rn \
    --include="*.js" \
    -E 'frappe\.(show_alert|msgprint|throw)\s*\(\s*["\x27]' \
    "$APPS_DIR"/tradehub_*/  "$APPS_DIR"/tr_tradehub/ 2>/dev/null \
    | grep -v '__(' \
    | grep -v '//' \
    | grep -v 'node_modules' \
    | grep -v '.bundle.' \
    || true)

if [ -n "$UNWRAPPED_JS" ]; then
    echo "  FAIL: Found unwrapped JavaScript strings:"
    echo "$UNWRAPPED_JS" | head -20
    COUNT=$(echo "$UNWRAPPED_JS" | wc -l)
    echo "  ... ($COUNT total occurrences)"
    ERRORS=$((ERRORS + 1))
else
    echo "  PASS: All frappe.show_alert/msgprint/throw strings are wrapped with __()"
fi
echo ""

# --------------------------------------------------------------------------
# Check 3: No frappe._() usage (should be: from frappe import _ then _())
# --------------------------------------------------------------------------
echo "Check 3: Deprecated frappe._() usage (should use 'from frappe import _')..."

# Find frappe._("...") calls which should be normalized to _("...")
FRAPPE_UNDERSCORE=$(grep -rn \
    --include="*.py" \
    -E 'frappe\._\s*\(' \
    "$APPS_DIR"/tradehub_*/  "$APPS_DIR"/tr_tradehub/ 2>/dev/null \
    | grep -v '#' \
    | grep -v '__pycache__' \
    | grep -v 'test_' \
    || true)

if [ -n "$FRAPPE_UNDERSCORE" ]; then
    echo "  FAIL: Found frappe._() usage (should be: from frappe import _ then _()):"
    echo "$FRAPPE_UNDERSCORE" | head -20
    COUNT=$(echo "$FRAPPE_UNDERSCORE" | wc -l)
    echo "  ... ($COUNT total occurrences)"
    ERRORS=$((ERRORS + 1))
else
    echo "  PASS: No frappe._() usage found - all using 'from frappe import _' pattern"
fi
echo ""

# --------------------------------------------------------------------------
# Check 4: All translation CSV files exist for every app
# --------------------------------------------------------------------------
echo "Check 4: Translation CSV files exist for all apps..."

MISSING_FILES=0
for APP in "${APPS[@]}"; do
    # Determine the inner package path
    if [ "$APP" = "tr_tradehub" ]; then
        TRANS_DIR="$APPS_DIR/$APP/$APP/translations"
    else
        TRANS_DIR="$APPS_DIR/$APP/$APP/translations"
    fi

    for LANG in tr en ar de; do
        CSV_FILE="$TRANS_DIR/${LANG}.csv"
        if [ ! -f "$CSV_FILE" ]; then
            echo "  MISSING: $CSV_FILE"
            MISSING_FILES=$((MISSING_FILES + 1))
        fi
    done
done

if [ "$MISSING_FILES" -gt 0 ]; then
    echo "  FAIL: $MISSING_FILES translation CSV file(s) missing"
    ERRORS=$((ERRORS + 1))
else
    TOTAL=$((${#APPS[@]} * 4))
    echo "  PASS: All $TOTAL translation CSV files present (${#APPS[@]} apps x 4 languages)"
fi
echo ""

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo "========================================"
if [ "$ERRORS" -eq 0 ]; then
    echo " ALL CHECKS PASSED"
    echo "========================================"
    exit 0
else
    echo " $ERRORS CHECK(S) FAILED"
    echo "========================================"
    exit 1
fi
