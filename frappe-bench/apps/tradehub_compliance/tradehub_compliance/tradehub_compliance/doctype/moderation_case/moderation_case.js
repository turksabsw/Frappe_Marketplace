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

        // =====================================================
        // Role-Based Field Authorization
        // =====================================================
        var is_admin = frappe.user_roles.includes('Satici Admin')
            || frappe.user_roles.includes('Alici Admin')
            || frappe.user_roles.includes('System Manager');

        if (!is_admin) {
            // Lock admin-editable fields for non-admin users
            frm.set_df_property('priority', 'read_only', 1);
            frm.set_df_property('status', 'read_only', 1);
            frm.set_df_property('assigned_to', 'read_only', 1);
            frm.set_df_property('decision', 'read_only', 1);
            frm.set_df_property('decision_reason', 'read_only', 1);
            frm.set_df_property('decision_notes', 'read_only', 1);
            frm.set_df_property('internal_notes', 'read_only', 1);

            // Hide internal notes from non-admin users
            frm.set_df_property('internal_notes', 'hidden', 1);
        }

        // =====================================================
        // Content Snapshot Renderer
        // =====================================================
        render_content_snapshot(frm);
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

/**
 * Render content_snapshot as a formatted key-value card below the Code field.
 * Supports both legacy flat JSON schema and new _meta/data structure.
 * All values are HTML-escaped via frappe.utils.escape_html() for XSS protection.
 */
function render_content_snapshot(frm) {
    // Remove any previously rendered snapshot card
    var wrapper = frm.fields_dict.content_snapshot
        && frm.fields_dict.content_snapshot.$wrapper;
    if (!wrapper) {
        return;
    }
    wrapper.find('.snapshot-rendered-card').remove();

    if (!frm.doc.content_snapshot) {
        return;
    }

    var snapshot;
    try {
        snapshot = JSON.parse(frm.doc.content_snapshot);
    } catch (e) {
        // Invalid JSON — skip rendering
        return;
    }

    if (!snapshot || typeof snapshot !== 'object') {
        return;
    }

    // Detect schema: new _meta/data structure vs legacy flat JSON
    var meta = null;
    var data = snapshot;

    if (snapshot._meta && snapshot.data && typeof snapshot.data === 'object') {
        // New schema with _meta and data keys
        meta = snapshot._meta;
        data = snapshot.data;
    }

    // Build HTML table rows from data
    var rows = build_snapshot_rows(data);
    if (!rows.length) {
        return;
    }

    var html = '<div class="snapshot-rendered-card" style="margin-top: 10px;">';

    // Render meta info header if present
    if (meta) {
        html += '<div style="padding: 8px 12px; background: var(--bg-light-gray, #f5f7fa);'
            + ' border: 1px solid var(--border-color, #d1d8dd); border-bottom: none;'
            + ' border-radius: 4px 4px 0 0; font-size: 12px; color: var(--text-muted, #8d99a6);">';
        if (meta.captured_at) {
            html += '<span>' + frappe.utils.escape_html(String(meta.captured_at)) + '</span>';
        }
        if (meta.content_type) {
            html += '<span style="margin-left: 12px; font-weight: 500;">'
                + frappe.utils.escape_html(String(meta.content_type)) + '</span>';
        }
        if (meta.content_id) {
            html += '<span style="margin-left: 8px;">'
                + frappe.utils.escape_html(String(meta.content_id)) + '</span>';
        }
        html += '</div>';
    }

    // Render key-value table
    var border_radius = meta ? '0 0 4px 4px' : '4px';
    html += '<table class="table table-bordered" style="margin-bottom: 0;'
        + ' border-radius: ' + border_radius + '; overflow: hidden;">';
    html += '<thead><tr>'
        + '<th style="width: 35%; background: var(--bg-light-gray, #f5f7fa);">'
        + __('Field') + '</th>'
        + '<th style="background: var(--bg-light-gray, #f5f7fa);">'
        + __('Value') + '</th>'
        + '</tr></thead>';
    html += '<tbody>';

    rows.forEach(function(row) {
        html += '<tr>'
            + '<td style="font-weight: 500; vertical-align: top;">'
            + frappe.utils.escape_html(row.key) + '</td>'
            + '<td>' + row.value_html + '</td>'
            + '</tr>';
    });

    html += '</tbody></table>';
    html += '</div>';

    wrapper.append(html);
}

/**
 * Build an array of {key, value_html} rows from a snapshot data object.
 * Recursively handles nested objects and arrays.
 * All leaf values are HTML-escaped for XSS protection.
 */
function build_snapshot_rows(data, prefix) {
    var rows = [];
    if (!data || typeof data !== 'object') {
        return rows;
    }

    var keys = Object.keys(data);
    keys.forEach(function(key) {
        var val = data[key];
        var display_key = prefix ? (prefix + '.' + key) : key;

        if (val === null || val === undefined) {
            rows.push({
                key: display_key,
                value_html: '<span style="color: var(--text-muted, #8d99a6);">—</span>'
            });
        } else if (Array.isArray(val)) {
            // Render arrays as comma-separated escaped values
            var items = val.map(function(item) {
                if (item && typeof item === 'object') {
                    return frappe.utils.escape_html(JSON.stringify(item));
                }
                return frappe.utils.escape_html(String(item));
            });
            rows.push({
                key: display_key,
                value_html: items.join(', ')
            });
        } else if (typeof val === 'object') {
            // Recursively flatten nested objects
            var nested = build_snapshot_rows(val, display_key);
            rows = rows.concat(nested);
        } else {
            rows.push({
                key: display_key,
                value_html: frappe.utils.escape_html(String(val))
            });
        }
    });

    return rows;
}
