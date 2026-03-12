# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box Entry DocType for Trade Hub B2B Marketplace.

This module implements seller offer entries that compete for the Buy Box position
on product pages. The Buy Box represents the primary sales position where buyers
can quickly add items to cart.

Key features:
- Multi-tenant data isolation via Seller Profile's tenant
- 6-criteria weighted scoring delegated to buy_box/scoring.py
- 11 disqualification rules delegated to buy_box/disqualification.py
- Winner determination based on composite score with tiebreaker cascade
- Redis-based cooldown for recalculation throttling
- Buy Box Log creation on each recalculation
- Improvement suggestions generated from score breakdown

Buy Box Algorithm (6 Criteria — weights from Buy Box Settings):
- Price Score: Lower prices score higher
- Delivery Score: Faster delivery scores higher
- Rating Score: Higher seller ratings score higher (with confidence)
- Stock Score: Higher stock availability scores higher (log scale)
- Service Score: Better service metrics score higher
- Tier Bonus: Seller tier bonus from Settings tier_bonuses table
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, now_datetime

from tradehub_seller.tradehub_seller.buy_box.scoring import (
    calculate_buy_box_score,
    apply_tiebreaker,
    get_buy_box_settings,
)
from tradehub_seller.tradehub_seller.buy_box.disqualification import (
    check_disqualification,
)


