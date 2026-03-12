# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MappingTemplateField(Document):
    """
    Mapping Template Field - Child table for column mapping definitions.

    Stores individual field mapping entries that map source CSV/Excel columns
    to target DocType fields, including match confidence and strategy information.
    """
    pass
