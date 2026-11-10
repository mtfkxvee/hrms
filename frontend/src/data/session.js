import { computed, reactive } from "vue"
import { createResource, call } from "frappe-ui"
import { userResource } from "./user"
import { employeeResource } from "./employee"
import router from "@/router"

export function sessionUser() {
	let cookies = new URLSearchParams(document.cookie.split("; ").join("&"))
	let _sessionUser = cookies.get("user_id")
	if (_sessionUser === "Guest") {
		_sessionUser = null
	}
	return _sessionUser
}

// A01: setelah login tanpa reload halaman, window.csrf_token masih token sesi tamu
// sehingga POST pertama (mis. check-in) ditolak "Invalid Request". Ambil token sesi
// baru lewat GET (GET tidak diperiksa CSRF) sebelum request lain dikirim.
async function refreshCsrfToken() {
	try {
		const res = await fetch("/api/method/hrms.api.get_csrf.get_csrf_token", {
			credentials: "same-origin",
		})
		const data = await res.json()
		if (data.message) {
			window.csrf_token = data.message
			return
		}
	} catch (e) {
		// jatuh ke reload di bawah
	}
	window.location.reload()
}

async function handleLogin(response) {
	if (response.message === "Logged In") {
		await refreshCsrfToken()
		userResource.reload()
		employeeResource.reload()

		session.user = sessionUser()
		router.replace({ path: "/" })
	}
}

export const session = reactive({
	login: async (email, password) => {
		const response = await call("login", { usr: email, pwd: password })
		await handleLogin(response)
		return response
	},
	otp: async (tmp_id, otp) => {
		const response = await call("login", { tmp_id, otp })
		await handleLogin(response)
		return response
	},
	logout: createResource({
		url: "logout",
		onSuccess() {
			userResource.reset()
			employeeResource.reset()

			session.user = sessionUser()
			router.replace({ name: "Login" })
			window.location.reload()
		},
	}),
	user: sessionUser(),
	isLoggedIn: computed(() => !!session.user),
})
