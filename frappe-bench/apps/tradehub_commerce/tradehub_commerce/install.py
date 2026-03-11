import frappe


DEFAULT_PAYMENT_TERMS = [
	{
		"template_code": "ADVANCE_100",
		"template_name": "100% Advance Payment",
		"term_type": "Advance",
		"due_days": 0,
		"description": "Full payment required before order processing.",
	},
	{
		"template_code": "NET_15",
		"template_name": "Net 15 Days",
		"term_type": "Net Days",
		"due_days": 15,
		"description": "Payment due within 15 days of invoice date.",
	},
	{
		"template_code": "NET_30",
		"template_name": "Net 30 Days",
		"term_type": "Net Days",
		"due_days": 30,
		"description": "Payment due within 30 days of invoice date.",
	},
	{
		"template_code": "NET_60",
		"template_name": "Net 60 Days",
		"term_type": "Net Days",
		"due_days": 60,
		"description": "Payment due within 60 days of invoice date.",
	},
	{
		"template_code": "NET_90",
		"template_name": "Net 90 Days",
		"term_type": "Net Days",
		"due_days": 90,
		"description": "Payment due within 90 days of invoice date.",
	},
	{
		"template_code": "DEPOSIT_30",
		"template_name": "30% Deposit, Balance on Delivery",
		"term_type": "Deposit-Balance",
		"deposit_percentage": 30,
		"description": "30% deposit upfront, remaining 70% due on delivery.",
	},
	{
		"template_code": "DEPOSIT_50",
		"template_name": "50% Deposit, Balance on Delivery",
		"term_type": "Deposit-Balance",
		"deposit_percentage": 50,
		"description": "50% deposit upfront, remaining 50% due on delivery.",
	},
	{
		"template_code": "COD",
		"template_name": "Cash on Delivery",
		"term_type": "COD",
		"due_days": 0,
		"description": "Payment collected upon delivery of goods.",
	},
	{
		"template_code": "INSTALLMENT_3",
		"template_name": "3 Monthly Installments",
		"term_type": "Installment",
		"installment_count": 3,
		"installment_interval_days": 30,
		"description": "Payment split into 3 equal monthly installments.",
	},
	{
		"template_code": "INSTALLMENT_6",
		"template_name": "6 Monthly Installments",
		"term_type": "Installment",
		"installment_count": 6,
		"installment_interval_days": 30,
		"description": "Payment split into 6 equal monthly installments.",
	},
	{
		"template_code": "ESCROW",
		"template_name": "Escrow Payment",
		"term_type": "Escrow",
		"description": "Payment held in escrow until buyer confirms receipt.",
	},
	{
		"template_code": "LC_30",
		"template_name": "Letter of Credit - 30 Days",
		"term_type": "Letter of Credit",
		"due_days": 30,
		"description": "Payment via letter of credit with 30-day sight.",
	},
]


def create_default_payment_terms():
	"""Create default Marketplace Payment Terms Template records."""
	for term_data in DEFAULT_PAYMENT_TERMS:
		doc = frappe.get_doc({
			"doctype": "Marketplace Payment Terms Template",
			"is_active": 1,
			**term_data,
		})
		doc.insert(ignore_if_duplicate=True)

	frappe.db.commit()
