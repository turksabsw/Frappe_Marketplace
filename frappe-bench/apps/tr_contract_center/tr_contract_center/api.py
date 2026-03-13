# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
TR Contract Center API Endpoints

REST API for contract management with digital/wet signature support.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, add_days, cint


def _api_response(success=True, data=None, message=None, errors=None):
    """Standard API response format."""
    return {
        "success": success,
        "data": data or {},
        "message": message or "",
        "errors": errors or []
    }


@frappe.whitelist(allow_guest=False)
def create_instance(template, party_type, party, signature_method=None, expiry_days=None, seller_name=None):
    """
    Create a new contract instance from a template.

    If the template has dynamic_rules_enabled, the contract content is compiled
    via the rule engine using seller attributes. Otherwise, static template
    content is used (backward compatibility).

    Args:
        template: Template name or code
        party_type: DocType of the party (e.g., 'User', 'Customer')
        party: Name/ID of the party
        signature_method: 'Digital' or 'Wet' (optional)
        expiry_days: Days until signature expires (optional)
        seller_name: Seller Profile name for dynamic rule compilation (optional)

    Returns:
        dict: API response with contract instance details
    """
    try:
        # Resolve template by code if needed
        template_name = template
        if not frappe.db.exists("Contract Template", template):
            template_name = frappe.db.get_value(
                "Contract Template",
                {"template_code": template.upper(), "status": "Published"},
                "name"
            )

        if not template_name:
            return _api_response(False, message=_("Template not found or not published: {0}").format(template))

        # Get template details
        template_doc = frappe.get_doc("Contract Template", template_name)

        # Check if dynamic rules are enabled on this template
        dynamic_rules_enabled = cint(getattr(template_doc, "dynamic_rules_enabled", 0))
        compiled_output_name = None

        if dynamic_rules_enabled and seller_name:
            # Dynamic compilation via rule engine
            from tr_contract_center.rule_engine import compile_contract

            compilation_result = compile_contract(template_name, seller_name)
            compiled_content = compilation_result.get("compiled_content", "")
            compiled_content_hash = compilation_result.get("content_hash")
            compiled_output_name = compilation_result.get("compiled_output_name")
        else:
            # Static content (backward compatibility)
            compiled_content = None
            compiled_content_hash = None

        # Create instance
        instance_data = {
            "doctype": "Contract Instance",
            "template": template_name,
            "party_type": party_type,
            "party": party,
            "signature_method": signature_method or (
                "Digital" if template_doc.signature_method in ["Any", "Digital Only"] else "Wet"
            ),
            "status": "Draft"
        }

        # If dynamic compilation was used, pre-set snapshot fields so that
        # the controller's snapshot_template() uses compiled content instead
        # of static template content
        if compiled_content:
            instance_data["template_version_snapshot"] = template_doc.version
            instance_data["template_content_snapshot"] = compiled_content
            instance_data["content_hash_snapshot"] = compiled_content_hash

        # Link compiled output reference if dynamic compilation was used
        if compiled_output_name:
            instance_data["compiled_output"] = compiled_output_name

        doc = frappe.get_doc(instance_data)

        # Set validity period
        if expiry_days:
            doc.valid_until = add_days(now_datetime(), int(expiry_days))

        doc.insert()
        frappe.db.commit()

        response_data = {
            "contract_instance": doc.name,
            "title": doc.title,
            "status": doc.status,
            "template": doc.template,
            "template_version": doc.template_version_snapshot,
            "valid_until": str(doc.valid_until) if doc.valid_until else None
        }

        # Include dynamic compilation info if applicable
        if compiled_output_name:
            response_data["compiled_output"] = compiled_output_name
            response_data["dynamic_compilation"] = True

        return _api_response(
            True,
            data=response_data,
            message=_("Contract instance created successfully")
        )

    except Exception as e:
        frappe.log_error(f"create_instance error: {str(e)}", "Contract Center API")
        return _api_response(False, message=str(e), errors=[str(e)])


@frappe.whitelist(allow_guest=False)
def sign_wet(contract_instance, signed_pdf, signer_name=None):
    """
    Complete wet signature by uploading signed PDF.

    Args:
        contract_instance: Name of the Contract Instance
        signed_pdf: File URL of the signed PDF
        signer_name: Name of the signer (optional)

    Returns:
        dict: API response
    """
    try:
        doc = frappe.get_doc("Contract Instance", contract_instance)

        if doc.status not in ["Sent", "Pending Signature"]:
            return _api_response(
                False,
                message=_("Contract is not awaiting signature. Status: {0}").format(doc.status)
            )

        if doc.signature_method != "Wet":
            return _api_response(
                False,
                message=_("This contract requires digital signature, not wet signature")
            )

        if not signed_pdf:
            return _api_response(False, message=_("Signed PDF is required for wet signature"))

        doc.signed_pdf = signed_pdf
        doc.signed_at = now_datetime()
        doc.signed_by = signer_name or frappe.session.user
        doc.status = "Signed"
        doc.save()
        frappe.db.commit()

        return _api_response(
            True,
            data={
                "contract_instance": doc.name,
                "status": "Signed",
                "signed_at": str(doc.signed_at)
            },
            message=_("Contract signed successfully with wet signature")
        )

    except Exception as e:
        frappe.log_error(f"sign_wet error: {str(e)}", "Contract Center API")
        return _api_response(False, message=str(e), errors=[str(e)])


