// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Brand', {
    refresh: function(frm) {
        // =====================================================
        // Dynamic Link Filters (set_query in refresh)
        // =====================================================

        // Country of Origin - show all countries (standard Link)
        frm.set_query('country_of_origin', function() {
            return {};
        });
    },

    // =========================================================================
    // CLEAR-ON-CHANGE HANDLERS (for fetch_from fields)
    // =========================================================================

    tenant: function(frm) {
        // Clear fetch_from fields when tenant is cleared
        if (!frm.doc.tenant) {
            frm.set_value('tenant_name', '');
        }
    },

    registered_by: function(frm) {
        // Clear fetch_from fields when registered_by is cleared
        if (!frm.doc.registered_by) {
            frm.set_value('registered_by_name', '');
        }
    }
});
