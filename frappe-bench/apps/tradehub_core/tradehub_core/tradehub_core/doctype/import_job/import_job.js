// Copyright (c) 2024, TR TradeHub and contributors
// For license information, please see license.txt

frappe.ui.form.on('Import Job', {
    refresh: function(frm) {
        // =====================================================
        // Auto-Match Columns Button
        // =====================================================
        if (frm.doc.status === 'Pending' && frm.doc.import_file && !frm.is_new()) {
            frm.add_custom_button(__('Auto-Match Columns'), function() {
                run_auto_match(frm);
            }, __('Actions'));
        }

        // =====================================================
        // Mapping Template Filter
        // =====================================================
        frm.set_query('mapping_template', function() {
            var filters = {};
            if (frm.doc.import_type) {
                filters['import_type'] = frm.doc.import_type;
            }
            if (frm.doc.tenant) {
                filters['tenant'] = ['in', [frm.doc.tenant, '']];
            }
            return { filters: filters };
        });
    },

    // =====================================================
    // Apply Mapping Template on Selection
    // =====================================================
    mapping_template: function(frm) {
        if (!frm.doc.mapping_template) {
            return;
        }

        if (frm.doc.status !== 'Pending') {
            frappe.msgprint(__('Mapping template can only be applied when status is Pending'));
            frm.set_value('mapping_template', '');
            return;
        }

        frappe.call({
            method: 'tradehub_core.utils.auto_match.apply_mapping_template',
            args: {
                import_job_name: frm.doc.name,
                template_name: frm.doc.mapping_template
            },
            freeze: true,
            freeze_message: __('Applying mapping template...'),
            callback: function(r) {
                if (r.message) {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __('Mapping template applied successfully'),
                        indicator: 'green'
                    });
                }
            }
        });
    }
});


/**
 * Run auto-match for the import job and display a review/confirm dialog.
 *
 * Calls the auto_match_for_import_job API to read file headers and match
 * them against target DocType fields using 4-priority matching (Historical,
 * Exact, Normalized, Fuzzy). Displays results in a color-coded dialog
 * for user review and confirmation.
 *
 * @param {Object} frm - The Frappe form object for Import Job.
 */
function run_auto_match(frm) {
    frappe.call({
        method: 'tradehub_core.utils.auto_match.auto_match_for_import_job',
        args: {
            import_job_name: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Analyzing columns...'),
        callback: function(r) {
            if (r.message && r.message.matches) {
                show_auto_match_dialog(frm, r.message);
            }
        },
        error: function() {
            frappe.msgprint(__('Failed to run auto-match. Please check that a valid import file is attached.'));
        }
    });
}


/**
 * Show a review/confirm dialog with auto-match results.
 *
 * Displays a table of matched columns with color-coded confidence indicators:
 * - Green (>=90%): High confidence match
 * - Yellow (70-89%): Medium confidence match
 * - Red (<70%): Low confidence or no match
 *
 * Users can review matches, modify them via dropdowns, and confirm.
 * On confirm, the column_mapping is saved to the Import Job and confirmed
 * mappings are saved to Mapping History for future P0 lookups.
 *
 * @param {Object} frm - The Frappe form object.
 * @param {Object} data - Auto-match result data containing matches, headers,
 *     target_doctype, and import_type.
 */
function show_auto_match_dialog(frm, data) {
    var matches = data.matches || [];
    var target_doctype = data.target_doctype;
    var import_type = data.import_type;

    if (!matches.length) {
        frappe.msgprint(__('No columns found to match'));
        return;
    }

    // Build the dialog HTML with match results table
    var html = build_match_results_html(matches);

    var dialog = new frappe.ui.Dialog({
        title: __('Review Column Mapping'),
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'match_info',
                options: '<div style="margin-bottom: 12px;">'
                    + '<p>' + __('Target DocType') + ': <strong>'
                    + frappe.utils.escape_html(target_doctype) + '</strong></p>'
                    + '<p style="font-size: 12px; color: var(--text-muted);">'
                    + __('Review the auto-matched columns below. '
                    + 'Green indicates high confidence, yellow indicates medium, '
                    + 'and red indicates low confidence or no match.')
                    + '</p>'
                    + '</div>'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'match_results',
                options: html
            }
        ],
        primary_action_label: __('Confirm Mapping'),
        primary_action: function() {
            confirm_auto_match(frm, dialog, matches, target_doctype, import_type);
        },
        secondary_action_label: __('Cancel')
    });

    dialog.show();

    // Store matches data on dialog for later retrieval
    dialog.matches = matches;
}


/**
 * Build HTML table displaying auto-match results with color-coded confidence.
 *
 * @param {Array} matches - Array of match result objects from auto_match_columns.
 * @returns {string} HTML string for the match results table.
 */
