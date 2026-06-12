# tests/test_phase2.py — Task1 Phase 2 後端單元測試
#
# 範圍（全程不碰外部資源，_get_sheet 一律 mock）：
#   1. D2 取號：日期前綴 YYYYMMDD-NN、序號 +1 補零、跨日歸零、超 99 進位
#   2. D2 舊資料相容：舊整數 id 取號時略過、字串查找不受影響
#   3. create_order 18 欄擴充 + created_at（D3）+ 4 新欄（D4）+ 回傳字串
#   4. _row_to_order 18 欄映射
#   5. 收件匣列解析 / 已轉入過濾 / 標記欄位置
#   6. 下午茶管理寫入（狀態固定「待處理」、不寫 orders）
#
# 執行：python -m unittest tests.test_phase2 -v

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "back"))
sys.path.insert(0, PROJECT_ROOT)

import db  # noqa: E402


class _FakeWS:
    """最小 worksheet 替身：記錄 append/update 呼叫，回放預設 rows。"""
    def __init__(self, rows=None):
        self.rows = rows or []
        self.appended = []
        self.updated_cells = []  # (row, col, value)

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def append_row(self, values, value_input_option=None):
        self.appended.append(list(values))
        self.rows.append(list(values))

    def update_cell(self, row, col, value):
        self.updated_cells.append((row, col, value))


def _patch_sheets(test, mapping):
    """把 db._get_sheet / _get_sheet_safe 換成回傳 mapping[tab] 的替身。"""
    orig = (db._get_sheet, db._get_sheet_safe)

    def fake_get(tab):
        if tab not in mapping:
            raise RuntimeError(f"unexpected tab {tab}")
        return mapping[tab]

    def fake_get_safe(tab):
        return mapping.get(tab)

    db._get_sheet = fake_get
    db._get_sheet_safe = fake_get_safe
    test.addCleanup(lambda: setattr(db, "_get_sheet", orig[0]))
    test.addCleanup(lambda: setattr(db, "_get_sheet_safe", orig[1]))


class TestOrdersHeader(unittest.TestCase):
    def test_header_is_18_cols(self):
        self.assertEqual(len(db.ORDERS_HEADER), 18)
        self.assertEqual(db.ORDERS_HEADER[14:], ["品項", "數量", "取貨日期", "外送"])

    def test_row_to_order_18_fields(self):
        row = [f"v{i}" for i in range(18)]
        o = db._row_to_order(row)
        self.assertEqual(o["product"], "v14")
        self.assertEqual(o["quantity"], "v15")
        self.assertEqual(o["pickup_date"], "v16")
        self.assertEqual(o["delivery"], "v17")

    def test_row_to_order_short_row_pads(self):
        o = db._row_to_order(["1", "2026-06-13 10:00", "王"])
        self.assertEqual(o["product"], "")
        self.assertEqual(o["delivery"], "")
        self.assertEqual(o["status"], "待處理")


class TestGetNextOrderIdByDate(unittest.TestCase):
    def _ws(self, ids):
        header = db.ORDERS_HEADER
        rows = [header] + [[i] + [""] * 17 for i in ids]
        return _FakeWS(rows)

    def test_first_of_day(self):
        _patch_sheets(self, {"orders": self._ws([])})
        self.assertEqual(db.get_next_order_id_by_date("20260613"), "20260613-01")

    def test_increment_same_day(self):
        _patch_sheets(self, {"orders": self._ws(["20260613-01", "20260613-02"])})
        self.assertEqual(db.get_next_order_id_by_date("20260613"), "20260613-03")

    def test_zero_pad_two_digits(self):
        _patch_sheets(self, {"orders": self._ws(["20260613-09"])})
        self.assertEqual(db.get_next_order_id_by_date("20260613"), "20260613-10")

    def test_over_99_becomes_three_digits(self):
        _patch_sheets(self, {"orders": self._ws(["20260613-99"])})
        self.assertEqual(db.get_next_order_id_by_date("20260613"), "20260613-100")

    def test_cross_day_resets(self):
        _patch_sheets(self, {"orders": self._ws(["20260613-05"])})
        self.assertEqual(db.get_next_order_id_by_date("20260614"), "20260614-01")

    def test_legacy_int_id_skipped(self):
        # 舊整數 id「1」不屬於任何日期群組，取號略過不干擾
        _patch_sheets(self, {"orders": self._ws(["1", "20260613-01"])})
        self.assertEqual(db.get_next_order_id_by_date("20260613"), "20260613-02")
        # 全新日期仍從 01 起，不受舊 id 影響
        _patch_sheets(self, {"orders": self._ws(["1"])})
        self.assertEqual(db.get_next_order_id_by_date("20260613"), "20260613-01")


