# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box 6-Criteria Scoring Algorithm for Trade Hub B2B Marketplace.

This module implements the enhanced Buy Box scoring algorithm with 6 weighted
criteria and a tiebreaker cascade. Weights are ALWAYS read from Buy Box Settings
(Single DocType) — never hardcoded.

Scoring Formula:
    total_score = (price_weight × normalize_price(price)) +
                  (delivery_weight × normalize_delivery(delivery_days)) +
                  (rating_weight × normalize_rating(avg_rating, review_count)) +
                  (stock_weight × normalize_stock(stock_available)) +
                  (service_weight × normalize_service(service_metrics)) +
                  (tier_weight × get_tier_bonus(seller_tier))

Normalize functions return 0.0–1.0 range. Final scores are stored as 0–100.

Tiebreaker Cascade (when composite scores are equal):
    1. Primary: Higher on_time_delivery_rate
    2. Secondary: Lower return_rate
    3. Final: Earlier creation timestamp (first-mover advantage)
"""

import math

import frappe
from frappe import _
from frappe.utils import flt, cint


# =============================================================================
# SETTINGS ACCESS
# =============================================================================


def get_buy_box_settings():
    """
    Read Buy Box Settings from the Single DocType.

    Returns cached settings to avoid repeated DB reads within the same request.

    Returns:
        Document: Buy Box Settings document
    """
    return frappe.get_single("Buy Box Settings")


# =============================================================================
# NORMALIZE FUNCTIONS (all return 0.0–1.0)
# =============================================================================


def normalize_price(price, all_prices):
    """
    Normalize price score (0.0–1.0). Lower price = better score.

    Uses linear normalization against competitor prices.
    The lowest price gets 1.0, the highest gets 0.0.
    If there is only one entry or all prices are equal, returns 1.0.

    Args:
        price: The entry's offer price
        all_prices: List of all active offer prices for the product

    Returns:
        float: Normalized score between 0.0 and 1.0
    """
    price = flt(price)

    if not all_prices or len(all_prices) <= 1:
        return 1.0

    min_price = min(all_prices)
    max_price = max(all_prices)

    if max_price == min_price:
        return 1.0

    # Linear: lowest price = 1.0, highest = 0.0
    score = (max_price - price) / (max_price - min_price)
    return max(0.0, min(1.0, score))


def normalize_delivery(delivery_days, all_delivery_days):
    """
    Normalize delivery score (0.0–1.0). Faster delivery = better score.

    Uses linear normalization against competitor delivery times.
    The fastest delivery gets 1.0, the slowest gets 0.0.

    Args:
        delivery_days: The entry's delivery days
        all_delivery_days: List of all active delivery days for the product

    Returns:
        float: Normalized score between 0.0 and 1.0
    """
    delivery_days = cint(delivery_days)

    if not all_delivery_days or len(all_delivery_days) <= 1:
        return 1.0

    min_days = min(all_delivery_days)
    max_days = max(all_delivery_days)

    if max_days == min_days:
        return 1.0

    # Linear: fastest delivery = 1.0, slowest = 0.0
    score = (max_days - delivery_days) / (max_days - min_days)
    return max(0.0, min(1.0, score))


def normalize_rating(avg_rating, review_count):
    """
    Normalize rating score (0.0–1.0). Higher rating = better, with log confidence.

    Combines the seller's average rating with a confidence factor based on
    the number of reviews (logarithmic scale). New sellers with few reviews
    regress toward a neutral 0.5 score.

    Args:
        avg_rating: Seller's average rating (0–5 scale)
        review_count: Total number of reviews

    Returns:
        float: Normalized score between 0.0 and 1.0
    """
    avg_rating = flt(avg_rating)
    review_count = cint(review_count)

    if avg_rating <= 0:
        return 0.5  # Neutral score for unrated sellers

    # Base score from 0–5 rating scaled to 0–1
    base_score = min(1.0, avg_rating / 5.0)

    # Confidence factor: log10(reviews + 1) / 3, capped at 1.0
    # At ~1000 reviews, confidence reaches 1.0
    confidence = min(1.0, math.log10(review_count + 1) / 3.0)

    # Weighted: confidence pulls toward actual rating, lack of reviews pulls to 0.5
    score = 0.5 + (base_score - 0.5) * confidence
    return max(0.0, min(1.0, score))


def normalize_stock(stock_available):
    """
    Normalize stock score (0.0–1.0). Log scale, capped.

    Uses logarithmic scaling to prevent massive stock quantities from
    dominating. Capped at a reference maximum (10,000 units).

    Args:
        stock_available: Available stock quantity

    Returns:
        float: Normalized score between 0.0 and 1.0
    """
    stock = flt(stock_available)

    if stock <= 0:
        return 0.0

    # Logarithmic scale with cap at 10,000 units
    cap = 10000.0
    score = math.log10(min(stock, cap) + 1) / math.log10(cap + 1)
    return max(0.0, min(1.0, score))


def normalize_service(entry):
    """
    Normalize service score (0.0–1.0). Higher = better.

    Computes a composite service quality score from seller performance metrics:
    - Response rate (weight: 0.5) — higher is better
    - Inverse of refund/return rate (weight: 0.3) — lower refund rate is better
    - On-time delivery rate contribution (weight: 0.2) — higher is better

    Falls back to neutral 0.5 if no metrics are available.

    Args:
        entry: Buy Box Entry document or dict with seller metric fields

    Returns:
        float: Normalized score between 0.0 and 1.0
    """
    response_rate = flt(getattr(entry, "seller_response_rate", 0) or 0)
    refund_rate = flt(getattr(entry, "seller_refund_rate", 0) or 0)
    on_time_rate = flt(getattr(entry, "seller_on_time_delivery_rate", 0) or 0)

    has_metrics = response_rate > 0 or refund_rate > 0 or on_time_rate > 0

    if not has_metrics:
        return 0.5  # Neutral for sellers without metrics

    # Component scores (each 0–1)
    response_score = min(1.0, response_rate / 100.0)
    refund_score = max(0.0, 1.0 - (refund_rate / 100.0))
    on_time_score = min(1.0, on_time_rate / 100.0)

    # Weighted composite
    score = (
        0.5 * response_score +
        0.3 * refund_score +
        0.2 * on_time_score
    )

    return max(0.0, min(1.0, score))


def get_tier_bonus(seller_tier, settings=None):
    """
    Get tier bonus score from Buy Box Settings tier_bonuses table.

    Looks up the seller's tier in the configurable tier bonuses child table
    and returns the corresponding bonus score normalized to 0.0–1.0.

    Args:
        seller_tier: The seller's tier (Link to Seller Tier)
        settings: Optional pre-fetched Buy Box Settings document

    Returns:
        float: Normalized tier bonus between 0.0 and 1.0
    """
    if not seller_tier:
        return 0.0

    if not settings:
        settings = get_buy_box_settings()

    for row in (settings.tier_bonuses or []):
        if row.seller_tier == seller_tier and cint(row.is_active):
            # bonus_score is stored as 0–100, normalize to 0–1
            return max(0.0, min(1.0, flt(row.bonus_score) / 100.0))

    return 0.0


# =============================================================================
# MAIN SCORING FUNCTION
# =============================================================================


def calculate_buy_box_score(buy_box_entry):
    """
    Calculate the 6-criteria Buy Box score for a single entry.

    Reads weights from Buy Box Settings (NEVER hardcoded), applies 6 normalize
    functions, and returns the complete score breakdown. Scores are returned on
    a 0–100 scale for storage on Buy Box Entry fields.

    Args:
        buy_box_entry: Buy Box Entry document (frappe Document or dict-like object)

    Returns:
        dict: Score breakdown with keys:
            - buy_box_score (float): Composite score 0–100
            - price_score (float): Price competitiveness 0–100
            - delivery_score (float): Delivery speed 0–100
            - rating_score (float): Seller rating 0–100
            - stock_score (float): Stock availability 0–100
            - service_score (float): Service quality 0–100
            - seller_tier_bonus (float): Tier bonus 0–100
            - score_breakdown_json (str): JSON string of full breakdown
    """
    settings = get_buy_box_settings()

    # Get competitor data for relative scoring (price, delivery)
    sku_product = getattr(buy_box_entry, "sku_product", None)
    entry_name = getattr(buy_box_entry, "name", None)

    all_prices, all_delivery_days = _get_competitor_data(sku_product)

    # Calculate normalized scores (0.0–1.0)
    price_norm = normalize_price(
        flt(buy_box_entry.offer_price),
        all_prices
    )
    delivery_norm = normalize_delivery(
        cint(buy_box_entry.delivery_days),
        all_delivery_days
    )
    rating_norm = normalize_rating(
        flt(getattr(buy_box_entry, "seller_average_rating", 0) or 0),
        cint(getattr(buy_box_entry, "seller_total_reviews", 0) or 0)
    )
    stock_norm = normalize_stock(
        flt(buy_box_entry.stock_available)
    )
    service_norm = normalize_service(buy_box_entry)
    tier_norm = get_tier_bonus(
        getattr(buy_box_entry, "seller_tier", None),
        settings
    )

    # Composite score: weighted sum × 100 for 0–100 scale
    composite = (
        flt(settings.price_weight) * price_norm +
        flt(settings.delivery_weight) * delivery_norm +
        flt(settings.rating_weight) * rating_norm +
        flt(settings.stock_weight) * stock_norm +
        flt(settings.service_weight) * service_norm +
        flt(settings.tier_weight) * tier_norm
    ) * 100

    # Build score breakdown
    breakdown = {
        "price": {
            "weight": flt(settings.price_weight),
            "normalized": round(price_norm, 4),
            "score": round(price_norm * 100, 2),
            "weighted": round(flt(settings.price_weight) * price_norm * 100, 2)
        },
        "delivery": {
            "weight": flt(settings.delivery_weight),
            "normalized": round(delivery_norm, 4),
            "score": round(delivery_norm * 100, 2),
            "weighted": round(flt(settings.delivery_weight) * delivery_norm * 100, 2)
        },
        "rating": {
            "weight": flt(settings.rating_weight),
            "normalized": round(rating_norm, 4),
            "score": round(rating_norm * 100, 2),
            "weighted": round(flt(settings.rating_weight) * rating_norm * 100, 2)
        },
        "stock": {
            "weight": flt(settings.stock_weight),
            "normalized": round(stock_norm, 4),
            "score": round(stock_norm * 100, 2),
            "weighted": round(flt(settings.stock_weight) * stock_norm * 100, 2)
        },
        "service": {
            "weight": flt(settings.service_weight),
            "normalized": round(service_norm, 4),
            "score": round(service_norm * 100, 2),
            "weighted": round(flt(settings.service_weight) * service_norm * 100, 2)
        },
        "tier": {
            "weight": flt(settings.tier_weight),
            "normalized": round(tier_norm, 4),
            "score": round(tier_norm * 100, 2),
            "weighted": round(flt(settings.tier_weight) * tier_norm * 100, 2)
        }
    }

    import json
    return {
        "buy_box_score": round(composite, 2),
        "price_score": round(price_norm * 100, 2),
        "delivery_score": round(delivery_norm * 100, 2),
        "rating_score": round(rating_norm * 100, 2),
        "stock_score": round(stock_norm * 100, 2),
        "service_score": round(service_norm * 100, 2),
        "seller_tier_bonus": round(tier_norm * 100, 2),
        "score_breakdown_json": json.dumps(breakdown, indent=2)
    }


# =============================================================================
# TIEBREAKER CASCADE
# =============================================================================


def apply_tiebreaker(entries):
    """
    Sort scored entries using the tiebreaker cascade when scores are tied.

    Tiebreaker cascade (applied when buy_box_score values are equal):
        1. Primary: Higher on_time_delivery_rate
        2. Secondary: Lower return_rate
        3. Final: Earlier creation timestamp (first-mover advantage)

    Args:
        entries: List of dicts with scoring data. Each must include:
            - buy_box_score (float)
            - seller_on_time_delivery_rate (float, percentage)
            - seller_refund_rate (float, percentage)
            - creation (datetime string)

    Returns:
        list: Entries sorted by score with tiebreakers applied (highest first)
    """
    def sort_key(entry):
        score = flt(entry.get("buy_box_score", 0))
        on_time = flt(entry.get("seller_on_time_delivery_rate", 0))
        # Lower return rate is better, so negate for descending sort
        return_rate = flt(entry.get("seller_refund_rate", 0))
        # Earlier creation is better, so we use it as-is (ascending)
        creation = entry.get("creation", "")

        return (
            -score,              # Higher score first (negate for ascending sort)
            -on_time,            # Higher on_time_delivery_rate first
            return_rate,         # Lower return_rate first
            creation             # Earlier creation first
        )

    return sorted(entries, key=sort_key)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_competitor_data(sku_product):
    """
    Fetch competitor data for relative scoring (prices and delivery days).

    Gets all active Buy Box entries for the same product to enable
    relative normalization of price and delivery scores.

    Args:
        sku_product: The SKU Product name

    Returns:
        tuple: (all_prices, all_delivery_days) — lists of float/int values
    """
    if not sku_product:
        return [], []

    competitors = frappe.get_all(
        "Buy Box Entry",
        filters={
            "sku_product": sku_product,
            "status": "Active"
        },
        fields=["offer_price", "delivery_days"]
    )

    all_prices = [flt(c.offer_price) for c in competitors if flt(c.offer_price) > 0]
    all_delivery_days = [cint(c.delivery_days) for c in competitors if cint(c.delivery_days) > 0]

    return all_prices, all_delivery_days
