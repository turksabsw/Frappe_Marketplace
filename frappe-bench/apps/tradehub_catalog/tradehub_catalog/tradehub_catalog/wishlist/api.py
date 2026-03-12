# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
Wishlist API Endpoints

REST API for wishlist and quick favorite operations.
Provides 6 whitelisted endpoints for managing user wishlists,
adding/removing items, moving items between lists, toggling
quick favorites, and accessing public wishlists.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cint, flt
from typing import Dict, Any, List, Optional
import json


def _response(success: bool, data: Any = None, message: str = None, errors: List = None) -> Dict:
    """Standard API response format."""
    return {
        "success": success,
        "data": data,
        "message": message,
        "errors": errors or []
    }


def _get_current_buyer() -> Optional[str]:
    """Get current user's buyer profile."""
    return frappe.db.get_value("Buyer Profile", {"user": frappe.session.user}, "name")


def _get_user_tenant() -> Optional[str]:
    """Get the tenant for the current user."""
    buyer = _get_current_buyer()
    if buyer:
        return frappe.db.get_value("Buyer Profile", buyer, "tenant")
    return None


def _get_or_create_default_wishlist(user: str, tenant: str) -> str:
    """
    Get the user's default wishlist, or create one if none exists.

    Args:
        user: User email/ID
        tenant: Tenant name for multi-tenant isolation

    Returns:
        Name of the default wishlist
    """
    default_wishlist = frappe.db.get_value(
        "User Wishlist",
        {"user": user, "is_default": 1},
        "name"
    )

    if default_wishlist:
        return default_wishlist

    # Create a default wishlist
    wishlist = frappe.get_doc({
        "doctype": "User Wishlist",
        "user": user,
        "list_name": _("My Wishlist"),
        "is_default": 1,
        "tenant": tenant,
    })
    wishlist.insert(ignore_permissions=True)
    frappe.db.commit()

    return wishlist.name


