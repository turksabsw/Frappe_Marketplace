# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Contract automation utilities for TradeHub compliance platform.

Provides functions for automated contract lifecycle management including
rule evaluation, contract creation, template rendering, and expiration.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime


def handle_seller_application_approval(doc, method):
	"""
	Hook handler for Seller Application approval/submit events.

	Evaluates contract rules with 'Registration' trigger point and creates
	contract instances for applicable rules.

	Args:
		doc: The Seller Application document being submitted/approved.
		method (str): The doc event method name (e.g., 'on_submit').
	"""
	try:
		evaluate_contract_rules("Registration", doc.doctype, doc)
	except Exception:
		frappe.log_error(
			title=_("Contract automation error for Seller Application {0}").format(doc.name),
			message=frappe.get_traceback()
		)


def handle_marketplace_order_submit(doc, method):
	"""
	Hook handler for Marketplace Order submit events.

	Evaluates contract rules with 'First Order' trigger point and creates
	contract instances for applicable buyer agreements.

	Args:
		doc: The Marketplace Order document being submitted.
		method (str): The doc event method name (e.g., 'on_submit').
	"""
	try:
		evaluate_contract_rules("First Order", doc.doctype, doc)
	except Exception:
		frappe.log_error(
			title=_("Contract automation error for Marketplace Order {0}").format(doc.name),
			message=frappe.get_traceback()
		)


def handle_seller_profile_created(doc, method):
	"""
	Hook handler for Seller Profile creation events.

	Evaluates contract rules with 'Registration' trigger point and creates
	contract instances for applicable seller agreements.

	Args:
		doc: The Seller Profile document being created.
		method (str): The doc event method name (e.g., 'after_insert').
	"""
	try:
		evaluate_contract_rules("Registration", doc.doctype, doc)
	except Exception:
		frappe.log_error(
			title=_("Contract automation error for Seller Profile {0}").format(doc.name),
			message=frappe.get_traceback()
		)


def evaluate_contract_rules(trigger_point, trigger_doctype, doc):
	"""
	Evaluate all active contract rules for a given trigger point and document.
	Creates contract instances for matching rules.

	Args:
		trigger_point (str): The trigger point (e.g., 'Registration', 'First Order').
		trigger_doctype (str): The DocType that triggered the evaluation.
		doc: The Frappe document that triggered the evaluation.

	Returns:
		list: List of created Contract Instance names.
	"""
	created_contracts = []

	# Get active rules for this trigger point
	rules = frappe.get_all(
		"Contract Rule",
		filters={
			"status": "Active",
			"trigger_point": trigger_point,
		},
		fields=["name"],
		order_by="priority asc"
	)

	for rule_entry in rules:
		rule = frappe.get_doc("Contract Rule", rule_entry.name)

		# Check if rule is currently active (date range check)
		if not rule.is_active():
			continue

		# Check trigger doctype filter if set
		if rule.trigger_doctype and rule.trigger_doctype != trigger_doctype:
			continue

		# Build context from document for condition evaluation
		context = _build_context_from_doc(doc)

		# Evaluate rule conditions and target filters
		if not rule.evaluate_context(context):
			continue

		# Determine party type and party from document
		party_type, party = _resolve_party(doc)
		if not party_type or not party:
			frappe.log_error(
				title=_("Cannot determine party for contract rule {0}").format(rule.name),
				message=_("Document {0} ({1}) does not have a resolvable party").format(
					doc.name, doc.doctype
				)
			)
			continue

		# Check for duplicate contracts
		if check_duplicate_contract(party_type, party, rule.contract_template):
			continue

		# Create contract instance
		contract_name = create_contract_instance(rule, doc, party_type, party)
		if contract_name:
			created_contracts.append(contract_name)

	return created_contracts


