// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Moderation Case', {
    refresh: function(frm) {
        // =====================================================
        // P1: Tenant Isolation Filters
        // =====================================================
        // Content Type - show only relevant DocTypes for moderation
        frm.set_query('content_type', function() {
            return {
                filters: {
                    'name': ['in', [
                        'Listing', 'Review', 'Storefront', 'Message',
                        'Seller Profile', 'Certificate'
                    ]]
                }
            };
        });

        // Account Action - filter by tenant
        frm.set_query('account_action_link', function() {
            if (frm.doc.tenant) {
                return {
                    filters: {
                        'tenant': frm.doc.tenant
                    }
                };
            }
            return {};
        });
    },

    // =====================================================
    // Clear-on-change Handlers
    // =====================================================
    tenant: function(frm) {
        // Clear fetch_from fields dependent on tenant
        if (!frm.doc.tenant) {
            frm.set_value('tenant_name', '');
        }
    }
});
