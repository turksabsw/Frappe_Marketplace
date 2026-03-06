// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Escrow Account', {
    refresh: function(frm) {
        // =====================================================
        // P1: Tenant Isolation Filters
        // =====================================================
        // Marketplace Order - filter by tenant
        frm.set_query('marketplace_order', function() {
            if (frm.doc.tenant) {
                return {
                    filters: {
                        'tenant': frm.doc.tenant
                    }
                };
            }
            return {};
        });

        // Sub Order - filter by tenant and marketplace_order
        frm.set_query('sub_order', function() {
            let filters = {};
            if (frm.doc.tenant) {
                filters['tenant'] = frm.doc.tenant;
            }
            if (frm.doc.marketplace_order) {
                filters['marketplace_order'] = frm.doc.marketplace_order;
            }
            return {
                filters: filters
            };
        });

        // Payment Intent - filter by tenant and marketplace_order
        frm.set_query('payment_intent', function() {
            let filters = {};
            if (frm.doc.tenant) {
                filters['tenant'] = frm.doc.tenant;
            }
            if (frm.doc.marketplace_order) {
                filters['marketplace_order'] = frm.doc.marketplace_order;
            }
            return {
                filters: filters
            };
        });

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

        // Dispute Case - filter by tenant
        frm.set_query('dispute_case', function() {
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
            frm.set_df_property('commission_amount', 'read_only', 1);
            frm.set_df_property('payout_status', 'read_only', 1);
            frm.set_df_property('dispute_status', 'read_only', 1);
            frm.set_df_property('dispute_resolution', 'read_only', 1);
            frm.set_df_property('erpnext_sync_status', 'read_only', 1);
            frm.set_df_property('internal_notes', 'read_only', 1);

            // Hide internal notes from non-admin users
            frm.set_df_property('internal_notes', 'hidden', 1);
        }
    },

    // =====================================================
    // Clear-on-change handlers for fetch_from fields
    // =====================================================
    tenant: function(frm) {
        if (!frm.doc.tenant) {
            frm.set_value('tenant_name', '');
        }
    },

    seller: function(frm) {
        if (!frm.doc.seller) {
            frm.set_value('seller_name', '');
        }
    },

    buyer: function(frm) {
        if (!frm.doc.buyer) {
            frm.set_value('buyer_name', '');
        }
    },

    marketplace_order: function(frm) {
        if (!frm.doc.marketplace_order) {
            frm.set_value('marketplace_order_number', '');
        }
    }
});
