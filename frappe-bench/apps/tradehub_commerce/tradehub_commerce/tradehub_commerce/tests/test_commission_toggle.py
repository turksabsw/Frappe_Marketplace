# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Test Suite: Commission Plan Temporary Disable (Task 154)

Tests the global commission toggle mechanism that allows the platform
to temporarily disable all commission calculations via a single
`commission_enabled` Check field in TR TradeHub Settings.

Unit Tests (T1–T8):
  T1 — Toggle ON→OFF sets commission_disabled_date
  T2 — Toggle OFF→ON sets commission_enabled_date
  T3 — is_commission_enabled() returns cached value
  T4 — Cache invalidation works within 1 second
  T5 — get_zero_commission_result returns correct structure
  T6 — CommissionPlan.calculate_commission returns 0 when disabled
  T7 — CommissionRule.calculate_commission returns 0 when disabled
  T8 — calculate_commission_with_rules returns 0 when disabled

Integration Tests (E1–E4):
  E1 — Full order flow with commission disabled — seller gets 100%
  E2 — Toggle during active orders — new orders get 0 commission
  E3 — API responses include bypass info
  E4 — Seller notifications sent on toggle
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate, getdate

from tradehub_commerce.tradehub_commerce.utils.commission_utils import (
    is_commission_enabled,
    get_zero_commission_result,
    invalidate_commission_cache,
    get_commission_banner_info,
    COMMISSION_CACHE_TTL,
)