@frappe.whitelist(allow_guest=False)
def init_digital_sign(contract_instance, provider=None, signer_info=None):
    """
    Initialize digital signature process.

    Args:
        contract_instance: Name of the Contract Instance
        provider: ESign Provider name (optional, uses default if not specified)
        signer_info: Dict with signer details (name, email, phone, tckn)

    Returns:
        dict: API response with signing URL
    """
    try:
        import json
        if isinstance(signer_info, str):
            signer_info = json.loads(signer_info)

        doc = frappe.get_doc("Contract Instance", contract_instance)

        if doc.status not in ["Draft", "Sent"]:
            return _api_response(
                False,
                message=_("Contract is not ready for signature. Status: {0}").format(doc.status)
            )

        # Get provider
        if not provider:
            provider = frappe.db.get_value(
                "ESign Provider",
                {"enabled": 1, "is_default": 1},
                "name"
            )

        if not provider:
            return _api_response(False, message=_("No e-sign provider configured"))

        # Get adapter
        from tr_contract_center.esign import get_provider_adapter
        adapter = get_provider_adapter(provider)

        if not adapter:
            return _api_response(False, message=_("Failed to initialize e-sign provider"))

        # Default signer info
        if not signer_info:
            signer_info = {
                "name": doc.party_name,
                "party_type": doc.party_type,
                "party": doc.party
            }

        # Create signing request
        result = adapter.create_signing_request(
            doc.name,
            doc.template_content_snapshot,
            signer_info
        )

        if not result.get("success"):
            return _api_response(False, message=result.get("error", "Unknown error"))

        # Update contract
        doc.esign_provider = provider
        doc.esign_transaction = result.get("transaction_name")
        doc.status = "Pending Signature"
        doc.signature_method = "Digital"
        doc.save()
        frappe.db.commit()

        return _api_response(
            True,
            data={
                "contract_instance": doc.name,
                "status": "Pending Signature",
                "signing_url": result.get("signing_url"),
                "external_id": result.get("external_id"),
                "expires_at": str(result.get("expires_at")) if result.get("expires_at") else None
            },
            message=_("Digital signature initiated successfully")
        )

    except Exception as e:
        frappe.log_error(f"init_digital_sign error: {str(e)}", "Contract Center API")
        return _api_response(False, message=str(e), errors=[str(e)])


@frappe.whitelist(allow_guest=True)
def esign_callback():
    """
    Webhook endpoint for e-sign provider callbacks.

    Expects POST with JSON payload from provider.
    """
    try:
        import json

        # Get payload
        payload = frappe.local.form_dict
        if isinstance(payload, str):
            payload = json.loads(payload)

        # Get signature header for validation
        signature = frappe.get_request_header("X-Signature") or \
                   frappe.get_request_header("X-Webhook-Signature")

        # Find transaction by external_id
        external_id = payload.get("transaction_id") or payload.get("external_id")
        if not external_id:
            return _api_response(False, message=_("Missing transaction ID in callback"))

        transaction = frappe.db.get_value(
            "ESign Transaction",
            {"external_id": external_id},
            ["name", "provider", "contract_instance"],
            as_dict=True
        )

        if not transaction:
            return _api_response(False, message=_("Transaction not found: {0}").format(external_id))

        # Get adapter and validate callback
        from tr_contract_center.esign import get_provider_adapter
        adapter = get_provider_adapter(transaction.provider)

        if adapter and signature:
            if not adapter.validate_callback(payload, signature):
                frappe.log_error(
                    f"Invalid callback signature for {external_id}",
                    "Contract Center Callback"
                )
                return _api_response(False, message=_("Invalid callback signature"))

        # Process callback
        callback_data = adapter.process_callback(payload) if adapter else payload

        # Update transaction
        trans_doc = frappe.get_doc("ESign Transaction", transaction.name)
        trans_doc.status = callback_data.get("status", trans_doc.status)

        if callback_data.get("signed_at"):
            trans_doc.signed_at = callback_data.get("signed_at")

        trans_doc.save(ignore_permissions=True)
        frappe.db.commit()

        return _api_response(
            True,
            data={"transaction": transaction.name, "status": trans_doc.status},
            message=_("Callback processed successfully")
        )

    except Exception as e:
        frappe.log_error(f"esign_callback error: {str(e)}", "Contract Center API")
        return _api_response(False, message=str(e), errors=[str(e)])


