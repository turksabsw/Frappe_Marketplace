# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
PPR Auto-Scoring Engine for TradeHub B2B Marketplace (TASK-143).

Implements the weighted auto-scoring algorithm for Seller Offers
against Platform Purchase Requests. Scores are computed by normalizing
four factors across all competing offers and applying configurable
weights from Marketplace Settings.

Scoring Factors (default weights):
    Price    — 40%  (lower total_offered_amount is better)
    Delivery — 25%  (earlier proposed_delivery_date is better)
    Rating   — 20%  (higher seller_rating_snapshot is better)
    Payment  — 15%  (shorter payment terms are better)

Each factor is normalized to a [0, 100] scale relative to the min/max
values across all Submitted/Under Review offers for the same purchase
request. The final auto_score is the weighted sum, clamped to [0, 100].

Usage:
    from tradehub_commerce.tradehub_commerce.utils.ppr_scoring import (
        calculate_auto_score,
        recalculate_all_scores,
    )

    score_result = calculate_auto_score("SOF-.2026.-.00001")
    recalculate_all_scores("PPR-.2026.-.00001")
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

# Statuses eligible for scoring comparison
SCORABLE_STATUSES = ("Submitted", "Under Review")

# Default payment term scores (days → score mapping)
# Shorter payment terms are better for the buyer
PAYMENT_TERM_SCORES = {
    "pesin": 100,
    "cash": 100,
    "advance": 100,
    "7": 90,
    "15": 75,
    "30": 60,
    "45": 45,
    "60": 30,
    "90": 15,
}


def _get_scoring_weights():
    """Load PPR scoring weights from Marketplace Settings.

    Falls back to default weights (40/25/20/15) if Marketplace Settings
    has not been configured.

    Returns:
        dict: Weight percentages for price, delivery, rating, payment.
    """
    try:
        settings = frappe.get_single("Marketplace Settings")
        return {
            "price": flt(settings.price_weight or 40, 2),
            "delivery": flt(settings.delivery_weight or 25, 2),
            "rating": flt(settings.rating_weight or 20, 2),
            "payment": flt(settings.payment_weight or 15, 2),
        }
    except Exception:
        frappe.logger(__name__).warning(
            "Marketplace Settings not found, using default PPR scoring weights"
        )
        return {
            "price": 40,
            "delivery": 25,
            "rating": 20,
            "payment": 15,
        }


def _get_competing_offers(purchase_request_name):
    """Fetch all scorable offers for a given purchase request.

    Returns offers with status in SCORABLE_STATUSES along with the
    fields needed for scoring.

    Args:
        purchase_request_name: Name of the Platform Purchase Request.

    Returns:
        list[dict]: List of offer dicts with name, total_offered_amount,
            proposed_delivery_date, seller_rating_snapshot,
            proposed_payment_terms.
    """
    return frappe.get_all(
        "Seller Offer",
        filters={
            "purchase_request": purchase_request_name,
            "status": ["in", SCORABLE_STATUSES],
        },
        fields=[
            "name",
            "total_offered_amount",
            "proposed_delivery_date",
            "seller_rating_snapshot",
            "proposed_payment_terms",
        ],
    )


def _normalize_price(offer_amount, all_amounts):
    """Normalize price score: lower is better.

    Maps the offer amount to [0, 100] where the lowest amount
    gets 100 and the highest gets 0. When all amounts are equal,
    returns 100 (no differentiation).

    Args:
        offer_amount: This offer's total amount.
        all_amounts: List of all competing offer amounts.

    Returns:
        float: Normalized price score in [0, 100].
    """
    if not all_amounts:
        return 50.0

    min_amount = min(all_amounts)
    max_amount = max(all_amounts)

    if max_amount == min_amount:
        return 100.0

    # Invert: lower amount → higher score
    return flt(
        (max_amount - offer_amount) / (max_amount - min_amount) * 100,
        2,
    )