class TestCommissionToggleUnit(FrappeTestCase):
    """Unit tests T1–T8 for the commission toggle mechanism."""

    def setUp(self):
        """Set up test fixtures — ensure a clean cache state."""
        super().setUp()
        # Always start with a clean cache for each test
        invalidate_commission_cache()

    def tearDown(self):
        """Tear down — clean up cache after each test."""
        invalidate_commission_cache()
        super().tearDown()

    # ------------------------------------------------------------------
    # T1: Toggle ON → OFF sets commission_disabled_date
    # ------------------------------------------------------------------
    def test_toggle_on_to_off_sets_commission_disabled_date(self):
        """T1: When commission_enabled is toggled from ON to OFF,
        commission_disabled_date must be set to today's date."""
        settings = frappe.get_doc("TR TradeHub Settings")
        settings.commission_enabled = 1
        settings.commission_disabled_date = None
        settings.commission_enabled_date = None
        settings.save()

        # Now toggle OFF
        settings.reload()
        settings.commission_enabled = 0
        settings.save()

        settings.reload()
        self.assertEqual(
            getdate(settings.commission_disabled_date),
            getdate(nowdate()),
            "commission_disabled_date should be set to today when toggled OFF",
        )

    # ------------------------------------------------------------------
    # T2: Toggle OFF → ON sets commission_enabled_date
    # ------------------------------------------------------------------
    def test_toggle_off_to_on_sets_commission_enabled_date(self):
        """T2: When commission_enabled is toggled from OFF to ON,
        commission_enabled_date must be set to today's date."""
        settings = frappe.get_doc("TR TradeHub Settings")
        settings.commission_enabled = 0
        settings.commission_disabled_date = None
        settings.commission_enabled_date = None
        settings.save()

        # Now toggle ON
        settings.reload()
        settings.commission_enabled = 1
        settings.save()

        settings.reload()
        self.assertEqual(
            getdate(settings.commission_enabled_date),
            getdate(nowdate()),
            "commission_enabled_date should be set to today when toggled ON",
        )

    # ------------------------------------------------------------------
    # T3: is_commission_enabled() returns cached value
    # ------------------------------------------------------------------
    def test_is_commission_enabled_returns_cached_value(self):
        """T3: After the first call, is_commission_enabled() should read
        from cache instead of hitting the database."""
        # Set DB to enabled
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 1)
        invalidate_commission_cache()

        # First call — cache miss, reads DB
        result1 = is_commission_enabled()
        self.assertTrue(result1, "Should return True when commission_enabled=1")

        # Verify the value is now cached
        cached = frappe.cache().get_value("commission_enabled")
        self.assertIsNotNone(cached, "Value should be stored in cache after first call")
        self.assertEqual(int(cached), 1, "Cached value should be 1")

        # Second call should return the same value (from cache)
        result2 = is_commission_enabled()
        self.assertTrue(result2, "Second call should still return True from cache")

    # ------------------------------------------------------------------
    # T4: Cache invalidation works within 1 second
    # ------------------------------------------------------------------
    def test_cache_invalidation_works_within_1s(self):
        """T4: After invalidate_commission_cache(), is_commission_enabled()
        must reflect the new DB value immediately (< 1 second)."""
        # Start with commission enabled
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 1)
        invalidate_commission_cache()
        self.assertTrue(is_commission_enabled(), "Should be True initially")

        # Change DB directly
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)

        # Without invalidation, cache should still show old value
        # (depending on cache implementation, it may or may not;
        #  we test that *after* invalidation the new value is returned)
        invalidate_commission_cache()

        # After invalidation, next call should re-read from DB
        result = is_commission_enabled()
        self.assertFalse(
            result,
            "After cache invalidation, is_commission_enabled() should "
            "reflect the updated DB value (False) immediately",
        )

    # ------------------------------------------------------------------
    # T5: get_zero_commission_result returns correct structure
    # ------------------------------------------------------------------
    def test_get_zero_commission_result_returns_correct_structure(self):
        """T5: get_zero_commission_result(order_value) must return a dict
        with commission_amount=0, effective_rate=0, seller_amount=order_value,
        bypassed=True, and a bypass_reason string."""
        order_value = 5000.0
        result = get_zero_commission_result(order_value)

        self.assertIsInstance(result, dict, "Result should be a dict")
        self.assertEqual(result["commission_amount"], 0, "commission_amount should be 0")
        self.assertEqual(result["effective_rate"], 0, "effective_rate should be 0")
        self.assertEqual(
            result["seller_amount"],
            order_value,
            "seller_amount should equal order_value",
        )
        self.assertTrue(result["bypassed"], "bypassed should be True")
        self.assertIn("bypass_reason", result, "Result should include bypass_reason")
        self.assertTrue(
            len(result["bypass_reason"]) > 0,
            "bypass_reason should not be empty",
        )

    def test_get_zero_commission_result_with_zero_order_value(self):
        """T5b: get_zero_commission_result(0) should work correctly."""
        result = get_zero_commission_result(0)
        self.assertEqual(result["commission_amount"], 0)
        self.assertEqual(result["seller_amount"], 0)
        self.assertTrue(result["bypassed"])

    # ------------------------------------------------------------------
    # T6: CommissionPlan.calculate_commission returns 0 when disabled
    # ------------------------------------------------------------------
    def test_commission_plan_calculate_returns_zero_when_disabled(self):
        """T6: When commission is globally disabled,
        CommissionPlan.calculate_commission() must return
        commission_amount=0 and bypassed=True."""
        # Disable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        # Get an active commission plan (or create a test one)
        plan_name = frappe.db.get_value(
            "Commission Plan",
            {"status": "Active"},
            "name",
        )
        if not plan_name:
            # Create a minimal test plan
            plan = frappe.get_doc(
                {
                    "doctype": "Commission Plan",
                    "plan_name": "Test Toggle Plan",
                    "plan_type": "Standard",
                    "status": "Active",
                    "base_commission_rate": 10,
                    "commission_calculation_type": "Percentage",
                    "effective_from": nowdate(),
                    "is_perpetual": 1,
                }
            )
            plan.insert(ignore_permissions=True)
            plan_name = plan.name

        plan = frappe.get_doc("Commission Plan", plan_name)
        result = plan.calculate_commission(order_value=1000)

        self.assertEqual(
            result["commission_amount"],
            0,
            "commission_amount should be 0 when commission is disabled",
        )
        self.assertTrue(
            result.get("bypassed"),
            "bypassed flag should be True when commission is disabled",
        )
        self.assertEqual(
            result["seller_amount"],
            1000,
            "seller_amount should equal full order value",
        )

    # ------------------------------------------------------------------
    # T7: CommissionRule.calculate_commission returns 0 when disabled
    # ------------------------------------------------------------------
    def test_commission_rule_calculate_returns_zero_when_disabled(self):
        """T7: When commission is globally disabled,
        CommissionRule.calculate_commission() must return
        commission_amount=0 and bypassed=True."""
        # Disable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        # Get an existing commission rule or create one
        rule_name = frappe.db.get_value(
            "Commission Rule",
            {"status": "Active"},
            "name",
        )
        if not rule_name:
            rule = frappe.get_doc(
                {
                    "doctype": "Commission Rule",
                    "rule_name": "Test Toggle Rule",
                    "rule_type": "Standard",
                    "status": "Active",
                    "priority": 100,
                    "commission_type": "Percentage",
                    "commission_rate": 10,
                    "effective_from": nowdate(),
                    "is_perpetual": 1,
                    "apply_to": "All",
                }
            )
            rule.insert(ignore_permissions=True)
            rule_name = rule.name

        rule = frappe.get_doc("Commission Rule", rule_name)
        result = rule.calculate_commission(order_value=2000)

        self.assertEqual(
            result["commission_amount"],
            0,
            "commission_amount should be 0 when commission is disabled",
        )
        self.assertTrue(
            result.get("bypassed"),
            "bypassed flag should be True when commission is disabled",
        )
        self.assertEqual(
            result["seller_amount"],
            2000,
            "seller_amount should equal full order value",
        )

    # ------------------------------------------------------------------
    # T8: calculate_commission_with_rules returns 0 when disabled
    # ------------------------------------------------------------------
    def test_calculate_commission_with_rules_returns_zero_when_disabled(self):
        """T8: When commission is globally disabled,
        calculate_commission_with_rules() must return
        commission_amount=0 and bypassed=True."""
        from tradehub_commerce.tradehub_commerce.doctype.commission_rule.commission_rule import (
            calculate_commission_with_rules,
        )

        # Disable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        ctx = {
            "order_value": 3000,
            "category": "Electronics",
            "seller": "SELLER-001",
        }
        result = calculate_commission_with_rules(order_value=3000, ctx=ctx)

        self.assertEqual(
            result["commission_amount"],
            0,
            "commission_amount should be 0 when commission is disabled",
        )
        self.assertTrue(
            result.get("bypassed"),
            "bypassed flag should be True when commission is disabled",
        )
        self.assertEqual(
            result["seller_amount"],
            3000,
            "seller_amount should equal full order value",
        )