class TestDateStrFromCreatedAt(unittest.TestCase):
    def test_parses_various_formats(self):
        self.assertEqual(db._date_str_from_created_at("2026-06-13 23:50"), "20260613")
        self.assertEqual(db._date_str_from_created_at("2026/06/13 2:32:48"), "20260613")
        self.assertEqual(db._date_str_from_created_at("2026/6/6 13:59:22"), "20260606")

    def test_empty_falls_back_today(self):
        out = db._date_str_from_created_at("")
        self.assertRegex(out, r"^\d{8}$")


class TestCreateOrder(unittest.TestCase):
    def test_appends_18_cols_and_returns_str_id(self):
        ws = _FakeWS([db.ORDERS_HEADER])
        _patch_sheets(self, {"orders": ws})
        new_id = db.create_order(
            name="王", phone="0912", birthday="1990-01-01", shichen="子時",
            wish_main="事業", wish_sub="升遷", note="備註",
            created_at="2026-06-13 23:50",
            product="專屬命格蛋糕", quantity="1",
            pickup_date="2026-07-01", delivery="面交",
        )
        self.assertEqual(new_id, "20260613-01")  # 日期取 created_at（D3/D2）
        self.assertIsInstance(new_id, str)
        appended = ws.appended[0]
        self.assertEqual(len(appended), 18)
        self.assertEqual(appended[0], "20260613-01")
        self.assertEqual(appended[1], "2026-06-13 23:50")  # created_at 帶入
        self.assertEqual(appended[9], "待處理")
        self.assertEqual(appended[14:], ["專屬命格蛋糕", "1", "2026-07-01", "面交"])

    def test_backward_compatible_without_new_params(self):
        ws = _FakeWS([db.ORDERS_HEADER])
        _patch_sheets(self, {"orders": ws})
        new_id = db.create_order("王", "0912", "1990-01-01", "", "事業", "", "")
        self.assertIsInstance(new_id, str)
        appended = ws.appended[0]
        self.assertEqual(len(appended), 18)  # 仍寫 18 欄
        self.assertEqual(appended[14:], ["", "", "", ""])

    def test_id_uses_created_at_date_not_today(self):
        # D2/D3：前台 6/13 下單、今天轉單 → id 日期仍是 6/13
        ws = _FakeWS([db.ORDERS_HEADER, ["20260613-01"] + [""] * 17])
        _patch_sheets(self, {"orders": ws})
        new_id = db.create_order("王", "0912", "1990-01-01", "", "事業", "", "",
                                 created_at="2026-06-13 10:00")
        self.assertEqual(new_id, "20260613-02")


