// X-SHA: persetujuan 2 lapis (Atasan -> HRD) untuk cuti/izin, ganti shift, dan koreksi absen di desk.
// Aturannya di server (hrms/xsha/approval.py); tombol di sini hanya memanggil API yang sama
// dengan aplikasi X-PEOPLE dan link WA.

["Leave Application", "Shift Request", "Attendance Request"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.is_new() || frm.doc.docstatus !== 0) return;

			frappe
				.call("hrms.xsha.approval.get_approval_actions", { doctype: doctype, name: frm.doc.name })
				.then(({ message: info }) => {
					if (!info || !info.stage) return;

					const waiting =
						info.stage === "hrd"
							? __("Waiting for HR approval")
							: __("Waiting for supervisor approval ({0})", [info.approver || "-"]);
					frm.dashboard.add_comment(waiting, "blue", true);

					const run = (method) =>
						frappe
							.call({
								method: "hrms.xsha.approval." + method,
								args: { doctype: doctype, name: frm.doc.name },
								freeze: true,
							})
							.then(() => frm.reload_doc());

					if (info.can_approve) {
						const label = info.stage === "hrd" ? __("Approve (HR)") : __("Approve (Supervisor)");
						frm.add_custom_button(
							label,
							() => frappe.confirm(__("Approve this request?"), () => run("approve")),
							__("Actions")
						);
					}
					if (info.can_reject) {
						frm.add_custom_button(
							__("Reject"),
							() => frappe.confirm(__("Reject this request?"), () => run("reject")),
							__("Actions")
						);
					}
				});
		},
	});
});