class BuyBoxEntry(Document):
    """
    Buy Box Entry DocType for marketplace seller offers.

    Each Buy Box Entry represents a seller's offer for a specific product.
    Multiple sellers can have entries for the same product, and the Buy Box
    algorithm determines which seller's entry wins the primary position.
    """

    def before_insert(self):
        """Set defaults before inserting a new entry."""
        self.validate_unique_entry()
        self.update_stock_timestamp()

    def validate(self):
        """Validate Buy Box entry data before saving."""
        self.validate_sku_product()
        self.validate_seller()
        self.validate_pricing()
        self.validate_delivery()
        self.validate_stock()
        self.validate_tenant_isolation()
        self.sync_is_active_status()

    def on_update(self):
        """Actions after Buy Box entry is updated."""
        if not self._check_cooldown():
            return
        self._trigger_recalculation("Hook")

    def on_trash(self):
        """Actions before Buy Box entry is deleted."""
        self._trigger_recalculation("Hook")

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_unique_entry(self):
        """
        Validate that only one active entry exists per product-seller combination.

        A seller cannot have multiple active Buy Box entries for the same product.
        """
        if self.status in ("Active", "Inactive"):
            existing = frappe.db.get_value(
                "Buy Box Entry",
                {
                    "sku_product": self.sku_product,
                    "seller": self.seller,
                    "status": ("in", ["Active", "Inactive"]),
                    "name": ("!=", self.name or "")
                },
                "name"
            )

            if existing:
                frappe.throw(
                    _("An entry for this product-seller combination already exists: {0}").format(
                        existing
                    )
                )

    def validate_sku_product(self):
        """Validate SKU Product link exists and is valid."""
        if not self.sku_product:
            frappe.throw(_("SKU Product is required"))

        product_status = frappe.db.get_value(
            "SKU Product", self.sku_product, "status"
        )

        if product_status == "Archive":
            frappe.throw(
                _("Cannot create Buy Box entry for archived product {0}").format(
                    self.sku_product
                )
            )

        if product_status != "Active":
            frappe.msgprint(
                _("Warning: Product {0} is not in Active status").format(
                    self.sku_product
                ),
                indicator='orange',
                alert=True
            )

    def validate_seller(self):
        """Validate Seller Profile link exists and is valid."""
        if not self.seller:
            frappe.throw(_("Seller is required"))

        seller_data = frappe.db.get_value(
            "Seller Profile",
            self.seller,
            ["status", "verification_status"],
            as_dict=True
        )

        if not seller_data:
            frappe.throw(_("Seller Profile not found"))

        if seller_data.status != "Active":
            frappe.throw(
                _("Cannot create Buy Box entry for inactive seller")
            )

        if seller_data.verification_status != "Verified":
            frappe.msgprint(
                _("Warning: Seller {0} is not verified").format(self.seller),
                indicator='orange',
                alert=True
            )

    def validate_pricing(self):
        """Validate pricing fields."""
        if flt(self.offer_price) <= 0:
            frappe.throw(_("Offer Price must be greater than zero"))

        if not self.currency:
            self.currency = "TRY"

        if flt(self.min_order_quantity) <= 0:
            self.min_order_quantity = 1

        if flt(self.max_order_quantity) < 0:
            self.max_order_quantity = 0

        if self.max_order_quantity and flt(self.min_order_quantity) > flt(self.max_order_quantity):
            frappe.throw(
                _("Min Order Quantity cannot be greater than Max Order Quantity")
            )

    def validate_delivery(self):
        """Validate delivery fields."""
        if cint(self.delivery_days) <= 0:
            frappe.throw(_("Delivery Days must be greater than zero"))

        if cint(self.delivery_days) > 365:
            frappe.msgprint(
                _("Delivery time of {0} days seems unusually long").format(
                    self.delivery_days
                ),
                indicator='orange',
                alert=True
            )

    def validate_stock(self):
        """Validate stock fields."""
        if flt(self.stock_available) < 0:
            frappe.throw(_("Stock Available cannot be negative"))

        if flt(self.stock_available) == 0 and self.status == "Active":
            frappe.msgprint(
                _("Warning: Stock is zero for an active Buy Box entry"),
                indicator='orange',
                alert=True
            )

    def validate_tenant_isolation(self):
        """
        Validate that entry belongs to user's tenant.

        Inherits tenant from Seller Profile to ensure multi-tenant data isolation.
        """
        if not self.tenant:
            return

        # System Manager can access all tenants
        if "System Manager" in frappe.get_roles():
            return

        # Get current user's tenant
        from tradehub_core.tradehub_core.utils.tenant import get_current_tenant
        current_tenant = get_current_tenant()

        if current_tenant and self.tenant != current_tenant:
            frappe.throw(
                _("Access denied: You can only access Buy Box entries in your tenant")
            )

    def sync_is_active_status(self):
        """Sync is_active checkbox with status field."""
        if self.status == "Active" and not self.is_active:
            self.is_active = 1
        elif self.status != "Active" and self.is_active:
            self.is_active = 0

    # =========================================================================
    # STOCK MANAGEMENT
    # =========================================================================

    def update_stock_timestamp(self):
        """Update the stock timestamp when stock changes."""
        self.last_stock_update = now_datetime()

    def update_stock(self, quantity):
        """
        Update stock availability.

        Args:
            quantity: New stock quantity
        """
        self.stock_available = flt(quantity)
        self.last_stock_update = now_datetime()
        self.save()

    # =========================================================================
    # COOLDOWN & RECALCULATION TRIGGERS
    # =========================================================================

    def _check_cooldown(self):
        """
        Check Redis-based cooldown for Buy Box recalculation.

        Uses Redis key trade_hub:buybox_cooldown:{sku_product} with TTL
        from Buy Box Settings.cooldown_seconds. Returns True if recalculation
        is allowed, False if still in cooldown period.

        Returns:
            bool: True if recalculation can proceed
        """
        if not self.sku_product:
            return False

        cache_key = f"trade_hub:buybox_cooldown:{self.sku_product}"
        cooldown_active = frappe.cache().get_value(cache_key)

        if cooldown_active:
            return False

        # Set cooldown
        try:
            settings = get_buy_box_settings()
            cooldown_seconds = cint(settings.cooldown_seconds) or 300
        except Exception:
            cooldown_seconds = 300

        frappe.cache().set_value(cache_key, 1, expires_in_sec=cooldown_seconds)
        return True

    def _trigger_recalculation(self, triggered_by="Hook"):
        """
        Trigger Buy Box recalculation for this product via background queue.

        Args:
            triggered_by: Source that triggered recalculation (Hook/Manual/Scheduled/API)
        """
        frappe.enqueue(
            "tradehub_seller.tradehub_seller.doctype.buy_box_entry.buy_box_entry.recalculate_buy_box_for_product",
            sku_product=self.sku_product,
            triggered_by=triggered_by,
            queue="short",
            deduplicate=True
        )