def _normalize_delivery(offer_date, all_dates, reference_date=None):
    """Normalize delivery score: earlier is better.

    Converts dates to days-from-reference (today or the earliest offer
    date) and maps to [0, 100]. The earliest delivery gets 100.
    When all dates are equal, returns 100.

    Args:
        offer_date: This offer's proposed delivery date.
        all_dates: List of all competing delivery dates (date objects).
        reference_date: Reference date for day calculations (default: today).

    Returns:
        float: Normalized delivery score in [0, 100].
    """
    if not all_dates or not offer_date:
        return 50.0

    ref = getdate(reference_date or today())

    offer_days = date_diff(getdate(offer_date), ref)
    all_days = [date_diff(getdate(d), ref) for d in all_dates]

    min_days = min(all_days)
    max_days = max(all_days)

    if max_days == min_days:
        return 100.0

    # Invert: fewer days (earlier delivery) → higher score
    return flt(
        (max_days - offer_days) / (max_days - min_days) * 100,
        2,
    )


def _normalize_rating(offer_rating, all_ratings):
    """Normalize rating score: higher is better.

    Maps the seller rating to [0, 100] where the highest rating
    gets 100 and the lowest gets 0. When all ratings are equal,
    returns 100.

    Args:
        offer_rating: This offer's seller rating snapshot.
        all_ratings: List of all competing seller ratings.

    Returns:
        float: Normalized rating score in [0, 100].
    """
    if not all_ratings:
        return 50.0

    min_rating = min(all_ratings)
    max_rating = max(all_ratings)

    if max_rating == min_rating:
        return 100.0

    # Higher rating → higher score
    return flt(
        (offer_rating - min_rating) / (max_rating - min_rating) * 100,
        2,
    )


def _parse_payment_terms(terms_text):
    """Parse payment terms text into a numeric score.

    Extracts the payment term score by matching known keywords or
    extracting day counts from the text. Returns a score in [0, 100]
    where shorter/immediate terms score higher.

    Recognized patterns:
        - "peşin", "cash", "advance" → 100
        - "7 gün", "7 days", "net 7" → 90
        - "15 gün", "15 days" → 75
        - "30 gün", "30 days", "net 30" → 60
        - "45 gün", "45 days" → 45
        - "60 gün", "60 days", "net 60" → 30
        - "90 gün", "90 days", "net 90" → 15

    Args:
        terms_text: Payment terms text from the offer.

    Returns:
        float: Payment terms score in [0, 100].
    """
    if not terms_text:
        return 50.0

    text = terms_text.strip().lower()

    # Check exact keyword matches first
    for keyword, score in PAYMENT_TERM_SCORES.items():
        if keyword in text:
            return float(score)

    # Try to extract day count from text
    import re

    day_match = re.search(r"(\d+)\s*(?:gün|gun|day|days)", text)
    if day_match:
        days = int(day_match.group(1))
        # Map days to score: 0 days → 100, 90+ days → 10
        if days <= 0:
            return 100.0
        elif days >= 90:
            return 10.0
        else:
            return flt(100 - (days / 90 * 90), 2)

    # Check for net terms: "net 30", "net30"
    net_match = re.search(r"net\s*(\d+)", text)
    if net_match:
        days = int(net_match.group(1))
        if days <= 0:
            return 100.0
        elif days >= 90:
            return 10.0
        else:
            return flt(100 - (days / 90 * 90), 2)

    # Default for unrecognized terms
    return 50.0


def _normalize_payment(offer_score, all_scores):
    """Normalize payment score: higher is better.

    Maps the parsed payment term score relative to all competing
    offers. Higher payment score (shorter terms) gets 100.
    When all scores are equal, returns 100.

    Args:
        offer_score: This offer's parsed payment terms score.
        all_scores: List of all competing payment scores.

    Returns:
        float: Normalized payment score in [0, 100].
    """
    if not all_scores:
        return 50.0

    min_score = min(all_scores)
    max_score = max(all_scores)

    if max_score == min_score:
        return 100.0

    # Higher payment score → higher normalized score
    return flt(
        (offer_score - min_score) / (max_score - min_score) * 100,
        2,
    )


