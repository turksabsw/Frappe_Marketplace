app_name = "tradehub_compliance"
app_title = "TradeHub Compliance"
app_publisher = "TradeHub Team"
app_description = "Legal, trust, and moderation layer for TradeHub Marketplace"
app_email = "dev@tradehub.local"
app_license = "MIT"
app_icon = "octicon octicon-law"
app_color = "#E17055"

# Dependencies - tradehub_core provides tenant isolation and ECA
required_apps = ["tradehub_core"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/tradehub_compliance/css/tradehub_compliance.css"
# app_include_js = "/assets/tradehub_compliance/js/tradehub_compliance.js"

# include js, css files in header of web template
# web_include_css = "/assets/tradehub_compliance/css/tradehub_compliance.css"
# web_include_js = "/assets/tradehub_compliance/js/tradehub_compliance.js"

# include custom scss in every website theme (without signing in)
# website_theme_scss = "tradehub_compliance/public/scss/website"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# -----

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "tradehub_compliance.utils.jinja_methods",
# 	"filters": "tradehub_compliance.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "tradehub_compliance.install.before_install"
# after_install = "tradehub_compliance.install.after_install"

# Uninstallation
# --------------

# before_uninstall = "tradehub_compliance.uninstall.before_uninstall"
# after_uninstall = "tradehub_compliance.uninstall.after_uninstall"

# Desk Notifications
# ------------------

# See frappe.core.notifications.get_notification_config

# notification_config = "tradehub_compliance.notifications.get_notification_config"

# Permissions
# -----------

# Permissions evaluated in scripted ways
# Tenant-based permission hooks for multi-tenant isolation

permission_query_conditions = {
	"Audience Segment": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Buyer Transparency Profile": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Buyer Visibility Rule": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Certificate": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Certificate Type": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Consent Channel": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Consent Method": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Consent Record": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Consent Text": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Consent Topic": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Contract Instance": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Contract Rule": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Contract Template": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Data Sharing Preference": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Marketplace Consent Record": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Marketplace Contract Instance": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Marketplace Contract Template": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Masked Message": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Message": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Message Thread": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Moderation Case": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Review": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Risk Score": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Sample Request": "tradehub_core.permissions.get_tenant_permission_query_conditions",
	"Seller Transparency Profile": "tradehub_core.permissions.get_tenant_permission_query_conditions",
}

has_permission = {
	"Audience Segment": "tradehub_core.permissions.has_tenant_permission",
	"Buyer Transparency Profile": "tradehub_core.permissions.has_tenant_permission",
	"Buyer Visibility Rule": "tradehub_core.permissions.has_tenant_permission",
	"Certificate": "tradehub_core.permissions.has_tenant_permission",
	"Certificate Type": "tradehub_core.permissions.has_tenant_permission",
	"Consent Channel": "tradehub_core.permissions.has_tenant_permission",
	"Consent Method": "tradehub_core.permissions.has_tenant_permission",
	"Consent Record": "tradehub_core.permissions.has_tenant_permission",
	"Consent Text": "tradehub_core.permissions.has_tenant_permission",
	"Consent Topic": "tradehub_core.permissions.has_tenant_permission",
	"Contract Instance": "tradehub_core.permissions.has_tenant_permission",
	"Contract Rule": "tradehub_core.permissions.has_tenant_permission",
	"Contract Template": "tradehub_core.permissions.has_tenant_permission",
	"Data Sharing Preference": "tradehub_core.permissions.has_tenant_permission",
	"Marketplace Consent Record": "tradehub_core.permissions.has_tenant_permission",
	"Marketplace Contract Instance": "tradehub_core.permissions.has_tenant_permission",
	"Marketplace Contract Template": "tradehub_core.permissions.has_tenant_permission",
	"Masked Message": "tradehub_core.permissions.has_tenant_permission",
	"Message": "tradehub_core.permissions.has_tenant_permission",
	"Message Thread": "tradehub_core.permissions.has_tenant_permission",
	"Moderation Case": "tradehub_core.permissions.has_tenant_permission",
	"Review": "tradehub_core.permissions.has_tenant_permission",
	"Risk Score": "tradehub_core.permissions.has_tenant_permission",
	"Sample Request": "tradehub_core.permissions.has_tenant_permission",
	"Seller Transparency Profile": "tradehub_core.permissions.has_tenant_permission",
}

# DocType Class
# -------------

# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------

# Hook on document methods and events

# NOTE: All compliance DocType lifecycle events are handled directly by their
# respective class methods (before_insert, validate, on_update, on_trash).
# No doc_events registration is needed because:
#   - DataSharingPreference.on_update: triggers 3-phase consent withdrawal
#   - SellerTransparencyProfile.on_update: refreshes last_refreshed timestamp
#   - MaskedMessage.before_insert: calls scan_and_sanitize_message_body
#   - AudienceSegment.on_update: calls enqueue_recompute_if_filter_changed
#   - AudienceSegment.on_trash: cleans up segment members
# Frappe automatically invokes these class methods during document lifecycle.

doc_events = {
	# Contract automation hooks - auto-generate contracts on key document events
	"Seller Application": {
		"on_submit": "tradehub_compliance.utils.contract_automation.handle_seller_application_approval"
	},
	"Marketplace Order": {
		"on_submit": "tradehub_compliance.utils.contract_automation.handle_marketplace_order_submit"
	},
	"Seller Profile": {
		"after_insert": "tradehub_compliance.utils.contract_automation.handle_seller_profile_created"
	}
}

# Scheduled Tasks
# ---------------

# Compliance-specific scheduled tasks:
# - certificate_alerts: daily alerts for expiring certificates (legacy)
# - Transparency tasks: refresh_transparency_metrics, check_certificate_expiry, anonymize_inactive_consent_data
# - Audience tasks: compute_all_audience_segments, compute_segment_metrics, cleanup_expired_masked_messages, pii_audit_scan
scheduler_events = {
	"daily": [
		"tradehub_compliance.tasks.certificate_alerts",
		"tradehub_compliance.utils.contract_automation.expire_unsigned_contracts"
	],
	"weekly": [
		"tradehub_compliance.tradehub_compliance.transparency.tasks.anonymize_inactive_consent_data",
		"tradehub_compliance.tradehub_compliance.audience.tasks.cleanup_expired_masked_messages",
		"tradehub_compliance.tradehub_compliance.audience.tasks.pii_audit_scan",
	],
	"cron": {
		"0 2 * * *": [
			"tradehub_compliance.tradehub_compliance.transparency.tasks.refresh_transparency_metrics",
		],
		"30 2 * * *": [
			"tradehub_compliance.tradehub_compliance.transparency.tasks.check_certificate_expiry",
		],
		"0 3 * * *": [
			"tradehub_compliance.tradehub_compliance.audience.tasks.compute_all_audience_segments",
		],
		"30 3 * * *": [
			"tradehub_compliance.tradehub_compliance.audience.tasks.compute_segment_metrics",
		],
	}
}

# Testing
# -------

# before_tests = "tradehub_compliance.install.before_tests"

# Overriding Methods
# ------------------------------

# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "tradehub_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "tradehub_compliance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Request Events
# --------------

# before_request = ["tradehub_compliance.utils.before_request"]
# after_request = ["tradehub_compliance.utils.after_request"]

# Job Events
# ----------

# before_job = ["tradehub_compliance.utils.before_job"]
# after_job = ["tradehub_compliance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"tradehub_compliance.auth.validate"
# ]