@frappe.whitelist(allow_guest=False)
def get_contracts(party_type=None, party=None, template=None, status=None, limit=20, offset=0):
    """
    Get contract instances with filtering.

    Args:
        party_type: Filter by party type
        party: Filter by party
        template: Filter by template
        status: Filter by status
        limit: Number of results (default 20)
        offset: Pagination offset

    Returns:
        dict: API response with list of contracts
    """
    try:
        filters = {}

        if party_type:
            filters["party_type"] = party_type
        if party:
            filters["party"] = party
        if template:
            filters["template"] = template
        if status:
            filters["status"] = status

        contracts = frappe.get_all(
            "Contract Instance",
            filters=filters,
            fields=[
                "name", "title", "template", "party_type", "party", "party_name",
                "status", "signature_method", "created_at", "sent_at",
                "signed_at", "expiry_date", "valid_until"
            ],
            order_by="created_at desc",
            limit_page_length=int(limit),
            limit_start=int(offset)
        )

        total = frappe.db.count("Contract Instance", filters)

        return _api_response(
            True,
            data={
                "contracts": contracts,
                "total": total,
                "limit": int(limit),
                "offset": int(offset)
            },
            message=_("Found {0} contract(s)").format(len(contracts))
        )

    except Exception as e:
        frappe.log_error(f"get_contracts error: {str(e)}", "Contract Center API")
        return _api_response(False, message=str(e), errors=[str(e)])


@frappe.whitelist(allow_guest=False)
def get_contract_detail(contract_instance):
    """
    Get detailed contract information including template content.

    Args:
        contract_instance: Name of the Contract Instance

    Returns:
        dict: API response with contract details
    """
    try:
        doc = frappe.get_doc("Contract Instance", contract_instance)

        data = {
            "name": doc.name,
            "title": doc.title,
            "template": doc.template,
            "template_version": doc.template_version_snapshot,
            "content": doc.template_content_snapshot,
            "content_hash": doc.content_hash_snapshot,
            "party_type": doc.party_type,
            "party": doc.party,
            "party_name": doc.party_name,
            "status": doc.status,
            "signature_method": doc.signature_method,
            "created_at": str(doc.created_at) if doc.created_at else None,
            "sent_at": str(doc.sent_at) if doc.sent_at else None,
            "signed_at": str(doc.signed_at) if doc.signed_at else None,
            "signed_by": doc.signed_by,
            "signed_pdf": doc.signed_pdf,
            "expiry_date": str(doc.expiry_date) if doc.expiry_date else None,
            "valid_until": str(doc.valid_until) if doc.valid_until else None
        }

        return _api_response(True, data=data, message=_("Contract details retrieved"))

    except Exception as e:
        frappe.log_error(f"get_contract_detail error: {str(e)}", "Contract Center API")
        return _api_response(False, message=str(e), errors=[str(e)])


@frappe.whitelist(allow_guest=False)
def preview_compiled_contract(template_name, seller_name):
    """
    Preview a dynamically compiled contract for admin review.

    Compiles the contract template using the rule engine for the specified
    seller without creating a Contract Instance. Useful for administrators
    to preview what a seller's contract would look like before sending.

    Args:
        template_name: Name of the Contract Template
        seller_name: Name of the Seller Profile

    Returns:
        dict: API response with compiled content, compilation log, and rule stats
    """
    try:
        # Validate inputs
        if not frappe.db.exists("Contract Template", template_name):
            return _api_response(
                False,
                message=_("Contract Template '{0}' not found").format(template_name)
            )

        if not frappe.db.exists("Seller Profile", seller_name):
            return _api_response(
                False,
                message=_("Seller Profile '{0}' not found").format(seller_name)
            )

        # Check if dynamic rules are enabled
        template_doc = frappe.get_doc("Contract Template", template_name)
        dynamic_rules_enabled = cint(getattr(template_doc, "dynamic_rules_enabled", 0))

        if not dynamic_rules_enabled:
            # Return static content with a note
            return _api_response(
                True,
                data={
                    "template_name": template_name,
                    "seller_name": seller_name,
                    "compiled_content": template_doc.content or "",
                    "dynamic_rules_enabled": False,
                    "compilation_log": [],
                    "rules_applied": 0,
                    "rules_skipped": 0,
                    "content_hash": template_doc.content_hash
                },
                message=_("Dynamic rules not enabled on this template. Showing static content.")
            )

        # Compile contract via rule engine
        from tr_contract_center.rule_engine import compile_contract

        result = compile_contract(template_name, seller_name)

        return _api_response(
            True,
            data={
                "template_name": template_name,
                "seller_name": seller_name,
                "compiled_content": result.get("compiled_content", ""),
                "dynamic_rules_enabled": True,
                "compilation_log": result.get("compilation_log", []),
                "rules_applied": result.get("rules_applied", 0),
                "rules_skipped": result.get("rules_skipped", 0),
                "content_hash": result.get("content_hash"),
                "compiled_output_name": result.get("compiled_output_name")
            },
            message=_("Contract compiled successfully for preview")
        )

    except Exception as e:
        frappe.log_error(f"preview_compiled_contract error: {str(e)}", "Contract Center API")
        return _api_response(False, message=str(e), errors=[str(e)])