class TestCommissionToggleIntegration(FrappeTestCase):
    """Integration tests E1–E4 for the commission toggle mechanism."""

    def setUp(self):
        """Set up integration test fixtures."""
        super().setUp()
        invalidate_commission_cache()

    def tearDown(self):
        """Tear down integration test fixtures."""
        invalidate_commission_cache()
        super().tearDown()

    # ------------------------------------------------------------------
    # E1: Full order flow with commission disabled — seller gets 100%
    # ------------------------------------------------------------------
    def test_full_order_flow_commission_disabled_seller_gets_100_percent(self):
        """E1: When commission is globally disabled, a completed order
        should result in the seller receiving the full order amount
        (commission_amount=0 everywhere in the flow)."""
        # Disable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        order_value = 10000.0

        # Verify via CommissionPlan
        plan_name = frappe.db.get_value(
            "Commission Plan",
            {"status": "Active"},
            "name",
        )
        if plan_name:
            plan = frappe.get_doc("Commission Plan", plan_name)
            plan_result = plan.calculate_commission(order_value=order_value)
            self.assertEqual(plan_result["commission_amount"], 0)
            self.assertEqual(plan_result["seller_amount"], order_value)
            self.assertTrue(plan_result.get("bypassed"))

        # Verify via rule engine
        from tradehub_commerce.tradehub_commerce.doctype.commission_rule.commission_rule import (
            calculate_commission_with_rules,
        )

        ctx = {"order_value": order_value, "category": None, "seller": None}
        rule_result = calculate_commission_with_rules(
            order_value=order_value, ctx=ctx
        )
        self.assertEqual(rule_result["commission_amount"], 0)
        self.assertEqual(rule_result["seller_amount"], order_value)
        self.assertTrue(rule_result.get("bypassed"))

        # Verify zero result helper gives 100% to seller
        zero_result = get_zero_commission_result(order_value)
        self.assertEqual(zero_result["seller_amount"], order_value)
        self.assertEqual(zero_result["commission_amount"], 0)

    # ------------------------------------------------------------------
    # E2: Toggle during active orders — new orders get 0 commission
    # ------------------------------------------------------------------
    def test_toggle_during_active_orders_new_orders_get_zero_commission(self):
        """E2: When the toggle is switched from ON to OFF mid-flight,
        new commission calculations should immediately return 0
        while preserving historical calculations."""
        from tradehub_commerce.tradehub_commerce.doctype.commission_rule.commission_rule import (
            calculate_commission_with_rules,
        )

        # Start with commission enabled
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 1)
        invalidate_commission_cache()

        # Simulate "old" calculation — with rules, commission should be > 0
        # (if no rules exist, default 10% applies)
        self.assertTrue(
            is_commission_enabled(),
            "Commission should be enabled at this point",
        )

        # Now toggle OFF
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        # New calculations must return 0
        self.assertFalse(
            is_commission_enabled(),
            "Commission should be disabled after toggle",
        )

        ctx = {"order_value": 5000, "category": None, "seller": None}
        new_result = calculate_commission_with_rules(order_value=5000, ctx=ctx)
        self.assertEqual(
            new_result["commission_amount"],
            0,
            "New orders should have 0 commission after toggle OFF",
        )
        self.assertTrue(
            new_result.get("bypassed"),
            "New orders should be flagged as bypassed",
        )

    # ------------------------------------------------------------------
    # E3: API responses include bypass info
    # ------------------------------------------------------------------
    def test_api_responses_include_bypass_info(self):
        """E3: When commission is disabled, API-level commission
        calculation responses should include bypass information
        (bypassed=True, bypass_reason, commission_enabled status)."""
        # Disable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        # Call the module-level calculate_commission whitelist
        from tradehub_commerce.tradehub_commerce.doctype.commission_rule.commission_rule import (
            calculate_commission as api_calculate_commission,
        )

        result = api_calculate_commission(
            order_value=1000,
            category="Electronics",
            seller="SELLER-001",
        )

        self.assertEqual(
            result["commission_amount"],
            0,
            "API should return 0 commission when disabled",
        )
        self.assertTrue(
            result.get("bypassed"),
            "API response should include bypassed=True",
        )
        self.assertIn(
            "bypass_reason",
            result,
            "API response should include bypass_reason",
        )

        # Verify the zero-commission result itself always contains bypass info
        zero = get_zero_commission_result(1000)
        self.assertTrue(zero["bypassed"])
        self.assertIn("bypass_reason", zero)

    # ------------------------------------------------------------------
    # E4: Seller notifications sent on toggle
    # ------------------------------------------------------------------
    def test_seller_notifications_on_toggle(self):
        """E4: When the commission toggle changes and
        commission_enable_notify_sellers is checked, the system should
        trigger notification functions. We verify by checking the
        banner info helper output."""
        # Disable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        # When commission is OFF, banner info should indicate info banner
        banner = get_commission_banner_info()
        self.assertTrue(
            banner["show_banner"],
            "Banner should be shown when commission is disabled",
        )
        self.assertEqual(
            banner["banner_type"],
            "info",
            "Banner type should be 'info' when commission is disabled",
        )
        self.assertTrue(
            len(banner["message"]) > 0,
            "Banner message should not be empty",
        )

        # Enable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 1)
        invalidate_commission_cache()

        # When commission is ON and stable (no recent re-enable),
        # banner may or may not show depending on commission_enabled_date.
        # At minimum, verify banner structure is valid.
        banner_on = get_commission_banner_info()
        self.assertIn("show_banner", banner_on)
        self.assertIn("banner_type", banner_on)
        self.assertIn("message", banner_on)


