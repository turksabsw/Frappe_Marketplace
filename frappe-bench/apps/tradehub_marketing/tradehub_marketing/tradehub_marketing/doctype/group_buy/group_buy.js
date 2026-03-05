// Copyright (c) 2026, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Group Buy', {
    refresh: function(frm) {
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

        // =====================================================
        // Listing - filter by seller and tenant
        // =====================================================
        frm.set_query('listing', function() {
            let filters = {};
            if (frm.doc.seller) {
                filters['seller'] = frm.doc.seller;
            }
            if (frm.doc.tenant) {
                filters['tenant'] = frm.doc.tenant;
            }
            return {
                filters: filters
            };
        });

        // =====================================================
        // Currency - filter enabled
        // =====================================================
        frm.set_query('currency', function() {
            return {
                filters: {
                    'enabled': 1
                }
            };
        });

        // Make tenant field read-only when seller is selected
        frm.set_df_property('tenant', 'read_only', frm.doc.seller ? 1 : 0);
    },

    tenant: function(frm) {
        // When tenant changes, check if current seller belongs to new tenant
        if (frm.doc.seller) {
            if (frm.doc.tenant) {
                frappe.db.get_value('Seller Profile', frm.doc.seller, 'tenant', function(r) {
                    if (r && r.tenant !== frm.doc.tenant) {
                        frm.set_value('seller', null);
                        frappe.show_alert({
                            message: __('Seller cleared because it does not belong to the selected Tenant'),
                            indicator: 'orange'
                        });
                    }
                });
            } else {
                frm.set_value('seller', null);
            }
        }
    },

    seller: function(frm) {
        if (frm.doc.seller) {
            // Auto-populate tenant from seller
            frappe.db.get_value('Seller Profile', frm.doc.seller, 'tenant', function(r) {
                if (r && r.tenant) {
                    if (!frm.doc.tenant || frm.doc.tenant !== r.tenant) {
                        frm.set_value('tenant', r.tenant);
                    }
                }
            });
            frm.set_df_property('tenant', 'read_only', 1);

            // Check if current listing belongs to new seller
            if (frm.doc.listing) {
                frappe.db.get_value('Listing', frm.doc.listing, 'seller', function(r) {
                    if (r && r.seller !== frm.doc.seller) {
                        frm.set_value('listing', null);
                        frappe.show_alert({
                            message: __('Listing cleared because it does not belong to the selected Seller'),
                            indicator: 'orange'
                        });
                    }
                });
            }
        } else {
            // Clear dependent fields when seller is emptied
            frm.set_value('listing', null);
            frm.set_value('tenant', '');
            frm.set_df_property('tenant', 'read_only', 0);
        }
    },

    listing: function(frm) {
        // If listing is selected and seller is empty, auto-populate seller from listing
        if (frm.doc.listing && !frm.doc.seller) {
            frappe.db.get_value('Listing', frm.doc.listing, ['seller', 'tenant'], function(r) {
                if (r) {
                    if (r.seller) {
                        frm.set_value('seller', r.seller);
                    }
                    if (r.tenant) {
                        frm.set_value('tenant', r.tenant);
                    }
                }
            });
        }
    }
});