class TestInboxLoad(unittest.TestCase):
    def _bazi_ws(self):
        rows = [
            db.BAZI_INBOX_HEADER,
            ["2026/6/6 13:59", "戴寧", "0912", "2001/7/21", "", "補運蛋糕", "1",
             "2026/6", "面交", "贈送", ""],            # 未轉
            ["2026/6/7 10:00", "已轉客", "0911", "1990-01-01", "子時", "蛋糕", "2",
             "2026-07-01", "面交", "", "orders:20260607-01"],  # 已轉
        ]
        return _FakeWS(rows)

    def test_load_inbox_bazi_only_unconverted(self):
        _patch_sheets(self, {"八字蛋糕訂單": self._bazi_ws()})
        out = db.load_inbox_bazi(only_unconverted=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "戴寧")
        self.assertEqual(out[0]["row"], 1)          # 1-based 資料列序
        self.assertEqual(out[0]["product"], "補運蛋糕")

    def test_load_inbox_bazi_all(self):
        _patch_sheets(self, {"八字蛋糕訂單": self._bazi_ws()})
        out = db.load_inbox_bazi(only_unconverted=False)
        self.assertEqual(len(out), 2)

    def test_get_inbox_bazi_row(self):
        _patch_sheets(self, {"八字蛋糕訂單": self._bazi_ws()})
        d = db.get_inbox_bazi_row(1)
        self.assertEqual(d["name"], "戴寧")
        self.assertIsNone(db.get_inbox_bazi_row(99))

    def test_mark_inbox_bazi_converted_writes_col11_realrow(self):
        ws = self._bazi_ws()
        _patch_sheets(self, {"八字蛋糕訂單": ws})
        db.mark_inbox_bazi_converted(1, "orders:20260613-01")
        # 資料列序 1 → Sheet 實體列 2（跳過標題），第 11 欄
        self.assertEqual(ws.updated_cells, [(2, 11, "orders:20260613-01")])

    def test_load_inbox_tea_only_unconverted(self):
        rows = [
            db.TEA_INBOX_HEADER,
            ["2026/6/6", "甲公司", "陳", "0912", "蛋糕30份", "2026-07-01", "30", "", ""],
            ["2026/6/7", "乙公司", "林", "0911", "茶點50", "2026-08-01", "50", "", "下午茶管理:待處理"],
        ]
        _patch_sheets(self, {"下午茶訂單": _FakeWS(rows)})
        out = db.load_inbox_tea(only_unconverted=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["company"], "甲公司")
        self.assertEqual(out[0]["total_qty"], "30")

    def test_mark_inbox_tea_converted_writes_col9(self):
        rows = [db.TEA_INBOX_HEADER,
                ["2026/6/6", "甲", "陳", "0912", "x", "2026-07-01", "30", "", ""]]
        ws = _FakeWS(rows)
        _patch_sheets(self, {"下午茶訂單": ws})
        db.mark_inbox_tea_converted(1, "下午茶管理:待處理")
        self.assertEqual(ws.updated_cells, [(2, 9, "下午茶管理:待處理")])


class TestTeaManage(unittest.TestCase):
    def test_add_tea_manage_default_status_pending(self):
        ws = _FakeWS([db.TEA_MANAGE_HEADER])
        _patch_sheets(self, {db.TEA_MANAGE_TAB: ws})
        tea = {"created_at": "2026/6/6", "company": "甲公司", "contact": "陳",
               "phone": "0912", "items": "蛋糕30份", "event_date": "2026-07-01",
               "total_qty": "30", "notes": "備註"}
        status = db.add_tea_manage_order(tea)
        self.assertEqual(status, "待處理")
        appended = ws.appended[0]
        self.assertEqual(len(appended), 9)
        self.assertEqual(appended[0], "2026/6/6")
        self.assertEqual(appended[1], "甲公司")
        self.assertEqual(appended[8], "待處理")

    def test_tea_default_status_constant(self):
        self.assertEqual(db.TEA_DEFAULT_STATUS, "待處理")


class TestUpdateOrderFieldsCompat(unittest.TestCase):
    """col_map 10-14 不變；新舊 id 都走字串比對命中。"""
    def test_col_map_unchanged_and_str_lookup(self):
        rows = [
            db.ORDERS_HEADER,
            ["1"] + [""] * 17,                 # 舊整數 id
            ["20260613-01"] + [""] * 17,       # 新日期 id
        ]
        ws = _FakeWS(rows)
        _patch_sheets(self, {"orders": ws})
        db.update_order_fields("1", {"status": "分析完成"})
        db.update_order_fields("20260613-01", {"bazi_result": "x"})
        # 舊 id 命中第 2 列、status 寫第 10 欄；新 id 命中第 3 列、bazi_result 寫第 11 欄
        self.assertIn((2, 10, "分析完成"), ws.updated_cells)
        self.assertIn((3, 11, "x"), ws.updated_cells)


if __name__ == "__main__":
    unittest.main(verbosity=2)