@frappe.whitelist()
def add_to_wishlist(
    wishlist: str = None,
    product: str = None,
    listing: str = None,
    target_price: float = None
) -> Dict:
    """
    Add a product or listing to a wishlist.

    If no wishlist is specified, uses the user's default wishlist.
    Captures the current price at the time of adding.

    Args:
        wishlist: User Wishlist name (optional, uses default if not provided)
        product: Product name to add
        listing: Listing name to add
        target_price: User's target price for price drop alerts

    Returns:
        API response with the created item name
    """
    try:
        user = frappe.session.user

        if not product and not listing:
            return _response(False, message=_("Either product or listing is required"))

        # Get tenant for the current user
        tenant = _get_user_tenant()
        if not tenant:
            return _response(False, message=_("No tenant found for current user"))

        # Resolve wishlist
        if not wishlist:
            wishlist = _get_or_create_default_wishlist(user, tenant)

        # Validate wishlist ownership
        wishlist_doc = frappe.get_doc("User Wishlist", wishlist)

        if wishlist_doc.user != user:
            return _response(False, message=_("You don't have permission to modify this wishlist"))

        # Validate product/listing exists
        if product and not frappe.db.exists("Product", product):
            return _response(False, message=_("Product '{0}' does not exist").format(product))

        if listing and not frappe.db.exists("Listing", listing):
            return _response(False, message=_("Listing '{0}' does not exist").format(listing))

        # Check for duplicate item in wishlist
        for item in wishlist_doc.items:
            if product and item.product == product:
                return _response(
                    False,
                    message=_("This product is already in your wishlist"),
                    data={"item_name": item.name}
                )
            if listing and item.listing == listing:
                return _response(
                    False,
                    message=_("This listing is already in your wishlist"),
                    data={"item_name": item.name}
                )

        # Get current price
        current_price = 0
        seller_store = None
        if listing:
            listing_data = frappe.db.get_value(
                "Listing", listing, ["price", "seller_store"], as_dict=True
            )
            if listing_data:
                current_price = flt(listing_data.get("price", 0))
                seller_store = listing_data.get("seller_store")
        elif product:
            # Try to get the lowest listing price for this product
            lowest_listing = frappe.db.get_value(
                "Listing",
                {"product": product, "status": "Active"},
                ["price", "seller_store"],
                order_by="price asc",
                as_dict=True
            )
            if lowest_listing:
                current_price = flt(lowest_listing.get("price", 0))
                seller_store = lowest_listing.get("seller_store")

        # Add item to wishlist
        new_item = wishlist_doc.append("items", {
            "product": product,
            "listing": listing,
            "seller_store": seller_store,
            "added_price": current_price,
            "current_price": current_price,
            "price_change_pct": 0,
            "target_price": flt(target_price) if target_price else None,
            "priority": "Medium",
            "notification_enabled": 1,
            "added_at": now_datetime(),
        })

        wishlist_doc.save()
        frappe.db.commit()

        # Update wishlist_count on the product
        if product:
            _increment_wishlist_count("Product", product)
        if listing:
            _increment_wishlist_count("Listing", listing)

        return _response(True, data={"item_name": new_item.name})

    except Exception as e:
        frappe.log_error(f"Error adding to wishlist: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def remove_from_wishlist(wishlist: str, item_name: str) -> Dict:
    """
    Remove an item from a wishlist.

    Args:
        wishlist: User Wishlist name
        item_name: Wishlist Item name to remove

    Returns:
        API response confirming removal
    """
    try:
        user = frappe.session.user

        if not wishlist:
            return _response(False, message=_("Wishlist is required"))

        if not item_name:
            return _response(False, message=_("Item name is required"))

        # Validate wishlist ownership
        wishlist_doc = frappe.get_doc("User Wishlist", wishlist)

        if wishlist_doc.user != user:
            return _response(False, message=_("You don't have permission to modify this wishlist"))

        # Find and remove the item
        item_to_remove = None
        for item in wishlist_doc.items:
            if item.name == item_name:
                item_to_remove = item
                break

        if not item_to_remove:
            return _response(False, message=_("Item not found in this wishlist"))

        # Track product/listing for counter update
        product = item_to_remove.product
        listing = item_to_remove.listing

        wishlist_doc.remove(item_to_remove)
        wishlist_doc.save()
        frappe.db.commit()

        # Decrement wishlist_count
        if product:
            _decrement_wishlist_count("Product", product)
        if listing:
            _decrement_wishlist_count("Listing", listing)

        return _response(True, message=_("Item removed from wishlist"))

    except Exception as e:
        frappe.log_error(f"Error removing from wishlist: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def get_user_wishlists() -> Dict:
    """
    Get all wishlists for the current user.

    Returns:
        API response with list of wishlists and their items
    """
    try:
        user = frappe.session.user

        wishlists = frappe.get_all(
            "User Wishlist",
            filters={"user": user},
            fields=[
                "name", "list_name", "is_default", "is_public",
                "share_token", "share_url", "total_items",
                "digest_mode", "creation", "modified"
            ],
            order_by="is_default desc, modified desc"
        )

        # Enrich with item details
        for wl in wishlists:
            wl["items"] = frappe.get_all(
                "Wishlist Item",
                filters={"parent": wl["name"]},
                fields=[
                    "name", "product", "listing", "seller_store",
                    "added_price", "current_price", "price_change_pct",
                    "target_price", "priority", "notification_enabled",
                    "notes", "added_at"
                ],
                order_by="added_at desc"
            )

        return _response(True, data={"wishlists": wishlists})

    except Exception as e:
        frappe.log_error(f"Error getting user wishlists: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def move_items(
    source_wishlist: str,
    target_wishlist: str,
    items: str = None
) -> Dict:
    """
    Move items from one wishlist to another.

    Args:
        source_wishlist: Source User Wishlist name
        target_wishlist: Target User Wishlist name
        items: JSON array of Wishlist Item names to move

    Returns:
        API response with count of moved items
    """
    try:
        user = frappe.session.user

        if not source_wishlist or not target_wishlist:
            return _response(False, message=_("Both source and target wishlists are required"))

        if source_wishlist == target_wishlist:
            return _response(False, message=_("Source and target wishlists must be different"))

        # Validate ownership of both wishlists
        source_doc = frappe.get_doc("User Wishlist", source_wishlist)
        if source_doc.user != user:
            return _response(False, message=_("You don't have permission to modify the source wishlist"))

        target_doc = frappe.get_doc("User Wishlist", target_wishlist)
        if target_doc.user != user:
            return _response(False, message=_("You don't have permission to modify the target wishlist"))

        # Parse items list
        if items:
            items_list = json.loads(items) if isinstance(items, str) else items
        else:
            # Move all items if none specified
            items_list = [item.name for item in source_doc.items]

        if not items_list:
            return _response(False, message=_("No items to move"))

        moved_count = 0
        for item_name in items_list:
            # Find item in source
            source_item = None
            for item in source_doc.items:
                if item.name == item_name:
                    source_item = item
                    break

            if not source_item:
                continue

            # Check if product/listing already exists in target
            duplicate = False
            for existing_item in target_doc.items:
                if (source_item.product and existing_item.product == source_item.product) or \
                   (source_item.listing and existing_item.listing == source_item.listing):
                    duplicate = True
                    break

            if duplicate:
                continue

            # Add to target
            target_doc.append("items", {
                "product": source_item.product,
                "listing": source_item.listing,
                "seller_store": source_item.seller_store,
                "added_price": source_item.added_price,
                "current_price": source_item.current_price,
                "price_change_pct": source_item.price_change_pct,
                "target_price": source_item.target_price,
                "priority": source_item.priority,
                "notes": source_item.notes,
                "notification_enabled": source_item.notification_enabled,
                "added_at": source_item.added_at,
            })

            # Remove from source
            source_doc.remove(source_item)
            moved_count += 1

        if moved_count > 0:
            source_doc.save()
            target_doc.save()
            frappe.db.commit()

        return _response(True, data={"moved_count": moved_count})

    except Exception as e:
        frappe.log_error(f"Error moving wishlist items: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def toggle_quick_favorite(target_type: str, target_reference: str) -> Dict:
    """
    Toggle a quick favorite for the current user.

    If the favorite exists, removes it. If not, creates it.
    Updates the counter on the target document accordingly.

    Args:
        target_type: Type of target (Product, Seller Profile, Seller Store, Listing)
        target_reference: Reference to the target document

    Returns:
        API response with favorite state and current count
    """
    try:
        user = frappe.session.user

        if not target_type:
            return _response(False, message=_("Target type is required"))

        if not target_reference:
            return _response(False, message=_("Target reference is required"))

        valid_types = ["Product", "Seller Profile", "Seller Store", "Listing"]
        if target_type not in valid_types:
            return _response(
                False,
                message=_("Invalid target type. Must be one of: {0}").format(
                    ", ".join(valid_types)
                )
            )

        # Validate target exists
        if not frappe.db.exists(target_type, target_reference):
            return _response(
                False,
                message=_("{0} '{1}' does not exist").format(target_type, target_reference)
            )

        # Check if favorite exists
        existing = frappe.db.get_value(
            "Quick Favorite",
            {
                "user": user,
                "target_type": target_type,
                "target_reference": target_reference,
            },
            "name"
        )

        if existing:
            # Remove favorite
            frappe.delete_doc("Quick Favorite", existing, force=True)
            frappe.db.commit()
            is_favorite = False
        else:
            # Get tenant
            tenant = _get_user_tenant()
            if not tenant:
                return _response(False, message=_("No tenant found for current user"))

            # Create favorite
            fav = frappe.get_doc({
                "doctype": "Quick Favorite",
                "user": user,
                "target_type": target_type,
                "target_reference": target_reference,
                "tenant": tenant,
            })
            fav.insert()
            frappe.db.commit()
            is_favorite = True

        # Get current count from target
        from tradehub_catalog.tradehub_catalog.doctype.quick_favorite.quick_favorite import COUNTER_FIELD_MAP
        counter_field = COUNTER_FIELD_MAP.get(target_type, "favorite_count")
        current_count = cint(
            frappe.db.get_value(target_type, target_reference, counter_field)
        )

        return _response(True, data={"is_favorite": is_favorite, "count": current_count})

    except Exception as e:
        frappe.log_error(f"Error toggling quick favorite: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist(allow_guest=True)
def get_public_wishlist(token: str) -> Dict:
    """
    Get a public wishlist by its share token.

    This endpoint is accessible without authentication (allow_guest=True)
    to support public sharing of wishlists.

    Args:
        token: Share token for the public wishlist

    Returns:
        API response with wishlist details and items
    """
    try:
        if not token:
            return _response(False, message=_("Share token is required"))

        # Find wishlist by token
        wishlist_name = frappe.db.get_value(
            "User Wishlist",
            {"share_token": token, "is_public": 1},
            "name"
        )

        if not wishlist_name:
            return _response(False, message=_("Wishlist not found or is not public"))

        # Get wishlist details (exclude sensitive user info)
        wishlist = frappe.db.get_value(
            "User Wishlist",
            wishlist_name,
            ["name", "list_name", "total_items", "creation", "modified"],
            as_dict=True
        )

        # Get items with product details
        items = frappe.get_all(
            "Wishlist Item",
            filters={"parent": wishlist_name},
            fields=[
                "name", "product", "listing", "seller_store",
                "current_price", "priority", "added_at"
            ],
            order_by="added_at desc"
        )

        return _response(True, data={"wishlist": wishlist, "items": items})

    except Exception as e:
        frappe.log_error(f"Error getting public wishlist: {str(e)}")
        return _response(False, message=str(e))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _increment_wishlist_count(doctype: str, name: str) -> None:
    """
    Increment the wishlist_count on a target document.

    Args:
        doctype: Target DocType (Product or Listing)
        name: Document name
    """
    if not frappe.db.exists(doctype, name):
        return

    current = cint(frappe.db.get_value(doctype, name, "wishlist_count"))
    frappe.db.set_value(
        doctype, name, "wishlist_count", current + 1,
        update_modified=False
    )


def _decrement_wishlist_count(doctype: str, name: str) -> None:
    """
    Decrement the wishlist_count on a target document.

    Args:
        doctype: Target DocType (Product or Listing)
        name: Document name
    """
    if not frappe.db.exists(doctype, name):
        return

    current = cint(frappe.db.get_value(doctype, name, "wishlist_count"))
    frappe.db.set_value(
        doctype, name, "wishlist_count", max(0, current - 1),
        update_modified=False
    )
