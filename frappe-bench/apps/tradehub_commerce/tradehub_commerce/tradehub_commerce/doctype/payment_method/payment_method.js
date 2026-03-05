// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Payment Method', {
    refresh: function(frm) {
        // =====================================================
        // Configuration Link Filters
        // =====================================================
        // Payment Method is a configuration DocType - no tenant isolation needed.
        // Currency, Email Template, Print Format, Mode of Payment, Account
        // are system-level DocTypes that don't require tenant filtering.
    }
});
