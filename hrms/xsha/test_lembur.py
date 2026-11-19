# Jalankan: bench --site <site> run-tests --module hrms.xsha.test_lembur

import datetime

from frappe.tests.utils import FrappeTestCase

from hrms.xsha.lembur import bulatkan_jam, durasi_jam, hitung_jam_lembur, rentang_bertumpuk, rentang_rencana


class TestHitungLembur(FrappeTestCase):
	def test_pembulatan_45_menit(self):
		self.assertEqual(bulatkan_jam(44), 0)
		self.assertEqual(bulatkan_jam(45), 1)
		self.assertEqual(bulatkan_jam(104), 1)  # 1 jam 44 menit
		self.assertEqual(bulatkan_jam(110), 2)  # 1 jam 50 menit

	def test_batas_harian_dan_spl(self):
		self.assertEqual(hitung_jam_lembur(240, 3), 3)  # maks 3 jam per hari
		self.assertEqual(hitung_jam_lembur(170, 2), 2)  # tidak melebihi SPL
		self.assertEqual(hitung_jam_lembur(120, 1.5), 1)  # SPL 1,5 jam diakui 1 jam
		self.assertEqual(hitung_jam_lembur(40, 2), 0)

	def test_lewat_tengah_malam(self):
		self.assertEqual(durasi_jam("23:00:00", "01:00:00"), 2.0)
		mulai, selesai = rentang_rencana("2026-11-20", "23:00", "01:00")
		self.assertEqual(selesai.date(), datetime.date(2026, 11, 21))

	def test_bentrok(self):
		d = lambda h: datetime.datetime(2026, 11, 20, h)
		self.assertTrue(rentang_bertumpuk(d(17), d(19), d(18), d(20)))
		self.assertFalse(rentang_bertumpuk(d(17), d(19), d(19), d(21)))