# =============================================================================
# IMPROVEMENT SUGGESTIONS
# =============================================================================


def _generate_improvement_suggestions(score_breakdown, is_disqualified, disqualification_reason):
    """
    Generate actionable improvement suggestions from score breakdown.

    Analyzes each scoring component and identifies the weakest areas
    where sellers can improve their Buy Box competitiveness.

    Args:
        score_breakdown: Dict with score breakdown per criterion
        is_disqualified: Whether entry is disqualified
        disqualification_reason: Reason for disqualification if applicable

    Returns:
        str: Newline-separated list of improvement suggestions
    """
    suggestions = []

    if is_disqualified and disqualification_reason:
        suggestions.append(
            _("Disqualified: {0}. Resolve this issue first.").format(disqualification_reason)
        )
        return "\n".join(suggestions)

    if not score_breakdown or not isinstance(score_breakdown, dict):
        return ""

    # Analyze each component and suggest improvements for weak scores
    threshold = 0.5  # Scores below 50% normalized are considered weak

    criteria_advice = {
        "price": _("Lower your offer price to be more competitive with other sellers."),
        "delivery": _("Reduce delivery time to improve your delivery score."),
        "rating": _("Improve your seller rating by providing better customer service and requesting reviews."),
        "stock": _("Increase stock availability to improve your stock score."),
        "service": _("Improve response rate, reduce refund rate, and maintain on-time delivery to boost service score."),
        "tier": _("Upgrade your seller tier to earn tier bonus points."),
    }

    weak_areas = []
    for criterion, advice in criteria_advice.items():
        data = score_breakdown.get(criterion, {})
        normalized = flt(data.get("normalized", 0))
        weight = flt(data.get("weight", 0))

        if weight > 0 and normalized < threshold:
            weak_areas.append((criterion, normalized, weight, advice))

    # Sort by potential impact (weight × improvement room)
    weak_areas.sort(key=lambda x: x[2] * (1 - x[1]), reverse=True)

    for criterion, normalized, weight, advice in weak_areas:
        score_pct = round(normalized * 100, 1)
        suggestions.append(
            _("{0} score is {1}% (weight: {2}). {3}").format(
                criterion.title(), score_pct, round(weight * 100, 1), advice
            )
        )

    if not suggestions:
        suggestions.append(_("Your Buy Box scores are competitive. Maintain current performance levels."))

    return "\n".join(suggestions)


# =============================================================================
# BUY BOX LOG CREATION
# =============================================================================


def _create_buy_box_log(entry_name, sku_product, seller, tenant,
                        previous_score, new_score, previous_rank, new_rank,
                        is_winner_change, score_breakdown_json,
                        disqualification_reason, triggered_by):
    """
    Create a Buy Box Log record for audit trail.

    Args:
        entry_name: Buy Box Entry name
        sku_product: SKU Product name
        seller: Seller Profile name
        tenant: Tenant name
        previous_score: Score before recalculation
        new_score: Score after recalculation
        previous_rank: Rank before recalculation
        new_rank: Rank after recalculation
        is_winner_change: Whether the winner changed
        score_breakdown_json: JSON string of score breakdown
        disqualification_reason: Disqualification reason if applicable
        triggered_by: What triggered the recalculation
    """
    try:
        log = frappe.new_doc("Buy Box Log")
        log.buy_box_entry = entry_name
        log.sku_product = sku_product
        log.seller = seller
        log.tenant = tenant
        log.recalculated_at = now_datetime()
        log.previous_score = flt(previous_score)
        log.new_score = flt(new_score)
        log.previous_rank = cint(previous_rank)
        log.new_rank = cint(new_rank)
        log.is_winner_change = 1 if is_winner_change else 0
        log.score_breakdown_json = score_breakdown_json
        log.disqualification_reason = disqualification_reason or ""
        log.triggered_by = triggered_by or "Hook"
        log.flags.ignore_permissions = True
        log.insert()
    except Exception:
        frappe.log_error(
            title=_("Buy Box Log Creation Error"),
            message=frappe.get_traceback()
        )


