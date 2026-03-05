// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Payment Intent', {
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

        // Cart - filter by tenant
        frm.set_query('cart', function() {
            if (frm.doc.tenant) {
                return {
                    filters: {
                        'tenant': frm.doc.tenant
                    }
                };
            }
            return {};
        });

        // Organization - filter by tenant
        frm.set_query('organization', function() {
            if (frm.doc.tenant) {
                return {
                    filters: {
                        'tenant': frm.doc.tenant
                    }
                };
            }
            return {};
        });

        // Escrow Account - filter by tenant and marketplace_order
        frm.set_query('escrow_account', function() {
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

        // Make tenant field read-only when buyer is selected
        frm.set_df_property('tenant', 'read_only', frm.doc.buyer ? 1 : 0);
    },

    // =====================================================
    // Clear-on-change handlers for fetch_from fields
    // =====================================================
    tenant: function(frm) {
        if (!frm.doc.tenant) {
            frm.set_value('tenant_name', '');
        }
    },

    buyer: function(frm) {
        if (!frm.doc.buyer) {
            frm.set_value('buyer_name', '');
            frm.set_value('buyer_email', '');
        }
    },

    marketplace_order: function(frm) {
        if (!frm.doc.marketplace_order) {
            frm.set_value('marketplace_order_number', '');
        }
    }
});