def calculate_auto_score(offer_name):
    """Calculate the auto-score for a single Seller Offer.

    Loads all Submitted/Under Review offers for the same purchase
    request, normalizes each scoring factor to [0, 100] relative to
    the competition, applies weights from Marketplace Settings, and
    returns the composite score.

    The calculated score and component scores are saved directly
    to the Seller Offer document.

    Args:
        offer_name: Name of the Seller Offer to score.

    Returns:
        dict: {
            "auto_score": float (composite weighted score, 0-100),
            "price_score": float (normalized price score, 0-100),
            "delivery_score": float (normalized delivery score, 0-100),
            "rating_score": float (normalized rating score, 0-100),
            "payment_score": float (normalized payment terms score, 0-100),
        }
    """
    offer = frappe.get_doc("Seller Offer", offer_name)
    purchase_request = offer.purchase_request

    if not purchase_request:
        frappe.logger(__name__).warning(
            f"Seller Offer {offer_name} has no purchase_request, skipping scoring"
        )
        return {"auto_score": 0, "price_score": 0, "delivery_score": 0,
                "rating_score": 0, "payment_score": 0}

    # Load all competing offers (including this one)
    competing = _get_competing_offers(purchase_request)

    if not competing:
        frappe.logger(__name__).info(
            f"No scorable offers found for {purchase_request}"
        )
        return {"auto_score": 0, "price_score": 0, "delivery_score": 0,
                "rating_score": 0, "payment_score": 0}

    # Collect raw values from all offers
    all_amounts = [flt(o.total_offered_amount, 2) for o in competing]
    all_dates = [o.proposed_delivery_date for o in competing if o.proposed_delivery_date]
    all_ratings = [flt(o.seller_rating_snapshot, 2) for o in competing]
    all_payment_scores = [_parse_payment_terms(o.proposed_payment_terms) for o in competing]

    # Find this offer's raw values
    offer_amount = flt(offer.total_offered_amount, 2)
    offer_date = offer.proposed_delivery_date
    offer_rating = flt(offer.seller_rating_snapshot, 2)
    offer_payment_raw = _parse_payment_terms(offer.proposed_payment_terms)

    # Normalize each factor
    price_score = _normalize_price(offer_amount, all_amounts)
    delivery_score = _normalize_delivery(offer_date, all_dates) if offer_date and all_dates else 50.0
    rating_score = _normalize_rating(offer_rating, all_ratings)
    payment_score = _normalize_payment(offer_payment_raw, all_payment_scores)

    # Apply weights from Marketplace Settings
    weights = _get_scoring_weights()

    auto_score = flt(
        price_score * weights["price"] / 100
        + delivery_score * weights["delivery"] / 100
        + rating_score * weights["rating"] / 100
        + payment_score * weights["payment"] / 100,
        2,
    )

    # Clamp to [0, 100]
    auto_score = max(0.0, min(100.0, auto_score))

    # Save scores to the offer document
    frappe.db.set_value(
        "Seller Offer",
        offer_name,
        {
            "auto_score": auto_score,
            "price_score": price_score,
            "delivery_score": delivery_score,
            "rating_score": rating_score,
            "payment_score": payment_score,
        },
        update_modified=False,
    )

    return {
        "auto_score": auto_score,
        "price_score": price_score,
        "delivery_score": delivery_score,
        "rating_score": rating_score,
        "payment_score": payment_score,
    }


def recalculate_all_scores(purchase_request_name):
    """Recalculate auto-scores for all scorable offers of a purchase request.

    This batch function loads all Submitted/Under Review offers for the
    given purchase request and recalculates their scores. This is necessary
    because scores are relative — when a new offer arrives or an offer is
    withdrawn, all remaining offers' scores must be re-normalized.

    Should be called when:
        - A new offer is submitted
        - An offer is withdrawn or status-changed
        - A scheduled recalculation task runs
        - Marketplace Settings scoring weights change

    Args:
        purchase_request_name: Name of the Platform Purchase Request.

    Returns:
        dict: {
            "purchase_request": str,
            "offers_scored": int (number of offers recalculated),
            "results": list of per-offer score dicts,
        }
    """
    competing = _get_competing_offers(purchase_request_name)

    if not competing:
        frappe.logger(__name__).info(
            f"No scorable offers for {purchase_request_name}, skipping batch recalculation"
        )
        return {
            "purchase_request": purchase_request_name,
            "offers_scored": 0,
            "results": [],
        }

    results = []
    for offer in competing:
        result = calculate_auto_score(offer.name)
        results.append({
            "offer": offer.name,
            **result,
        })

    frappe.logger(__name__).info(
        f"Recalculated scores for {len(results)} offers on {purchase_request_name}"
    )

    return {
        "purchase_request": purchase_request_name,
        "offers_scored": len(results),
        "results": results,
    }
