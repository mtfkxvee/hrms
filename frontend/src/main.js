// X-Sha: harus paling awal, supaya semua request API ikut mencatat selisih jam server
import "./offline/jam"
import { createApp } from "vue"
import App from "./App.vue"
import router from "./router"
import { initSocket } from "./socket"

import {
	Button,
	Input,
	setConfig,
	frappeRequest,
	resourcesPlugin,
	FormControl,
} from "frappe-ui"
import { translationsPlugin } from "./plugins/translationsPlugin.js"
import EmptyState from "@/components/EmptyState.vue"

import { IonicVue } from "@ionic/vue"

import { session } from "@/data/session"
import { userResource } from "@/data/user"
import { employeeResource } from "@/data/employee"

import dayjs from "@/utils/dayjs"
import getIonicConfig from "@/utils/ionicConfig"

import FrappePushNotification from "../public/frappe-push-notification"
import { mulaiSinkronOtomatis } from "@/offline/antrean"

/* Core CSS required for Ionic components to work properly */
import "@ionic/vue/css/core.css"

/* Theme variables */
import "./theme/variables.css"

import "./main.css"

const app = createApp(App)
const socket = initSocket()

setConfig("resourceFetcher", frappeRequest)
app.use(resourcesPlugin)
app.use(translationsPlugin)

app.component("Button", Button)
app.component("Input", Input)
app.component("FormControl", FormControl)
app.component("EmptyState", EmptyState)

app.use(router)
app.use(IonicVue, getIonicConfig())

if (session?.isLoggedIn && !employeeResource?.data) {
	employeeResource.reload()
}

app.provide("$session", session)
app.provide("$user", userResource)
app.provide("$employee", employeeResource)
app.provide("$socket", socket)
app.provide("$dayjs", dayjs)

const registerServiceWorker = async () => {
	window.frappePushNotification = new FrappePushNotification("hrms")

	if ("serviceWorker" in navigator) {
		// X-Sha: sw.js disajikan lewat endpoint (header Service-Worker-Allowed) supaya scope-nya
		// /hrms dan halaman app tetap bisa dibuka saat server down. Lihat hrms/xsha/offline.py.
		let serviceWorkerURL = import.meta.env.DEV
			? "/assets/hrms/frontend/sw.js"
			: "/api/method/hrms.xsha.offline.service_worker"
		const registerOptions = import.meta.env.DEV ? { type: "classic" } : { type: "classic", scope: "/hrms" }
		let config = ""

		try {
			config = await window.frappePushNotification.fetchWebConfig()
			serviceWorkerURL = `${serviceWorkerURL}?config=${encodeURIComponent(
				JSON.stringify(config)
			)}`
		} catch (err) {
			console.error("Failed to fetch FCM config", err)
		}

		navigator.serviceWorker
			.register(serviceWorkerURL, registerOptions)
			.then((registration) => {
				if (config) {
					window.frappePushNotification.initialize(registration).then(() => {
						console.log("Frappe Push Notification initialized")
					})
				}
			})
			.catch((err) => {
				console.error("Failed to register service worker", err)
			})
	} else {
		console.error("Service worker not enabled/supported by the browser")
	}
}

router.isReady().then(async () => {
	if (import.meta.env.DEV) {
		await frappeRequest({
			url: "/api/method/hrms.www.hrms.get_context_for_dev",
		}).then(async (values) => {
			if (!window.frappe) window.frappe = {}
			window.frappe.boot = values
		})
	}

	await translationsPlugin.isReady();
	registerServiceWorker()
	app.mount("#app")
})

// X-Sha mode offline: saat server down, request bisa gagal atau menggantung lama (Cloudflare
// 522 baru menjawab setelah belasan detik). Pakai data cache terakhir supaya app tetap terbuka.
const BATAS_TUNGGU_SERVER_MS = 8000
// setelah sekali gagal, pindah halaman berikutnya tidak perlu menunggu lama lagi
const BATAS_TUNGGU_SAAT_DOWN_MS = 2000
let serverTerakhirGagal = false
const batasTunggu = () => (serverTerakhirGagal ? BATAS_TUNGGU_SAAT_DOWN_MS : BATAS_TUNGGU_SERVER_MS)

function denganBatasWaktu(promise, ms) {
	let timer
	const batas = new Promise((_, reject) => {
		timer = setTimeout(() => reject(new Error("timeout")), ms)
	})
	return Promise.race([Promise.resolve(promise), batas]).finally(() => clearTimeout(timer))
}

function errorLogin(error) {
	const status = error?.response?.status
	return (
		status === 401 ||
		status === 403 ||
		["AuthenticationError", "PermissionError", "SessionExpired"].includes(error?.exc_type)
	)
}

// data cache (IndexedDB) dimuat async oleh frappe-ui; tunggu sebentar
async function tungguData(resource, ms = 2000) {
	const sampai = Date.now() + ms
	while (!resource.data && Date.now() < sampai) {
		await new Promise((r) => setTimeout(r, 50))
	}
	return Boolean(resource.data)
}

router.beforeEach(async (to, _, next) => {
	let isLoggedIn = session.isLoggedIn

	try {
		if (isLoggedIn) {
			await denganBatasWaktu(userResource.reload(), batasTunggu())
			serverTerakhirGagal = false
		}
	} catch (error) {
		// server tidak bisa dihubungi: tetap masuk dengan data user terakhir
		serverTerakhirGagal = !errorLogin(error)
		isLoggedIn = serverTerakhirGagal && (await tungguData(userResource))
	}

	if (!isLoggedIn) {
		// password reset page is outside the PWA scope
		if (to.path === "/update-password") {
			return next(false)
		} else if (to.name !== "Login") {
			next({ name: "Login" })
		}
	}

	if (isLoggedIn) mulaiSinkronOtomatis()

	if (isLoggedIn && to.name !== "InvalidEmployee") {
		try {
			await denganBatasWaktu(employeeResource.promise, batasTunggu())
		} catch (error) {
			await tungguData(employeeResource)
		}
		// user should be an employee to access the app
		// since all views are employee specific
		if (
			!employeeResource?.data ||
			employeeResource?.data?.user_id !== userResource.data.name
		) {
			next({ name: "InvalidEmployee" })
		} else if (to.name === "Login") {
			next({ name: "Home" })
		} else {
			next()
		}
	} else {
		next()
	}
})
