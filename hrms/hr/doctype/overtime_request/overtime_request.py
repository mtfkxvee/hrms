# Copyright (c) 2026, X-Sha
# Rules live in hrms/xsha/lembur.py

from frappe.model.document import Document

from hrms.xsha import lembur


class OvertimeRequest(Document):
	def validate(self):
		lembur.validate(self)

	def after_insert(self):
		lembur.after_insert(self)
