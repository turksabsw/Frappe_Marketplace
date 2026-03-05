// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Media Library', {
    refresh: function(frm) {
        // Both uploaded_by and tenant are read_only Link fields
        // No set_query needed for read-only fields
        // No clear-on-change needed since users cannot modify them
    }
});
