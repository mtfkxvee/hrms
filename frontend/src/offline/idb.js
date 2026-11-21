// X-Sha: penyimpanan antrean offline di IndexedDB HP (tetap ada walau app ditutup).
const DB_NAME = "xpeople-offline"
const STORE = "antrean"

let dbPromise = null

function buka() {
	if (!dbPromise) {
		dbPromise = new Promise((resolve, reject) => {
			const req = indexedDB.open(DB_NAME, 1)
			req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" })
			req.onsuccess = () => resolve(req.result)
			req.onerror = () => {
				dbPromise = null
				reject(req.error)
			}
		})
	}
	return dbPromise
}

async function jalankan(mode, aksi) {
	const db = await buka()
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE, mode)
		const req = aksi(tx.objectStore(STORE))
		tx.oncomplete = () => resolve(req?.result)
		tx.onerror = () => reject(tx.error)
		tx.onabort = () => reject(tx.error)
	})
}

export const semuaItem = () => jalankan("readonly", (store) => store.getAll())
// item disalin dulu: proxy reaktif Vue tidak bisa disimpan ke IndexedDB
export const simpanItem = (item) => jalankan("readwrite", (store) => store.put(JSON.parse(JSON.stringify(item))))
export const hapusItem = (id) => jalankan("readwrite", (store) => store.delete(id))
