// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Carrier', {
    refresh: function(frm) {
        // =====================================================
        // UOM Filter
        // =====================================================
        frm.set_query('weight_uom', function() {
            return {
                filters: {
                    'name': ['in', [
                        'Kilogram', 'Gram', 'Pound', 'Ounce', 'Kg', 'Gm',
                        'g', 'kg', 'lb', 'oz', 'Milligram', 'Ton'
                    ]]
                }
            };
        });

        // =====================================================
        // Currency Filter
        // =====================================================
        frm.set_query('currency', function() {
            return {
                filters: {
                    'enabled': 1
                }
            };
        });
    },

    tenant: function(frm) {
        if (!frm.doc.tenant) {
            // Clear fetch_from field dependent on tenant
            frm.set_value('tenant_name', '');
        }
    }
});