def create_contract_instance(rule, doc, party_type, party):
	"""
	Create a Contract Instance from a Contract Rule for a given party.

	Args:
		rule: The Contract Rule document (or name) triggering the creation.
		doc: The source document that triggered the contract creation.
		party_type (str): The party DocType (e.g., 'Seller Profile', 'User').
		party (str): The party document name.

	Returns:
		str: The name of the created Contract Instance, or None on failure.
	"""
	try:
		if isinstance(rule, str):
			rule = frappe.get_doc("Contract Rule", rule)

		template = rule.contract_template
		if not template:
			frappe.log_error(
				title=_("No template configured for Contract Rule {0}").format(rule.name),
				message=_("Contract Rule {0} does not have a contract template set").format(
					rule.name
				)
			)
			return None

		# Get the template document to verify it's published
		template_doc = frappe.get_doc("Contract Template", template)
		if template_doc.status != "Published":
			frappe.log_error(
				title=_("Contract template {0} is not published").format(template),
				message=_("Cannot create contract instance from unpublished template")
			)
			return None

		# Prepare context for template rendering
		context = _build_context_from_doc(doc)
		context["party_type"] = party_type
		context["party"] = party
		context["rule_name"] = rule.rule_name

		# Sanitize context before template rendering
		safe_context = sanitize_context(context)

		# Render template content with context (for logging/audit purposes)
		render_template(template_doc.content or "", safe_context)

		# Determine signature method
		signature_method = (
			template_doc.signature_method
			if template_doc.get("signature_method") and template_doc.signature_method != "Any"
			else None
		)

		# Create the contract instance
		contract_instance = frappe.new_doc("Contract Instance")
		contract_instance.template = template
		contract_instance.party_type = party_type
		contract_instance.party = party
		contract_instance.status = "Draft"

		if signature_method:
			contract_instance.signature_method = signature_method

		# Set tenant from rule or document
		if rule.get("tenant"):
			contract_instance.tenant = rule.tenant
		elif doc.get("tenant"):
			contract_instance.tenant = doc.tenant

		contract_instance.insert(ignore_permissions=True)

		# Record the trigger event on the rule
		rule.trigger(frappe.session.user, _build_context_from_doc(doc))

		frappe.logger().info(
			_("Contract Instance {0} created from Rule {1} for {2} {3}").format(
				contract_instance.name, rule.name, party_type, party
			)
		)

		return contract_instance.name

	except Exception:
		frappe.log_error(
			title=_("Error creating contract instance"),
			message=frappe.get_traceback()
		)
		return None


def render_template(template_content, context):
	"""
	Render a contract template using Jinja2 SandboxedEnvironment.

	Uses jinja2.Undefined to safely handle undefined variables.
	SandboxedEnvironment provides security against template injection
	by restricting access to unsafe attributes and functions.

	Args:
		template_content (str): The Jinja2 template content string.
		context (dict): The context variables for template rendering.

	Returns:
		str: The rendered template content.

	Raises:
		frappe.ValidationError: If template rendering fails due to security violation.
	"""
	from jinja2 import Undefined
	from jinja2.sandbox import SandboxedEnvironment, SecurityError

	if not template_content:
		return ""

	try:
		env = SandboxedEnvironment(undefined=Undefined)
		template = env.from_string(template_content)
		return template.render(**(context or {}))
	except SecurityError as e:
		frappe.throw(
			_("Template rendering blocked for security reasons: {0}").format(str(e)),
			frappe.ValidationError
		)
	except Exception as e:
		frappe.log_error(
			title=_("Contract template rendering error"),
			message=frappe.get_traceback()
		)
		frappe.throw(
			_("Error rendering contract template: {0}").format(str(e)),
			frappe.ValidationError
		)


def sanitize_context(context):
	"""
	Sanitize context dictionary values to prevent Jinja2 template injection.

	Strips ``{{``, ``}}``, ``{%``, ``%}`` from all string values in the context.

	Args:
		context (dict): The context dictionary to sanitize.

	Returns:
		dict: A new dictionary with sanitized values.
	"""
	if not context or not isinstance(context, dict):
		return context or {}

	sanitized = {}
	for key, value in context.items():
		if isinstance(value, str):
			sanitized[key] = _strip_template_syntax(value)
		elif isinstance(value, dict):
			sanitized[key] = sanitize_context(value)
		elif isinstance(value, list):
			sanitized[key] = [
				sanitize_context(item) if isinstance(item, dict)
				else _strip_template_syntax(item) if isinstance(item, str)
				else item
				for item in value
			]
		else:
			sanitized[key] = value

	return sanitized


