// X-Sha: Overtime Request (lembur). Nama route mengikuti pola `${doctype tanpa spasi}DetailView`
// yang dipakai FormView setelah dokumen tersimpan.
const routes = [
	{
		name: "OvertimeRequestListView",
		path: "/overtime-requests",
		component: () => import("@/views/lembur/List.vue"),
	},
	{
		name: "OvertimeRequestFormView",
		path: "/overtime-requests/new",
		component: () => import("@/views/lembur/Form.vue"),
	},
	{
		name: "OvertimeRequestDetailView",
		path: "/overtime-requests/:id",
		props: true,
		component: () => import("@/views/lembur/Detail.vue"),
	},
]

export default routes