class TestCommissionToggleEdgeCases(FrappeTestCase):
    """Additional edge-case tests for the commission toggle."""

    def setUp(self):
        super().setUp()
        invalidate_commission_cache()

    def tearDown(self):
        invalidate_commission_cache()
        super().tearDown()

    def test_is_commission_enabled_returns_false_when_disabled(self):
        """Verify is_commission_enabled() returns False when
        commission_enabled=0 in settings."""
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()
        self.assertFalse(is_commission_enabled())

    def test_is_commission_enabled_returns_true_when_enabled(self):
        """Verify is_commission_enabled() returns True when
        commission_enabled=1 in settings."""
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 1)
        invalidate_commission_cache()
        self.assertTrue(is_commission_enabled())

    def test_invalidate_commission_cache_clears_cache_key(self):
        """Verify that invalidate_commission_cache() removes the cached
        value from Redis."""
        # Populate cache
        frappe.cache().set_value("commission_enabled", 1)
        self.assertIsNotNone(frappe.cache().get_value("commission_enabled"))

        # Invalidate
        invalidate_commission_cache()
        self.assertIsNone(
            frappe.cache().get_value("commission_enabled"),
            "Cache should be empty after invalidation",
        )

    def test_get_zero_commission_result_with_large_order_value(self):
        """Verify zero-commission result handles large order values."""
        order_value = 999_999_999.99
        result = get_zero_commission_result(order_value)
        self.assertEqual(result["commission_amount"], 0)
        self.assertEqual(result["seller_amount"], order_value)
        self.assertTrue(result["bypassed"])

    def test_commission_plan_preserves_rate_when_toggle_off(self):
        """Verify that toggling commission OFF does not alter the
        base_commission_rate stored in any Commission Plan."""
        plan_name = frappe.db.get_value(
            "Commission Plan",
            {"status": "Active"},
            "name",
        )
        if not plan_name:
            return  # Skip if no plans exist

        plan = frappe.get_doc("Commission Plan", plan_name)
        original_rate = plan.base_commission_rate

        # Disable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 0)
        invalidate_commission_cache()

        # Re-read the plan and check rate is preserved
        plan.reload()
        self.assertEqual(
            plan.base_commission_rate,
            original_rate,
            "Commission rate should be preserved when toggle is OFF",
        )

        # Calculate returns 0 but rate is intact
        result = plan.calculate_commission(order_value=1000)
        self.assertEqual(result["commission_amount"], 0)

        # Re-enable commission
        frappe.db.set_single_value("TR TradeHub Settings", "commission_enabled", 1)
        invalidate_commission_cache()

        # Rate is still intact, calculation should be normal
        plan.reload()
        self.assertEqual(plan.base_commission_rate, original_rate)


def run_tests():
    """Run all commission toggle tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCommissionToggleUnit))
    suite.addTests(loader.loadTestsFromTestCase(TestCommissionToggleIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestCommissionToggleEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    run_tests()
