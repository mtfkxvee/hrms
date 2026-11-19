// Copyright (c) 2026, X-Sha
// Approvals and Start/End Overtime are done in the HRMS app (/hrms).
// Here HR can review, create requests on behalf of employees, and process approvals.

const API = "hrms.xsha.lembur.";

frappe.ui.form.on("Overtime Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call(API + "get_info_persetujuan", { name: frm.doc.name }).then(({ message: info }) => {
			if (!info) return;
			const run = (method, args) =>
				frappe.call({ method: API + method, args: { name: frm.doc.name, ...args }, freeze: true }).then(() => frm.reload_doc());

			if (info.bisa_setujui_atasan) {
				frm.add_custom_button(__("Approve (Supervisor)"), () => {
					const d = new frappe.ui.Dialog({
						title: __("Approve Overtime"),
						fields: [
							{ fieldname: "kompensasi", label: __("Compensation"), fieldtype: "Select", options: "PJK
Paid Overtime", reqd: 1 },
							{ fieldname: "pjk_tanggal", label: __("PJK Date"), fieldtype: "Date", depends_on: "eval:doc.kompensasi=='PJK'" },
							{ fieldname: "pjk_jam_mulai", label: __("PJK From Time"), fieldtype: "Time", depends_on: "eval:doc.kompensasi=='PJK'" },
							{ fieldname: "pjk_jam_selesai", label: __("PJK To Time"), fieldtype: "Time", depends_on: "eval:doc.kompensasi=='PJK'" },
						],
						primary_action_label: __("Approve"),
						primary_action(values) {
							d.hide();
							run("setujui_atasan", values);
						},
					});
					d.show();
				}, __("Actions"));
			}
			if (info.bisa_setujui_hrd) {
				frm.add_custom_button(__("Approve (HR)"), () => run("setujui_hrd", {}), __("Actions"));
			}
			if (info.bisa_ubah_ke_berbayar) {
				frm.add_custom_button(__("Approve as Paid Overtime"), () => run("setujui_hrd", { ubah_ke_berbayar: 1 }), __("Actions"));
			}
			if (info.bisa_tolak) {
				frm.add_custom_button(__("Reject"), () => {
					frappe.prompt({ fieldname: "alasan", label: __("Rejection Reason"), fieldtype: "Small Text", reqd: 1 },
						(v) => run("tolak", { alasan: v.alasan }), __("Reject Overtime"));
				}, __("Actions"));
			}
			if (info.bisa_konfirmasi) {
				frm.add_custom_button(__("Confirm Hours"), () => {
					if (frm.doc.status === "In Progress") {
						frappe.prompt({ fieldname: "jam", label: __("Overtime End Time"), fieldtype: "Time", reqd: 1 },
							(v) => run("konfirmasi", { jam_selesai_manual: v.jam }), __("The employee has not ended the overtime"));
					} else {
						run("konfirmasi", {});
					}
				}, __("Actions"));
			}
			if (info.bisa_batalkan) {
				frm.add_custom_button(__("Cancel Request"), () =>
					frappe.confirm(__("Cancel this Overtime Request?"), () => run("batalkan", {})), __("Actions"));
			}
		});
	},
});
