// Copyright (c) 2026, X-Sha
frappe.query_reports["Overtime Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_end() },
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: "Detail
Summary per Employee", default: "Detail" },
		{ fieldname: "kompensasi", label: __("Compensation"), fieldtype: "Select", options: "
PJK
Paid Overtime" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: "
Pending Supervisor
Pending HR
Approved
In Progress
Pending Confirmation
Completed
Rejected
Cancelled" },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
};
