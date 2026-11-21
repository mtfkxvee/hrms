import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { VitePWA } from "vite-plugin-pwa"
import frappeui from "frappe-ui/vite"

import path from "path"
import fs from "fs"

export default defineConfig({
	server: {
		port: 8080,
		proxy: getProxyOptions(),
		allowedHosts: true,
	},
	plugins: [
		vue(),
		frappeui(),
		VitePWA({
			// nama manifest diberi versi: Cache-Control aset 1 tahun, URL baru = langsung terbaca semua HP
			manifestFilename: "x-people-w1.webmanifest",
			registerType: "autoUpdate",
			strategies: "injectManifest",
			injectRegister: null,
			devOptions: {
				enabled: true,
			},
			injectManifest: {
				// X-Sha mode offline: semua aset app ikut di-precache (termasuk font & ikon),
				// dan chunk besar (frappe-ui) tidak terlewat oleh batas default 2 MB
				globPatterns: ["**/*.{js,css,html,woff,woff2,svg,png}"],
				maximumFileSizeToCacheInBytes: 8 * 1024 * 1024,
			},
			manifest: {
				display: "standalone",
				name: "X-PEOPLE",
				short_name: "X-PEOPLE",
				start_url: "/hrms",
				description: "Aplikasi HR karyawan X-Sha: absensi, cuti, lembur, dan pengajuan",
				theme_color: "#ffffff",
				background_color: "#ffffff",
				icons: [
					{
						src: "/assets/hrms/manifest/xp-w1-icon-192.png",
						sizes: "192x192",
						type: "image/png",
						purpose: "any",
					},
					{
						src: "/assets/hrms/manifest/xp-w1-icon-192.png",
						sizes: "192x192",
						type: "image/png",
						purpose: "maskable",
					},
					{
						src: "/assets/hrms/manifest/xp-w1-icon-512.png",
						sizes: "512x512",
						type: "image/png",
						purpose: "any",
					},
					{
						src: "/assets/hrms/manifest/xp-w1-icon-512.png",
						sizes: "512x512",
						type: "image/png",
						purpose: "maskable",
					},
				],
			},
		}),
	],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
	},
	build: {
		outDir: "../hrms/public/frontend",
		emptyOutDir: true,
		target: "es2015",
		commonjsOptions: {
			include: [/tailwind.config.js/, /node_modules/],
		},
		sourcemap: true,
		rollupOptions: {
			output: {
				manualChunks: {
					"frappe-ui": ["frappe-ui"],
				},
			},
		},
	},
	optimizeDeps: {
		include: [
			"frappe-ui > feather-icons",
			"showdown",
			"tailwind.config.js",
			"engine.io-client",
		],
	},
})

function getProxyOptions() {
	const config = getCommonSiteConfig()
	const webserver_port = config ? config.webserver_port : 8000
	if (!config) {
		console.log("No common_site_config.json found, using default port 8000")
	}
	return {
		"^/(app|login|api|assets|files|private)": {
			target: `http://127.0.0.1:${webserver_port}`,
			ws: true,
			router: function (req) {
				const site_name = req.headers.host.split(":")[0]
				console.log(`Proxying ${req.url} to ${site_name}:${webserver_port}`)
				return `http://${site_name}:${webserver_port}`
			},
		},
	}
}

function getCommonSiteConfig() {
	let currentDir = path.resolve(".")
	// traverse up till we find frappe-bench with sites directory
	while (currentDir !== "/") {
		if (
			fs.existsSync(path.join(currentDir, "sites")) &&
			fs.existsSync(path.join(currentDir, "apps"))
		) {
			let configPath = path.join(currentDir, "sites", "common_site_config.json")
			if (fs.existsSync(configPath)) {
				return JSON.parse(fs.readFileSync(configPath))
			}
			return null
		}
		currentDir = path.resolve(currentDir, "..")
	}
	return null
}
