# tests/test_phase1.py — Task1 Phase 1 後端單元測試
#
# 範圍：
#   1. admin.py gws 層錯誤語意（空資料=合法、API/CLI 錯誤=拋 GwsError，不再靜默吞掉）
#   2. admin.py 常數拆分（LAITEN_SHEET_ID / BACK_SHEET_ID 雙常數，GOOGLE_SHEETS_ID 不變值）
#   3. _parse_laiten 純函式（品牌/產品列解析，products.js 資料結構來源）
#   4. migrate_sheets.py 防護常數（受保護 tab 絕不在遷移清單、防呆函式）
#
# 全程不碰外部資源：subprocess / gspread 一律 mock。
# 執行：python -m unittest tests.test_phase1 -v

import json
import os
import subprocess
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "back"))
sys.path.insert(0, PROJECT_ROOT)

import admin  # noqa: E402  (import 即設定 GOOGLE_SHEETS_ID)
import migrate_sheets  # noqa: E402

BACK_ID = "1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E"
FRONT_ID = "1xtuKyod3lOQUmp_D10AhDDGSD4bVxG3TmZudO2S9AMo"


def _cp(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["gws"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestConstants(unittest.TestCase):
    """常數拆分：兩用途常數明確分離，合併後皆指後台 Sheet"""

    def test_two_named_constants_exist(self):
        self.assertEqual(admin.LAITEN_SHEET_ID, BACK_ID)
        self.assertEqual(admin.BACK_SHEET_ID, BACK_ID)

    def test_google_sheets_id_env_points_to_back_sheet(self):
        # db.py 的生命線：值不可被拆壞（impact.md Backend 注意 1）
        self.assertEqual(os.environ.get("GOOGLE_SHEETS_ID"), BACK_ID)

    def test_legacy_single_constant_removed(self):
        self.assertFalse(hasattr(admin, "SHEET_ID"),
                         "單一 SHEET_ID 應已拆分移除（根因修復）")


class TestGwsLayer(unittest.TestCase):
    """gws 層：空資料合法、錯誤可見（GwsError），兩種語意可區分"""

    def setUp(self):
        self._orig = admin._gws

    def tearDown(self):
        admin._gws = self._orig

    def test_read_success_returns_values(self):
        admin._gws = lambda *a: _cp(
            'Using keyring backend: keyring\n'
            '{"range": "品牌設定!A2:B20", "majorDimension": "ROWS", '
            '"values": [["tagline", "尋味時光"]]}'
        )
        self.assertEqual(admin._gws_read("品牌設定!A2:B20"), [["tagline", "尋味時光"]])

    def test_read_empty_tab_returns_empty_list(self):
        # API 200 但無 values key（tab 存在但範圍無資料）→ 空 list，是合法狀態
        admin._gws = lambda *a: _cp('{"range": "品牌設定!A2:B20", "majorDimension": "ROWS"}')
        self.assertEqual(admin._gws_read("品牌設定!A2:B20"), [])

    def test_api_error_json_raises(self):
        # gws 實測（2026-06-13）：API 錯誤時 stdout 印 error JSON、exit code 2
        admin._gws = lambda *a: _cp(
            stdout='{"error": {"code": 400, "message": "Unable to parse range: 不存在!A1", "reason": "badRequest"}}',
            stderr="error[api]: Unable to parse range",
            returncode=2,
        )
        with self.assertRaises(admin.GwsError) as ctx:
            admin._gws_read("不存在!A1")
        self.assertIn("400", str(ctx.exception))

    def test_nonzero_exit_without_json_raises(self):
        admin._gws = lambda *a: _cp(stdout="", stderr="boom", returncode=1)
        with self.assertRaises(admin.GwsError):
            admin._gws_read("品牌設定!A2:B20")

    def test_garbage_output_raises(self):
        # exit 0 但回應完全不是 JSON → 不可再默默回空 list
        admin._gws = lambda *a: _cp(stdout="not json at all")
        with self.assertRaises(admin.GwsError):
            admin._gws_read("品牌設定!A2:B20")

    def test_write_success_no_raise(self):
        admin._gws = lambda *a: _cp(
            '{"spreadsheetId": "%s", "updatedRange": "品牌設定!A1:B5", "updatedCells": 10}' % BACK_ID
        )
        admin._gws_write("品牌設定!A1", [["a", "b"]])  # 不應拋例外

    def test_write_error_raises(self):
        admin._gws = lambda *a: _cp(
            stdout='{"error": {"code": 401, "message": "Authentication failed", "reason": "authError"}}',
            returncode=2,
        )
        with self.assertRaises(admin.GwsError):
            admin._gws_write("品牌設定!A1", [["a", "b"]])

    def test_clear_error_raises(self):
        admin._gws = lambda *a: _cp(
            stdout='{"error": {"code": 400, "message": "Unable to parse range", "reason": "badRequest"}}',
            returncode=2,
        )
        with self.assertRaises(admin.GwsError):
            admin._gws_clear("品牌設定!A1:B20")

    def test_load_laiten_safe_returns_error_string(self):
        admin._gws = lambda *a: _cp(stdout="", stderr="boom", returncode=1)
        data, err = admin._load_laiten_safe()
        self.assertIsNotNone(err)
        # 降級資料仍可渲染頁面（含預設品牌結構）
        self.assertIn("brand", data)
        self.assertIn("lines", data)


class TestParseLaiten(unittest.TestCase):
    """_parse_laiten 純函式：products.js 的資料結構來源"""

    def test_empty_rows_gives_defaults(self):
        data = admin._parse_laiten([], [])
        b = data["brand"]
        for key in ("tagline", "subtitle", "cta_text", "cta_url_bazi", "cta_url_tea"):
            self.assertIn(key, b)
        ids = [l["id"] for l in data["lines"]]
        self.assertEqual(ids, ["bazi-cake", "afternoon-tea"])
        for line in data["lines"]:
            self.assertEqual(line["products"], [])

    def test_brand_and_products_mapping(self):
        brand_rows = [
            ["tagline", "尋味時光"],
            ["cta_url_bazi", "https://gas/bazi"],
            ["cta_url_tea", "https://gas/tea"],
            ["bazi-cake_name", "八字蛋糕"],
            ["bazi-cake_subtitle", "命格甜點"],
        ]
        prod_rows = [
            ["bazi-cake", "p1", "命格蛋糕", "八字客製", "說明", "1280", "0",
             "個", "TRUE", "1", "a.jpg, b.jpg", "蛋糕"],
            ["bazi-cake", "p2", "下架品", "", "", "0", "0", "個", "FALSE", "2", "", ""],
            ["afternoon-tea", "t1", "企業套組", "", "", "150", "0", "人份", "TRUE", "1", "", "套組"],
        ]
        data = admin._parse_laiten(brand_rows, prod_rows)
        self.assertEqual(data["brand"]["tagline"], "尋味時光")
        self.assertEqual(data["brand"]["cta_url_bazi"], "https://gas/bazi")
        bazi = next(l for l in data["lines"] if l["id"] == "bazi-cake")
        self.assertEqual(bazi["name"], "八字蛋糕")
        self.assertEqual(bazi["subtitle"], "命格甜點")
        self.assertEqual(len(bazi["products"]), 2)
        p1 = bazi["products"][0]
        self.assertEqual(p1["price"], 1280)
        self.assertEqual(p1["images"], ["a.jpg", "b.jpg"])
        self.assertTrue(p1["active"])
        self.assertFalse(bazi["products"][1]["active"], "active=FALSE 須保留布林讓前台跳過")

    def test_serializable_as_products_js(self):
        data = admin._parse_laiten([], [])
        text = "const PRODUCTS_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n"
        self.assertIn("PRODUCTS_DATA", text)


class TestMigrateSheets(unittest.TestCase):
    """遷移腳本防護常數與防呆"""

    def test_sheet_ids(self):
        self.assertEqual(migrate_sheets.FRONT_SHEET_ID, FRONT_ID)
        self.assertEqual(migrate_sheets.BACK_SHEET_ID, BACK_ID)
        self.assertNotEqual(migrate_sheets.FRONT_SHEET_ID, migrate_sheets.BACK_SHEET_ID)

    def test_migrate_tabs_exact(self):
        self.assertEqual(list(migrate_sheets.MIGRATE_TABS),
                         ["品牌設定", "產品主檔", "八字蛋糕訂單", "下午茶訂單"])

    def test_protected_tabs_disjoint(self):
        self.assertEqual(migrate_sheets.PROTECTED_TABS, {"orders", "ingredients", "monthly"})
        self.assertFalse(set(migrate_sheets.MIGRATE_TABS) & migrate_sheets.PROTECTED_TABS)

    def test_guard_raises_on_protected(self):
        for tab in ("orders", "ingredients", "monthly"):
            with self.assertRaises(RuntimeError):
                migrate_sheets._ensure_not_protected(tab)
        migrate_sheets._ensure_not_protected("品牌設定")  # 不應拋

    def test_norm_rows_ignores_trailing_empties(self):
        a = [["x", "y", ""], ["", "", ""]]
        b = [["x", "y"]]
        self.assertEqual(migrate_sheets._norm_rows(a), migrate_sheets._norm_rows(b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