# =============================================================================
# WHITELISTED API FUNCTIONS
# =============================================================================


@frappe.whitelist()
def recalculate_buy_box_for_product(sku_product, triggered_by="Hook"):
    """
    Recalculate Buy Box scores for all entries of a product.

    Uses the 6-criteria scoring algorithm from buy_box/scoring.py and
    the 11 disqualification rules from buy_box/disqualification.py.

    This function:
    1. Gets all active entries for the product
    2. Checks disqualification rules for each entry
    3. Calculates 6-criteria scores for qualified entries
    4. Applies tiebreaker cascade for tied scores
    5. Determines the winner
    6. Updates all entries with scores, ranks, and improvement suggestions
    7. Creates Buy Box Log entries for audit trail

    Args:
        sku_product: The SKU Product name
        triggered_by: What triggered recalculation (Hook/Manual/Scheduled/API)

    Returns:
        dict: Recalculation result with winner info
    """
    # Get all entries (active and inactive) for comprehensive processing
    entries = frappe.get_all(
        "Buy Box Entry",
        filters={
            "sku_product": sku_product,
            "status": ("in", ["Active", "Inactive"]),
        },
        fields=[
            "name", "offer_price", "delivery_days", "stock_available",
            "seller_average_rating", "seller_total_reviews", "is_winner",
            "seller", "seller_tier", "seller_verification_status",
            "seller_on_time_delivery_rate", "seller_response_rate",
            "seller_refund_rate", "status", "tenant",
            "buy_box_score", "rank", "creation",
        ]
    )

    if not entries:
        return {"message": _("No Buy Box entries for this product")}

    total_competitors = len([e for e in entries if e.status == "Active"])
    now = now_datetime()
    scored_entries = []

    for entry in entries:
        previous_score = flt(entry.buy_box_score)
        previous_rank = cint(entry.rank)

        # Step 1: Check disqualification
        is_disqualified, disqualification_reason = check_disqualification(entry)

        if is_disqualified:
            scored_entries.append({
                "name": entry.name,
                "seller": entry.seller,
                "tenant": entry.tenant,
                "buy_box_score": 0,
                "price_score": 0,
                "delivery_score": 0,
                "rating_score": 0,
                "stock_score": 0,
                "service_score": 0,
                "seller_tier_bonus": 0,
                "is_disqualified": 1,
                "disqualification_reason": disqualification_reason,
                "score_breakdown_json": "{}",
                "improvement_suggestions": _generate_improvement_suggestions(
                    {}, True, disqualification_reason
                ),
                "was_winner": entry.is_winner,
                "previous_score": previous_score,
                "previous_rank": previous_rank,
                "creation": entry.creation,
                "seller_on_time_delivery_rate": flt(entry.seller_on_time_delivery_rate),
                "seller_refund_rate": flt(entry.seller_refund_rate),
            })
            continue

        # Step 2: Calculate 6-criteria score
        score_result = calculate_buy_box_score(entry)

        # Parse breakdown for improvement suggestions
        breakdown = {}
        try:
            breakdown = json.loads(score_result.get("score_breakdown_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass

        scored_entries.append({
            "name": entry.name,
            "seller": entry.seller,
            "tenant": entry.tenant,
            "buy_box_score": flt(score_result["buy_box_score"]),
            "price_score": flt(score_result["price_score"]),
            "delivery_score": flt(score_result["delivery_score"]),
            "rating_score": flt(score_result["rating_score"]),
            "stock_score": flt(score_result["stock_score"]),
            "service_score": flt(score_result["service_score"]),
            "seller_tier_bonus": flt(score_result["seller_tier_bonus"]),
            "is_disqualified": 0,
            "disqualification_reason": None,
            "score_breakdown_json": score_result.get("score_breakdown_json", "{}"),
            "improvement_suggestions": _generate_improvement_suggestions(
                breakdown, False, None
            ),
            "was_winner": entry.is_winner,
            "previous_score": previous_score,
            "previous_rank": previous_rank,
            "creation": entry.creation,
            "seller_on_time_delivery_rate": flt(entry.seller_on_time_delivery_rate),
            "seller_refund_rate": flt(entry.seller_refund_rate),
        })

    # Step 3: Sort qualified entries with tiebreaker cascade
    qualified = [e for e in scored_entries if not e["is_disqualified"]]
    disqualified = [e for e in scored_entries if e["is_disqualified"]]

    sorted_qualified = apply_tiebreaker(qualified)

    # Step 4: Determine winner and assign ranks
    winner_name = sorted_qualified[0]["name"] if sorted_qualified else None
    previous_winner = None

    for e in scored_entries:
        if e["was_winner"]:
            previous_winner = e["name"]
            break

    is_winner_change = winner_name != previous_winner

    # Assign ranks to qualified entries
    for rank_idx, entry_data in enumerate(sorted_qualified, start=1):
        entry_data["new_rank"] = rank_idx

    # Disqualified entries get rank 0
    for entry_data in disqualified:
        entry_data["new_rank"] = 0

    # Step 5: Update all entries in database
    all_sorted = sorted_qualified + disqualified

    for entry_data in all_sorted:
        is_winner = 1 if entry_data["name"] == winner_name else 0

        update_values = {
            "price_score": round(entry_data["price_score"], 2),
            "delivery_score": round(entry_data["delivery_score"], 2),
            "rating_score": round(entry_data["rating_score"], 2),
            "stock_score": round(entry_data["stock_score"], 2),
            "service_score": round(entry_data["service_score"], 2),
            "seller_tier_bonus": round(entry_data["seller_tier_bonus"], 2),
            "buy_box_score": round(entry_data["buy_box_score"], 2),
            "is_winner": is_winner,
            "is_disqualified": entry_data["is_disqualified"],
            "disqualification_reason": entry_data.get("disqualification_reason") or "",
            "rank": entry_data["new_rank"],
            "total_competitors": total_competitors,
            "score_breakdown_json": entry_data.get("score_breakdown_json", "{}"),
            "improvement_suggestions": entry_data.get("improvement_suggestions", ""),
            "last_score_update": now,
        }

        # Set winner_since if this is a new winner
        if is_winner and not entry_data["was_winner"]:
            update_values["winner_since"] = now
            update_values["last_winner_change"] = now

        # Clear winner_since if no longer winner
        if not is_winner and entry_data["was_winner"]:
            update_values["winner_since"] = None
            update_values["last_winner_change"] = now

        frappe.db.set_value("Buy Box Entry", entry_data["name"], update_values)

        # Step 6: Create Buy Box Log
        _create_buy_box_log(
            entry_name=entry_data["name"],
            sku_product=sku_product,
            seller=entry_data.get("seller"),
            tenant=entry_data.get("tenant"),
            previous_score=entry_data["previous_score"],
            new_score=entry_data["buy_box_score"],
            previous_rank=entry_data["previous_rank"],
            new_rank=entry_data["new_rank"],
            is_winner_change=is_winner_change,
            score_breakdown_json=entry_data.get("score_breakdown_json", "{}"),
            disqualification_reason=entry_data.get("disqualification_reason"),
            triggered_by=triggered_by,
        )

    frappe.db.commit()

    return {
        "success": True,
        "winner": winner_name,
        "entries_processed": len(all_sorted),
        "winner_changed": is_winner_change,
        "message": _("Buy Box recalculated successfully")
    }


@frappe.whitelist()
def get_buy_box_winner(sku_product):
    """
    Get the current Buy Box winner for a product.

    Args:
        sku_product: The SKU Product name

    Returns:
        dict: Winner entry details or None
    """
    winner = frappe.get_all(
        "Buy Box Entry",
        filters={
            "sku_product": sku_product,
            "status": "Active",
            "is_winner": 1
        },
        fields=[
            "name", "seller", "seller_name", "offer_price", "currency",
            "delivery_days", "stock_available", "buy_box_score",
            "seller_average_rating", "winner_since"
        ],
        limit=1
    )

    return winner[0] if winner else None


@frappe.whitelist()
def get_product_buy_box_entries(sku_product, include_inactive=False):
    """
    Get all Buy Box entries for a product.

    Args:
        sku_product: The SKU Product name
        include_inactive: Whether to include inactive entries

    Returns:
        list: List of Buy Box entries sorted by score
    """
    filters = {"sku_product": sku_product}

    if not include_inactive:
        filters["status"] = "Active"

    entries = frappe.get_all(
        "Buy Box Entry",
        filters=filters,
        fields=[
            "name", "seller", "seller_name", "offer_price", "currency",
            "delivery_days", "stock_available", "buy_box_score",
            "is_winner", "status", "seller_average_rating",
            "price_score", "delivery_score", "rating_score", "stock_score",
            "service_score", "seller_tier_bonus", "rank", "is_disqualified"
        ],
        order_by="buy_box_score desc"
    )

    return entries


@frappe.whitelist()
def get_seller_buy_box_entries(seller, sku_product=None):
    """
    Get all Buy Box entries for a seller.

    Args:
        seller: The Seller Profile name
        sku_product: Optional product filter

    Returns:
        list: List of Buy Box entries for the seller
    """
    filters = {"seller": seller}

    if sku_product:
        filters["sku_product"] = sku_product

    entries = frappe.get_all(
        "Buy Box Entry",
        filters=filters,
        fields=[
            "name", "sku_product", "product_name", "product_sku_code",
            "offer_price", "currency", "delivery_days", "stock_available",
            "buy_box_score", "is_winner", "status", "rank",
            "improvement_suggestions"
        ],
        order_by="is_winner desc, buy_box_score desc"
    )

    return entries


@frappe.whitelist()
def create_buy_box_entry(sku_product, seller, offer_price, delivery_days,
                          stock_available, currency="TRY", **kwargs):
    """
    Create a new Buy Box entry.

    Args:
        sku_product: The SKU Product name
        seller: The Seller Profile name
        offer_price: The offer price
        delivery_days: Estimated delivery days
        stock_available: Available stock quantity
        currency: Currency code (default TRY)
        **kwargs: Additional optional fields

    Returns:
        dict: Created entry info
    """
    doc = frappe.new_doc("Buy Box Entry")
    doc.sku_product = sku_product
    doc.seller = seller
    doc.offer_price = flt(offer_price)
    doc.delivery_days = cint(delivery_days)
    doc.stock_available = flt(stock_available)
    doc.currency = currency

    # Set optional fields
    for field in ["min_order_quantity", "max_order_quantity", "delivery_location",
                  "origin_country", "shipping_method", "price_includes_shipping",
                  "is_stock_guaranteed"]:
        if field in kwargs:
            setattr(doc, field, kwargs[field])

    doc.insert()

    return {
        "name": doc.name,
        "message": _("Buy Box entry created successfully")
    }


@frappe.whitelist()
def update_buy_box_entry(name, **kwargs):
    """
    Update a Buy Box entry.

    Args:
        name: The Buy Box Entry name
        **kwargs: Fields to update

    Returns:
        dict: Update result
    """
    doc = frappe.get_doc("Buy Box Entry", name)

    # Update allowed fields
    allowed_fields = [
        "offer_price", "delivery_days", "stock_available", "currency",
        "min_order_quantity", "max_order_quantity", "delivery_location",
        "origin_country", "shipping_method", "price_includes_shipping",
        "is_stock_guaranteed", "status", "internal_notes"
    ]

    for field in allowed_fields:
        if field in kwargs:
            setattr(doc, field, kwargs[field])

    doc.save()

    return {
        "success": True,
        "message": _("Buy Box entry updated successfully")
    }


@frappe.whitelist()
def activate_entry(name):
    """
    Activate a Buy Box entry.

    Args:
        name: The Buy Box Entry name

    Returns:
        dict: Activation result
    """
    doc = frappe.get_doc("Buy Box Entry", name)

    if doc.status == "Active":
        return {"success": True, "message": _("Entry is already active")}

    doc.status = "Active"
    doc.is_active = 1
    doc.save()

    return {
        "success": True,
        "message": _("Buy Box entry activated successfully")
    }


@frappe.whitelist()
def deactivate_entry(name):
    """
    Deactivate a Buy Box entry.

    Args:
        name: The Buy Box Entry name

    Returns:
        dict: Deactivation result
    """
    doc = frappe.get_doc("Buy Box Entry", name)

    if doc.status == "Inactive":
        return {"success": True, "message": _("Entry is already inactive")}

    doc.status = "Inactive"
    doc.is_active = 0

    # Clear winner status
    if doc.is_winner:
        doc.is_winner = 0
        doc.winner_since = None

    doc.save()

    return {
        "success": True,
        "message": _("Buy Box entry deactivated successfully")
    }


@frappe.whitelist()
def get_buy_box_statistics(sku_product=None, seller=None):
    """
    Get Buy Box statistics.

    Args:
        sku_product: Optional product filter
        seller: Optional seller filter

    Returns:
        dict: Statistics including total entries, winners, average scores
    """
    filters = {"status": "Active"}

    if sku_product:
        filters["sku_product"] = sku_product
    if seller:
        filters["seller"] = seller

    entries = frappe.get_all(
        "Buy Box Entry",
        filters=filters,
        fields=["name", "is_winner", "buy_box_score", "offer_price"]
    )

    if not entries:
        return {
            "total_entries": 0,
            "total_winners": 0,
            "average_score": 0,
            "average_price": 0
        }

    total_entries = len(entries)
    total_winners = sum(1 for e in entries if e.is_winner)
    average_score = sum(flt(e.buy_box_score) for e in entries) / total_entries
    average_price = sum(flt(e.offer_price) for e in entries) / total_entries

    return {
        "total_entries": total_entries,
        "total_winners": total_winners,
        "average_score": round(average_score, 2),
        "average_price": round(average_price, 2)
    }


@frappe.whitelist()
def recalculate_all_buy_boxes():
    """
    Recalculate Buy Box for all products with active entries.

    This should be called by a scheduled job.

    Returns:
        dict: Summary of recalculations
    """
    products = frappe.get_all(
        "Buy Box Entry",
        filters={"status": "Active"},
        fields=["sku_product"],
        group_by="sku_product"
    )

    recalculated = 0
    for product in products:
        try:
            recalculate_buy_box_for_product(product.sku_product, triggered_by="Scheduled")
            recalculated += 1
        except Exception as e:
            frappe.log_error(
                message=str(e),
                title=_("Buy Box Recalculation Error: {0}").format(product.sku_product)
            )

    return {
        "success": True,
        "products_recalculated": recalculated,
        "message": _("Buy Box recalculation completed")
    }