def check_duplicate_contract(party_type, party, template):
	"""
	Check if an active (non-expired, non-rejected) contract already exists
	for the given party and template.

	Args:
		party_type (str): The party DocType (e.g., 'Seller Profile', 'User').
		party (str): The party document name.
		template (str): The Contract Template name.

	Returns:
		bool: True if a duplicate active contract exists, False otherwise.
	"""
	if not party_type or not party or not template:
		return False

	active_statuses = ["Draft", "Sent", "Pending Signature", "Signed"]

	existing = frappe.db.exists(
		"Contract Instance",
		{
			"party_type": party_type,
			"party": party,
			"template": template,
			"status": ["in", active_statuses],
		}
	)

	return bool(existing)


def expire_unsigned_contracts():
	"""
	Scheduled task to expire unsigned contracts that have passed their valid_until date.

	Runs daily via scheduler_events in hooks.py. Updates status from
	Draft/Sent/Pending Signature to Expired for contracts where valid_until
	has passed.
	"""
	expirable_statuses = ["Draft", "Sent", "Pending Signature"]

	expired_contracts = frappe.get_all(
		"Contract Instance",
		filters=[
			["status", "in", expirable_statuses],
			["valid_until", "<", now_datetime()],
			["valid_until", "is", "set"],
		],
		pluck="name"
	)

	count = 0
	for contract_name in expired_contracts:
		try:
			contract = frappe.get_doc("Contract Instance", contract_name)
			contract.status = "Expired"
			contract.save(ignore_permissions=True)
			count += 1
		except Exception:
			frappe.log_error(
				title=_("Error expiring contract {0}").format(contract_name),
				message=frappe.get_traceback()
			)

	if count:
		frappe.logger().info(
			_("{0} unsigned contracts expired").format(count)
		)

	frappe.db.commit()


def _build_context_from_doc(doc):
	"""
	Build a context dictionary from a Frappe document for rule evaluation
	and template rendering.

	Args:
		doc: The Frappe document to extract context from.

	Returns:
		dict: A context dictionary with document fields.
	"""
	context = {
		"doctype": doc.doctype,
		"name": doc.name,
		"owner": doc.owner,
	}

	# Add common fields if they exist
	common_fields = [
		"seller", "buyer", "user", "email", "status",
		"tenant", "company", "seller_name", "buyer_name",
		"full_name", "seller_level", "buyer_level",
		"user_type", "order_total", "total_orders",
		"total_revenue", "days_since_registration",
	]

	for field in common_fields:
		if hasattr(doc, field) and doc.get(field) is not None:
			context[field] = doc.get(field)

	return context


def _resolve_party(doc):
	"""
	Resolve the party type and party from a document.

	Args:
		doc: The Frappe document to resolve party from.

	Returns:
		tuple: (party_type, party) or (None, None) if unresolvable.
	"""
	# Try to resolve based on DocType
	if doc.doctype == "Seller Application":
		if doc.get("seller"):
			return "Seller Profile", doc.seller
		if doc.get("user"):
			return "User", doc.user
		return "User", doc.owner

	if doc.doctype == "Seller Profile":
		return "Seller Profile", doc.name

	if doc.doctype == "Marketplace Order":
		if doc.get("buyer"):
			return "User", doc.buyer
		if doc.get("customer"):
			return "Customer", doc.customer
		return "User", doc.owner

	# Generic resolution for other DocTypes
	if doc.get("seller"):
		return "Seller Profile", doc.seller
	if doc.get("buyer"):
		return "User", doc.buyer
	if doc.get("user"):
		return "User", doc.user

	return "User", doc.owner


def _strip_template_syntax(value):
	"""
	Strip Jinja2 template syntax characters from a string value.

	Args:
		value (str): The string value to sanitize.

	Returns:
		str: The sanitized string with template syntax removed.
	"""
	value = value.replace("{{", "")
	value = value.replace("}}", "")
	value = value.replace("{%", "")
	value = value.replace("%}", "")
	return value
