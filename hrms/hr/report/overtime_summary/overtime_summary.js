// Copyright (c) 2026, X-Sha
frappe.query_reports["Overtime Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_end() },
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: "Detail\nSummary per Employee", default: "Detail" },
		{ fieldname: "kompensasi", label: __("Compensation"), fieldtype: "Select", options: "\nPJK\nPaid Overtime" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nPending Supervisor\nPending HR\nApproved\nIn Progress\nPending Confirmation\nCompleted\nRejected\nCancelled",
		},
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
};
