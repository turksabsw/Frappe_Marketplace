// Copyright (c) 2026, Trade Hub and contributors
// For license information, please see license.txt

/**
 * SKU Product Client Script
 *
 * Handles client-side behavior for SKU Product DocType including:
 * - Form actions (Activate, Deactivate, Archive)
 * - Dynamic field behaviors
 * - fetch_from refresh handling
 * - URL slug generation
 * - Media gallery integration (placeholder)
 */

frappe.ui.form.on('SKU Product', {
    /**
     * Called when form is refreshed/loaded
     */
    refresh: function(frm) {
        // Add custom buttons based on status
        frm.events.add_status_buttons(frm);

        // Setup dashboard
        frm.events.setup_dashboard(frm);

        // Initialize media gallery (UI component placeholder)
        frm.events.init_media_gallery(frm);

        // Show stock indicator
        frm.events.show_stock_indicator(frm);

        // =====================================================
        // P1: Tenant Isolation Filters
        // =====================================================
        // Seller - filter by tenant
        frm.set_query('seller', function() {
            if (frm.doc.tenant) {
                return {
                    filters: {
                        'tenant': frm.doc.tenant
                    }
                };
            }
            return {};
        });

        // Make tenant field read-only when seller is selected
        // (since tenant is auto-populated from seller via fetch_from)
        frm.set_df_property('tenant', 'read_only', frm.doc.seller ? 1 : 0);
    
        // =====================================================
        // Role-Based Field Authorization
        // =====================================================
        var is_admin = frappe.user_roles.includes('Satici Admin')
            || frappe.user_roles.includes('Alici Admin')
            || frappe.user_roles.includes('System Manager');

        if (!is_admin) {
            // Lock admin-editable fields for non-admin users
            frm.set_df_property('status', 'read_only', 1);
            frm.set_df_property('is_published', 'read_only', 1);
            frm.set_df_property('internal_notes', 'read_only', 1);

            // Hide internal notes from non-admin users
            frm.set_df_property('internal_notes', 'hidden', 1);
        }
    },

    /**
     * Called before form is saved
     */
    before_save: function(frm) {
        // Auto-generate URL slug if empty
        if (!frm.doc.url_slug && frm.doc.product_name) {
            frm.doc.url_slug = frm.events.generate_slug(frm.doc.product_name);
        }

        // Auto-generate SEO title if empty
        if (!frm.doc.seo_title && frm.doc.product_name) {
            frm.doc.seo_title = frm.doc.product_name.substring(0, 60);
        }
    },

    /**
     * Called when seller field changes
     */
    seller: function(frm) {
        // Update read-only state of tenant field
        frm.set_df_property('tenant', 'read_only', frm.doc.seller ? 1 : 0);

        if (frm.doc.seller) {
            // Auto-populate tenant from seller
            frappe.db.get_value('Seller Profile', frm.doc.seller, 'tenant', function(r) {
                if (r && r.tenant) {
                    if (!frm.doc.tenant || frm.doc.tenant !== r.tenant) {
                        frm.set_value('tenant', r.tenant);
                    }
                }
            });
        } else {
            // Seller cleared - allow tenant to be edited again
            frm.set_df_property('tenant', 'read_only', 0);

            // Clear all fetch_from fields dependent on seller
            frm.set_value('seller_name', '');
            frm.set_value('tenant', '');
            frm.set_value('tenant_name', '');
        }
    },

    /**
     * Called when category field changes
     */
    category: function(frm) {
        // Clear fetch_from fields dependent on category
        if (!frm.doc.category) {
            frm.set_value('category_name', '');
        }
    },

    /**
     * Called when brand field changes
     */
    brand: function(frm) {
        // Clear fetch_from fields dependent on brand
        if (!frm.doc.brand) {
            frm.set_value('brand_name', '');
        }
    },

    /**
     * Called when product name changes
     */
    product_name: function(frm) {
        // Auto-generate URL slug
        if (frm.doc.product_name && !frm.doc.url_slug) {
            frm.set_value('url_slug', frm.events.generate_slug(frm.doc.product_name));
        }

        // Auto-set SEO title if empty
        if (frm.doc.product_name && !frm.doc.seo_title) {
            frm.set_value('seo_title', frm.doc.product_name.substring(0, 60));
        }
    },

    /**
     * Called when status changes
     */
    status: function(frm) {
        // Update is_published based on status
        if (frm.doc.status === 'Active') {
            frm.set_value('is_published', 1);
        } else if (frm.doc.status === 'Passive' || frm.doc.status === 'Archive') {
            frm.set_value('is_published', 0);
        }
    },

    /**
     * Called when base_price changes
     */
    base_price: function(frm) {
        // Validate price is not negative
        if (frm.doc.base_price < 0) {
            frappe.msgprint(__('Price cannot be negative'));
            frm.set_value('base_price', 0);
        }
    },

    /**
     * Called when min_order_quantity changes
     */
    min_order_quantity: function(frm) {
        // Validate MOQ
        if (frm.doc.min_order_quantity < 1) {
            frm.set_value('min_order_quantity', 1);
        }

        // Ensure max >= min if max is set
        if (frm.doc.max_order_quantity > 0 &&
            frm.doc.max_order_quantity < frm.doc.min_order_quantity) {
            frm.set_value('max_order_quantity', frm.doc.min_order_quantity);
        }
    },

    /**
     * Called when stock_quantity changes
     */
    stock_quantity: function(frm) {
        // Update stock indicator
        frm.events.show_stock_indicator(frm);

        // Warn if negative and not allowed
        if (frm.doc.stock_quantity < 0 && !frm.doc.allow_negative_stock) {
            frappe.msgprint(__('Stock quantity is negative. Enable "Allow Negative Stock" or correct the quantity.'));
        }
    },

    // =========================================================================
    // CUSTOM METHODS
    // =========================================================================

    /**
     * Add status action buttons
     */
    add_status_buttons: function(frm) {
        if (frm.is_new()) return;

        // Activate button (for Draft and Passive products)
        if (frm.doc.status === 'Draft' || frm.doc.status === 'Passive') {
            frm.add_custom_button(__('Activate'), function() {
                frappe.call({
                    method: 'tr_tradehub.doctype.sku_product.sku_product.activate_product',
                    args: { product_name: frm.doc.name },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: r.message.message,
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Actions'));
        }

        // Deactivate button (for Active products)
        if (frm.doc.status === 'Active') {
            frm.add_custom_button(__('Deactivate'), function() {
                frappe.call({
                    method: 'tr_tradehub.doctype.sku_product.sku_product.deactivate_product',
                    args: { product_name: frm.doc.name },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: r.message.message,
                                indicator: 'orange'
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Actions'));
        }

        // Archive button (for non-archived products)
        if (frm.doc.status !== 'Archive') {
            frm.add_custom_button(__('Archive'), function() {
                frappe.confirm(
                    __('Are you sure you want to archive this product? This action is permanent.'),
                    function() {
                        frappe.call({
                            method: 'tr_tradehub.doctype.sku_product.sku_product.archive_product',
                            args: { product_name: frm.doc.name },
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: 'red'
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __('Actions'));
        }

        // Duplicate button
        frm.add_custom_button(__('Duplicate'), function() {
            frappe.new_doc('SKU Product', {
                product_name: frm.doc.product_name + ' (Copy)',
                seller: frm.doc.seller,
                category: frm.doc.category,
                brand: frm.doc.brand,
                description: frm.doc.description,
                short_description: frm.doc.short_description,
                base_price: frm.doc.base_price,
                currency: frm.doc.currency,
                min_order_quantity: frm.doc.min_order_quantity,
                stock_uom: frm.doc.stock_uom,
                weight: frm.doc.weight,
                weight_uom: frm.doc.weight_uom,
                country_of_origin: frm.doc.country_of_origin
            });
        }, __('Actions'));
    },

    /**
     * Setup dashboard with stats
     */
    setup_dashboard: function(frm) {
        if (frm.is_new()) return;

        // Add links section
        frm.dashboard.add_comment(__('Product Details'), 'blue', true);
    },

    /**
     * Initialize media gallery component (placeholder for UI component)
     */
    init_media_gallery: function(frm) {
        // Media gallery UI component will be initialized here
        // This is a placeholder for the custom media gallery component
        // that manages the JSON images field via a user-friendly UI

        // For now, we just hide the raw JSON field (already hidden in DocType)
        // The actual MediaGallery Vue component will be integrated in
        // the PWA frontend phase
    },

    /**
     * Show stock availability indicator
     */
    show_stock_indicator: function(frm) {
        if (frm.is_new()) return;

        var stock = flt(frm.doc.stock_quantity);
        var indicator = 'green';
        var message = __('In Stock') + ': ' + stock;

        if (!frm.doc.is_stock_item) {
            indicator = 'blue';
            message = __('Non-Stock Item');
        } else if (stock <= 0 && !frm.doc.allow_negative_stock) {
            indicator = 'red';
            message = __('Out of Stock');
        } else if (stock < 10) {
            indicator = 'orange';
            message = __('Low Stock') + ': ' + stock;
        }

        frm.dashboard.add_indicator(message, indicator);
    },

    /**
     * Generate URL-friendly slug from text
     */
    generate_slug: function(text) {
        if (!text) return '';

        // Convert to lowercase
        var slug = text.toLowerCase().trim();

        // Replace Turkish characters
        var turkishMap = {
            'c': 'c', 's': 's', 'g': 'g', 'i': 'i', 'o': 'o', 'u': 'u'
        };
        for (var tr in turkishMap) {
            slug = slug.replace(new RegExp(tr, 'g'), turkishMap[tr]);
        }

        // Replace spaces and special chars with dashes
        slug = slug.replace(/[^a-z0-9]+/g, '-');

        // Remove leading/trailing dashes
        slug = slug.replace(/^-+|-+$/g, '');

        // Limit length
        return slug.substring(0, 100);
    }
});