function build_match_results_html(matches) {
    var html = '<div class="auto-match-results">';
    html += '<table class="table table-bordered" style="margin-bottom: 0;">';
    html += '<thead><tr>'
        + '<th style="width: 30%; background: var(--bg-light-gray, #f5f7fa);">'
        + __('Source Column') + '</th>'
        + '<th style="width: 30%; background: var(--bg-light-gray, #f5f7fa);">'
        + __('Matched To') + '</th>'
        + '<th style="width: 15%; background: var(--bg-light-gray, #f5f7fa);">'
        + __('Confidence') + '</th>'
        + '<th style="width: 25%; background: var(--bg-light-gray, #f5f7fa);">'
        + __('Strategy') + '</th>'
        + '</tr></thead>';
    html += '<tbody>';

    matches.forEach(function(match) {
        var confidence_color = get_confidence_color(match.confidence);
        var confidence_bg = get_confidence_bg(match.confidence);
        var target_display = match.target_label
            ? frappe.utils.escape_html(match.target_label)
                + ' <span style="color: var(--text-muted); font-size: 11px;">('
                + frappe.utils.escape_html(match.target_fieldname) + ')</span>'
            : '<span style="color: var(--text-muted);">' + __('No match') + '</span>';

        html += '<tr>'
            + '<td style="font-weight: 500;">'
            + frappe.utils.escape_html(match.source_column) + '</td>'
            + '<td>' + target_display + '</td>'
            + '<td style="text-align: center;">'
            + '<span style="display: inline-block; padding: 2px 8px; border-radius: 4px;'
            + ' background: ' + confidence_bg + '; color: ' + confidence_color
            + '; font-weight: 600; font-size: 12px;">'
            + match.confidence + '%</span></td>'
            + '<td><span style="font-size: 12px;">'
            + frappe.utils.escape_html(match.match_strategy) + '</span></td>'
            + '</tr>';
    });

    html += '</tbody></table>';
    html += '</div>';

    // Add legend
    html += '<div style="margin-top: 10px; font-size: 11px; color: var(--text-muted);">';
    html += '<span style="display: inline-block; width: 10px; height: 10px;'
        + ' background: var(--green-100, #dcfce7); border: 1px solid var(--green-600, #16a34a);'
        + ' border-radius: 2px; margin-right: 4px;"></span> '
        + __('High confidence (90%+)') + ' &nbsp;&nbsp; ';
    html += '<span style="display: inline-block; width: 10px; height: 10px;'
        + ' background: var(--yellow-100, #fef9c3); border: 1px solid var(--yellow-600, #ca8a04);'
        + ' border-radius: 2px; margin-right: 4px;"></span> '
        + __('Medium confidence (70-89%)') + ' &nbsp;&nbsp; ';
    html += '<span style="display: inline-block; width: 10px; height: 10px;'
        + ' background: var(--red-100, #fee2e2); border: 1px solid var(--red-600, #dc2626);'
        + ' border-radius: 2px; margin-right: 4px;"></span> '
        + __('Low confidence (<70%)');
    html += '</div>';

    return html;
}


/**
 * Get the text color for a confidence percentage.
 *
 * @param {number} confidence - Confidence percentage (0-100).
 * @returns {string} CSS color value.
 */
function get_confidence_color(confidence) {
    if (confidence >= 90) {
        return 'var(--green-600, #16a34a)';
    } else if (confidence >= 70) {
        return 'var(--yellow-600, #ca8a04)';
    }
    return 'var(--red-600, #dc2626)';
}


/**
 * Get the background color for a confidence percentage.
 *
 * @param {number} confidence - Confidence percentage (0-100).
 * @returns {string} CSS background color value.
 */
function get_confidence_bg(confidence) {
    if (confidence >= 90) {
        return 'var(--green-100, #dcfce7)';
    } else if (confidence >= 70) {
        return 'var(--yellow-100, #fef9c3)';
    }
    return 'var(--red-100, #fee2e2)';
}


/**
 * Confirm the auto-match results: save column_mapping and Mapping History.
 *
 * Builds a column mapping JSON from confirmed matches (those with a
 * target_fieldname), saves it to the Import Job's column_mapping field,
 * and saves confirmed mappings to Mapping History for future lookups.
 *
 * @param {Object} frm - The Frappe form object.
 * @param {Object} dialog - The review dialog to close after confirmation.
 * @param {Array} matches - The auto-match results.
 * @param {string} target_doctype - The target DocType name.
 * @param {string} import_type - The import type.
 */
function confirm_auto_match(frm, dialog, matches, target_doctype, import_type) {
    // Build column_mapping from matched results
    var column_mapping = {};
    var confirmed_mappings = [];

    matches.forEach(function(match) {
        if (match.target_fieldname) {
            column_mapping[match.source_column] = match.target_fieldname;
            confirmed_mappings.push({
                source_column: match.source_column,
                target_fieldname: match.target_fieldname
            });
        }
    });

    if (!confirmed_mappings.length) {
        frappe.msgprint(__('No columns were matched. Please configure column mapping manually.'));
        dialog.hide();
        return;
    }

    // Save column_mapping to the Import Job
    frm.set_value('column_mapping', JSON.stringify(column_mapping, null, 2));
    frm.dirty();
    frm.save().then(function() {
        // Save to Mapping History for future P0 lookups
        frappe.call({
            method: 'tradehub_core.utils.auto_match.save_to_mapping_history',
            args: {
                confirmed_mappings: confirmed_mappings,
                target_doctype: target_doctype,
                import_type: import_type,
                tenant: frm.doc.tenant || '',
                seller: frm.doc.seller || ''
            },
            callback: function() {
                frappe.show_alert({
                    message: __('Column mapping saved successfully ({0} columns matched)', [confirmed_mappings.length]),
                    indicator: 'green'
                });
            }
        });

        dialog.hide();
    });
}
