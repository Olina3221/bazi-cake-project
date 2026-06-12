# qa_smoke_test.py - 萊點（Laiten）八字蛋糕系統 全系統迴歸冒煙基線
#
# 基線數：42 PASS + 1 SKIP（2026-06-13 Task1 Phase 2 同步後實跑全綠）
#   Phase 2 新增 6 項：新舊 id 並存 order detail、GET /admin/inbox、
#   inbox convert（心願必填擋下 / 八字轉單成功 / 下午茶轉單成功）、D6 品牌頁空 cta_url 擋下。
#   （Phase 4 死碼刪除尚未執行，本基線仍 import app/ingredient_classifier/ingredient_web）
#
# 用途：任何程式修改完成後，必須先跑本測試確認沒有「改A壞B」。
# 執行：python qa_smoke_test.py（需要 flask / gspread / anthropic / openpyxl）
#
# 驗證層級：可執行、型別正確、不噴錯。不驗證業務數值正確性。
#
# 安全設計（絕對不碰外部資源）：
# - Google Sheets：db._get_sheet / admin._gws_* 全部以攔截器取代，
#   任何真實呼叫會被記錄為 FAIL（external-call violation）。
# - Claude API：anthropic.Anthropic 以攔截器取代，呼叫即 FAIL。
# - 不依賴 service_account.json / 網路 / API key，可在 CI 環境執行。
# - bazi_cake.xlsx 僅做唯讀讀取（openpyxl load），不寫入。

import json
import os
import re
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACK_DIR = os.path.join(PROJECT_ROOT, "back")
sys.path.insert(0, BACK_DIR)
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # ingredient_web 的 EXCEL_PATH 是相對路徑

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

results = []


def record(name, status, msg=""):
    results.append((name, status, msg))
    print(f"[{status}] {name}" + (f": {msg}" if msg else ""))


# ─── 外部資源攔截器 ──────────────────────────────────────────────────────────
# 任何測試途中真的打到 Google Sheets / Claude API / git push，都記在這裡。

violations = []


def _make_blocker(label):
    def _blocked(*args, **kwargs):
        violations.append(label)
        raise RuntimeError(f"[SMOKE-BLOCKED] 測試中禁止外部呼叫：{label}")
    return _blocked


class _BlockedAnthropic:
    def __init__(self, *args, **kwargs):
        violations.append("anthropic.Anthropic()")
        raise RuntimeError("[SMOKE-BLOCKED] 測試中禁止呼叫 Claude API")


# ─── Smoke 1：核心模組 import ────────────────────────────────────────────────

print("\n=== Smoke 1: 核心模組 import ===")

import importlib

MODULES = ["db", "admin", "app", "ingredient_classifier", "ingredient_web"]
imported = {}
import_ok = True
for mod_name in MODULES:
    try:
        imported[mod_name] = importlib.import_module(mod_name)
        record(f"Smoke-1 import {mod_name}", "PASS")
    except Exception as e:
        record(f"Smoke-1 import {mod_name}", "FAIL", f"{type(e).__name__}: {e}")
        import_ok = False

if not import_ok:
    print("\n核心模組 import 失敗，停止執行")
    sys.exit(1)

db = imported["db"]
admin = imported["admin"]
front_app_mod = imported["app"]           # back/app.py（舊版前台表單）
ingredient_classifier = imported["ingredient_classifier"]
ingredient_web = imported["ingredient_web"]

# ─── 裝上攔截器（import 完成後、發任何請求前）────────────────────────────────

db._get_sheet = _make_blocker("db._get_sheet")
db._get_sheet_safe = _make_blocker("db._get_sheet_safe")
admin._gws = _make_blocker("admin._gws (gws CLI)")
admin._gws_json = _make_blocker("admin._gws_json (gws CLI)")
admin._gws_write = _make_blocker("admin._gws_write")
admin._gws_clear = _make_blocker("admin._gws_clear")
# Phase 1 起 gws 層語意：空資料=合法（回空 list）、API 錯誤=拋 admin.GwsError。
# mock 回空 list = 模擬「tab 存在但無資料」的合法狀態，GET 路由應照常 200。
admin._gws_read = lambda range_: []
admin.anthropic.Anthropic = _BlockedAnthropic
ingredient_classifier.anthropic.Anthropic = _BlockedAnthropic
# git push（laiten_sync 只在 POST 才會跑，這裡再加一層保險）
admin.subprocess.run = _make_blocker("admin.subprocess.run (git)")

# 用 db 真實的列轉換函式造一筆假訂單，保證欄位形狀與正式資料一致
_SAMPLE_SUGGESTION = {
    "base_color_wuxing": "水", "layer1_wuxing": "木", "layer2_wuxing": "火",
    "topping_wuxing": "水", "avoid_wuxing": ["土"],
}
_SAMPLE_ORDER_ROW = [
    "1", "2026-01-01 10:00", "煙霧測試客", "0912345678", "1990-01-01", "子時",
    "事業", "升遷順利", "測試備註", "分析完成",
    "（煙霧測試用八字分析文字）",
    json.dumps({"base_color": "淡霧藍", "layer1": "檸檬凝乳", "layer2": "草莓果醬",
                "topping": "藍莓", "garnish": "薄荷葉"}, ensure_ascii=False),
    "（煙霧測試用小卡文案）",
    json.dumps(_SAMPLE_SUGGESTION, ensure_ascii=False),
]
_sample_order = db._row_to_order(_SAMPLE_ORDER_ROW)

# Task1 D2：新日期前綴 id 的訂單列（18 欄，尾端 4 欄為前台帶入的品項/數量/取貨日期/外送）
_SAMPLE_ORDER_ROW_NEW = [
    "20260613-01", "2026-06-13 23:50", "新格式客", "0912000000", "1990-01-01", "子時",
    "事業", "升遷", "備註", "待處理",
    "", "", "", "",
    "專屬命格蛋糕", "1", "2026-07-01", "面交",
]
_sample_order_new = db._row_to_order(_SAMPLE_ORDER_ROW_NEW)

# 新舊 id 並存（D2 舊資料相容）：舊整數 id=1 與新日期 id 同時存在，皆字串查找
db.load_orders = lambda: [_sample_order, _sample_order_new]
db.load_ingredients = lambda: [
    ["藍莓", "水", "木", "夾層,秀面", "常備", "深紫近黑屬水", "微酸沉靜", "涼潤", ""],
]
db.save_ingredient = lambda data: "saved"
db.update_ingredient = lambda data: "updated"
db.delete_ingredient = lambda name: "deleted"
db.update_order_fields = lambda order_id, fields: None
# Task1 Phase 2：create_order / get_next_order_id 被 /admin/inbox/convert 複用（裁定一保留），
# 不能再用 blocker（會誤殺合法呼叫）。改為回傳假的日期前綴字串 id（D2）。
db.create_order = lambda *a, **k: "20260613-99"
db.get_next_order_id_by_date = lambda date_str: f"{date_str}-99"
db.get_next_order_id = lambda: "20260613-99"

# Task1 Phase 2：前台訂單收件匣的 db 函式 mock（不打 Sheets）。
# 一筆未轉八字單 + 一筆未轉下午茶單，row 為 1-based 資料列序。
_SAMPLE_INBOX_BAZI = {
    "row": 1, "created_at": "2026-06-13 23:50", "name": "煙霧八字客",
    "phone": "0912000000", "birthdate": "1990-01-01", "birth_hour": "子時",
    "product": "專屬命格蛋糕", "quantity": "1", "pickup_date": "2026-07-01",
    "delivery": "面交", "notes": "測試", "converted": "",
}
_SAMPLE_INBOX_TEA = {
    "row": 1, "created_at": "2026-06-13 10:00", "company": "煙霧公司",
    "contact": "陳", "phone": "0911000000", "items": "茶點50份",
    "event_date": "2026-08-01", "total_qty": "50", "notes": "", "converted": "",
}
db.load_inbox_bazi = lambda only_unconverted=True: [dict(_SAMPLE_INBOX_BAZI)]
db.load_inbox_tea = lambda only_unconverted=True: [dict(_SAMPLE_INBOX_TEA)]
db.get_inbox_bazi_row = lambda row_idx: dict(_SAMPLE_INBOX_BAZI) if row_idx == 1 else None
db.get_inbox_tea_row = lambda row_idx: dict(_SAMPLE_INBOX_TEA) if row_idx == 1 else None
db.mark_inbox_bazi_converted = lambda row_idx, mark: None
db.mark_inbox_tea_converted = lambda row_idx, mark: None
db.add_tea_manage_order = lambda tea, status=None: "待處理"

# ─── Smoke 2：Flask app 可建立、路由表可列出 ─────────────────────────────────

print("\n=== Smoke 2: Flask app 與路由表 ===")

try:
    rules = {r.rule for r in admin.app.url_map.iter_rules()}
    expected = {
        "/", "/admin", "/admin/order/<order_id>",  # Task1 D2：id 改字串日期前綴，路由不可 <int:>
        "/admin/inbox", "/admin/inbox/convert", "/admin/inbox/convert_tea",  # Task1 Phase 2 收件匣
        "/admin/ingredients", "/admin/api/ingredients", "/admin/api/classify",
        "/admin/api/ingredient/save", "/admin/api/ingredient/update",
        "/admin/api/ingredient/delete",
        "/admin/api/analyze", "/admin/api/generate_card", "/admin/print",
        "/admin/laiten", "/admin/laiten/brand", "/admin/laiten/products/<line_id>",
        "/admin/laiten/images", "/admin/laiten/image/<filename>", "/admin/laiten/sync",
    }
    missing = expected - rules
    assert not missing, f"後台路由表缺少：{sorted(missing)}"
    record("Smoke-2 admin app 路由表", "PASS", f"共 {len(rules)} 條路由")
except AssertionError as e:
    record("Smoke-2 admin app 路由表", "FAIL", str(e))
except Exception:
    record("Smoke-2 admin app 路由表", "FAIL", traceback.format_exc(limit=3))

try:
    front_rules = {r.rule for r in front_app_mod.app.url_map.iter_rules()}
    for rule in ("/", "/submit", "/success"):
        assert rule in front_rules, f"app.py 路由表缺少 {rule}"
    record("Smoke-2 app.py（舊版前台）路由表", "PASS")
except AssertionError as e:
    record("Smoke-2 app.py（舊版前台）路由表", "FAIL", str(e))
except Exception:
    record("Smoke-2 app.py（舊版前台）路由表", "FAIL", traceback.format_exc(limit=3))

try:
    web_rules = {r.rule for r in ingredient_web.app.url_map.iter_rules()}
    for rule in ("/", "/classify", "/save", "/ingredients"):
        assert rule in web_rules, f"ingredient_web 路由表缺少 {rule}"
    record("Smoke-2 ingredient_web 路由表", "PASS")
except AssertionError as e:
    record("Smoke-2 ingredient_web 路由表", "FAIL", str(e))
except Exception:
    record("Smoke-2 ingredient_web 路由表", "FAIL", traceback.format_exc(limit=3))

# ─── Smoke 3：後台關鍵路由冒煙（test_client，外部呼叫全 mock）────────────────

print("\n=== Smoke 3: 後台關鍵路由（test_client）===")

client = admin.app.test_client()

GET_CASES = [
    # (路徑, 可接受的狀態碼)
    ("/",                                  {302}),
    ("/admin",                             {200}),
    ("/admin/order/1",                     {200}),  # 舊整數 id 仍可查找（D2 相容）
    ("/admin/order/20260613-01",           {200}),  # 新日期前綴 id 路由可接受字串並命中
    ("/admin/order/999999",                {404}),
    ("/admin/inbox",                       {200}),  # Task1 Phase 2 收件匣
    ("/admin/ingredients",                 {200}),
    ("/admin/api/ingredients",             {200}),
    ("/admin/print",                       {200}),
    ("/admin/laiten",                      {302}),
    ("/admin/laiten/brand",                {200}),
    ("/admin/laiten/products/bazi-cake",   {200}),
    ("/admin/laiten/products/afternoon-tea", {200}),
    ("/admin/laiten/products/no-such-line", {404}),
    ("/admin/laiten/images",               {200}),
    ("/admin/laiten/sync",                 {200}),
]

for path, ok_codes in GET_CASES:
    try:
        resp = client.get(path)
        assert resp.status_code in ok_codes, \
            f"狀態碼 {resp.status_code}，預期 {sorted(ok_codes)}"
        record(f"Smoke-3 GET {path}", "PASS", f"{resp.status_code}")
    except AssertionError as e:
        record(f"Smoke-3 GET {path}", "FAIL", str(e))
    except Exception:
        record(f"Smoke-3 GET {path}", "FAIL", traceback.format_exc(limit=3))

# 圖片路由：用實際存在的第一張圖測（沒有圖則 SKIP）
try:
    images = admin._list_images()
    if images:
        resp = client.get(f"/admin/laiten/image/{images[0]}")
        assert resp.status_code == 200, f"狀態碼 {resp.status_code}"
        record(f"Smoke-3 GET /admin/laiten/image/{images[0]}", "PASS", "200")
    else:
        record("Smoke-3 GET /admin/laiten/image/<filename>", "SKIP",
               "laiten_public/images 目前沒有圖片檔")
except AssertionError as e:
    record("Smoke-3 GET /admin/laiten/image/<filename>", "FAIL", str(e))
except Exception:
    record("Smoke-3 GET /admin/laiten/image/<filename>", "FAIL",
           traceback.format_exc(limit=3))

# API 驗證層冒煙：空輸入應回 error JSON，且「不會」打到 Claude API / Sheets
API_EMPTY_CASES = [
    ("/admin/api/classify",          {"name": ""}),
    ("/admin/api/ingredient/save",   {"食材名稱": ""}),
    ("/admin/api/ingredient/update", {"食材名稱": ""}),
    ("/admin/api/ingredient/delete", {"食材名稱": ""}),
]
for path, payload in API_EMPTY_CASES:
    try:
        resp = client.post(path, json=payload)
        assert resp.status_code == 200, f"狀態碼 {resp.status_code}"
        body = resp.get_json()
        assert isinstance(body, dict) and "error" in body, \
            f"空輸入應回 error JSON，實際 {body!r}"
        record(f"Smoke-3 POST {path}（空輸入驗證）", "PASS")
    except AssertionError as e:
        record(f"Smoke-3 POST {path}（空輸入驗證）", "FAIL", str(e))
    except Exception:
        record(f"Smoke-3 POST {path}（空輸入驗證）", "FAIL",
               traceback.format_exc(limit=3))

# 有效輸入的食材寫入 API（db 層已 mock，驗證路由 → db 的串接與回傳格式）
try:
    valid_ing = {"食材名稱": "煙霧測試食材", "主五行": "水", "副五行": "",
                 "用途": "夾層", "季節": "常備",
                 "顏色分析": "x", "氣味分析": "x", "屬性分析": "x", "備注": ""}
    for path, expect_status in [
        ("/admin/api/ingredient/save",   "saved"),
        ("/admin/api/ingredient/update", "updated"),
        ("/admin/api/ingredient/delete", "deleted"),
    ]:
        resp = client.post(path, json=valid_ing)
        body = resp.get_json()
        assert resp.status_code == 200 and isinstance(body, dict), \
            f"{path} 回應異常：{resp.status_code} {body!r}"
        assert body.get("status") == expect_status, \
            f"{path} 應回 status={expect_status}，實際 {body!r}"
    record("Smoke-3 POST 食材 save/update/delete（mock db）", "PASS")
except AssertionError as e:
    record("Smoke-3 POST 食材 save/update/delete（mock db）", "FAIL", str(e))
except Exception:
    record("Smoke-3 POST 食材 save/update/delete（mock db）", "FAIL",
           traceback.format_exc(limit=3))

# ── Task1 Phase 2：收件匣轉單冒煙（create_order / inbox db 已 mock）──

# 八字轉單：缺心願主項 → 應擋下（redirect 回 inbox 帶 err），不呼叫 create_order
try:
    resp = client.post("/admin/inbox/convert", data={"row": "1", "wish_main": ""})
    assert resp.status_code in {302, 303}, f"應 redirect，實際 {resp.status_code}"
    assert "msg=err" in resp.headers.get("Location", ""), \
        f"心願主項空應帶 err，實際 Location={resp.headers.get('Location')}"
    record("Smoke-3 POST /admin/inbox/convert（心願主項必填擋下）", "PASS")
except AssertionError as e:
    record("Smoke-3 POST /admin/inbox/convert（心願主項必填擋下）", "FAIL", str(e))
except Exception:
    record("Smoke-3 POST /admin/inbox/convert（心願主項必填擋下）", "FAIL",
           traceback.format_exc(limit=3))

# 八字轉單：補心願主項 → 成功（create_order mock 回假 id，redirect 帶 ok）
try:
    resp = client.post("/admin/inbox/convert",
                       data={"row": "1", "wish_main": "事業", "wish_sub": "升遷"})
    assert resp.status_code in {302, 303}, f"應 redirect，實際 {resp.status_code}"
    assert "msg=ok" in resp.headers.get("Location", ""), \
        f"補心願主項應成功，實際 Location={resp.headers.get('Location')}"
    record("Smoke-3 POST /admin/inbox/convert（八字轉單成功）", "PASS")
except AssertionError as e:
    record("Smoke-3 POST /admin/inbox/convert（八字轉單成功）", "FAIL", str(e))
except Exception:
    record("Smoke-3 POST /admin/inbox/convert（八字轉單成功）", "FAIL",
           traceback.format_exc(limit=3))

# 下午茶轉單：成功（add_tea_manage_order mock，不寫 orders）
try:
    resp = client.post("/admin/inbox/convert_tea", data={"row": "1"})
    assert resp.status_code in {302, 303}, f"應 redirect，實際 {resp.status_code}"
    assert "msg=ok" in resp.headers.get("Location", ""), \
        f"下午茶轉單應成功，實際 Location={resp.headers.get('Location')}"
    record("Smoke-3 POST /admin/inbox/convert_tea（下午茶轉單成功）", "PASS")
except AssertionError as e:
    record("Smoke-3 POST /admin/inbox/convert_tea（下午茶轉單成功）", "FAIL", str(e))
except Exception:
    record("Smoke-3 POST /admin/inbox/convert_tea（下午茶轉單成功）", "FAIL",
           traceback.format_exc(limit=3))

# Task1 D6：品牌頁 cta_url 空值禁止存檔——攔在 _save_laiten clear 之前。
# 攔截成功則不會呼叫被 blocker 的 _gws_clear/_gws_write（Smoke-7 亦會雙重把關）。
try:
    resp = client.post("/admin/laiten/brand", data={
        "tagline": "x", "subtitle": "y", "cta_text": "立即詢問",
        "cta_url_bazi": "", "cta_url_tea": "https://gas/tea",  # bazi 空
    })
    assert resp.status_code == 200, f"狀態碼 {resp.status_code}"
    html = resp.get_data(as_text=True)
    assert "不可留空" in html, "空 cta_url 應顯示禁止存檔的錯誤訊息"
    assert "已儲存" not in html, "空 cta_url 不應顯示存檔成功"
    record("Smoke-3 POST /admin/laiten/brand（D6 空 cta_url 擋下）", "PASS")
except AssertionError as e:
    record("Smoke-3 POST /admin/laiten/brand（D6 空 cta_url 擋下）", "FAIL", str(e))
except Exception:
    record("Smoke-3 POST /admin/laiten/brand（D6 空 cta_url 擋下）", "FAIL",
           traceback.format_exc(limit=3))

# ─── Smoke 4：ingredient_web 路由冒煙（唯讀，不打 API）──────────────────────

print("\n=== Smoke 4: ingredient_web 路由 ===")

web_client = ingredient_web.app.test_client()

try:
    resp = web_client.get("/")
    assert resp.status_code == 200, f"狀態碼 {resp.status_code}"
    record("Smoke-4 GET /（食材判斷頁）", "PASS")
except AssertionError as e:
    record("Smoke-4 GET /（食材判斷頁）", "FAIL", str(e))
except Exception:
    record("Smoke-4 GET /（食材判斷頁）", "FAIL", traceback.format_exc(limit=3))

try:
    if os.path.exists(os.path.join(PROJECT_ROOT, ingredient_web.EXCEL_PATH)):
        resp = web_client.get("/ingredients")
        assert resp.status_code == 200, f"狀態碼 {resp.status_code}"
        body = resp.get_json()
        assert isinstance(body, list), f"/ingredients 應回 list，實際 {type(body)}"
        record("Smoke-4 GET /ingredients（唯讀 xlsx）", "PASS", f"{len(body)} 筆")
    else:
        record("Smoke-4 GET /ingredients（唯讀 xlsx）", "SKIP",
               f"{ingredient_web.EXCEL_PATH} 不存在")
except AssertionError as e:
    record("Smoke-4 GET /ingredients（唯讀 xlsx）", "FAIL", str(e))
except Exception:
    record("Smoke-4 GET /ingredients（唯讀 xlsx）", "FAIL",
           traceback.format_exc(limit=3))

try:
    resp = web_client.post("/classify", json={"name": ""})
    body = resp.get_json()
    assert resp.status_code == 200 and isinstance(body, dict) and "error" in body, \
        f"空輸入應回 error JSON，實際 {resp.status_code} {body!r}"
    record("Smoke-4 POST /classify（空輸入驗證）", "PASS")
except AssertionError as e:
    record("Smoke-4 POST /classify（空輸入驗證）", "FAIL", str(e))
except Exception:
    record("Smoke-4 POST /classify（空輸入驗證）", "FAIL",
           traceback.format_exc(limit=3))

# ─── Smoke 5：templates 完整性 ───────────────────────────────────────────────

print("\n=== Smoke 5: templates 完整性 ===")

# 已知舊版缺漏（back/app.py 是被 Netlify 靜態前台取代的舊版表單，模板從未存在）
KNOWN_LEGACY_MISSING = {"order_form.html", "success.html"}

_render_re = re.compile(r"""render_template\(\s*["']([^"']+)["']""")


def _referenced_templates(py_path):
    with open(py_path, encoding="utf-8") as f:
        return _render_re.findall(f.read())


try:
    # admin.py：template_folder = 專案根 /templates
    admin_tpl_dir = os.path.join(PROJECT_ROOT, "templates")
    refs = _referenced_templates(os.path.join(BACK_DIR, "admin.py"))
    assert refs, "admin.py 找不到任何 render_template 引用（regex 解析異常？）"
    missing = [t for t in refs if not os.path.exists(os.path.join(admin_tpl_dir, t))]
    assert not missing, f"admin.py 引用但不存在的模板：{missing}"
    record("Smoke-5 admin.py 模板完整性", "PASS", f"共 {len(set(refs))} 個模板")
except AssertionError as e:
    record("Smoke-5 admin.py 模板完整性", "FAIL", str(e))
except Exception:
    record("Smoke-5 admin.py 模板完整性", "FAIL", traceback.format_exc(limit=3))

try:
    # app.py：Flask(__name__) 預設 template_folder = back/templates
    app_tpl_dir = os.path.join(BACK_DIR, "templates")
    refs = set(_referenced_templates(os.path.join(BACK_DIR, "app.py")))
    missing = [t for t in refs if not os.path.exists(os.path.join(app_tpl_dir, t))]
    unexpected = [t for t in missing if t not in KNOWN_LEGACY_MISSING]
    if unexpected:
        record("Smoke-5 app.py 模板完整性", "FAIL",
               f"引用但不存在的模板：{unexpected}")
    elif missing:
        record("Smoke-5 app.py 模板完整性", "SKIP",
               f"已知舊版缺漏 {sorted(missing)}（前台已改 laiten_public 靜態頁，"
               f"app.py 的 / 與 /success 實際無法渲染，已回報）")
    else:
        record("Smoke-5 app.py 模板完整性", "PASS")
except Exception:
    record("Smoke-5 app.py 模板完整性", "FAIL", traceback.format_exc(limit=3))

# ─── Smoke 6：前台 laiten_public 靜態檔 ──────────────────────────────────────

print("\n=== Smoke 6: laiten_public 靜態檔 ===")

LAITEN_DIR = os.path.join(PROJECT_ROOT, "laiten_public")

try:
    index_path = os.path.join(LAITEN_DIR, "index.html")
    assert os.path.exists(index_path), "laiten_public/index.html 不存在"
    html = open(index_path, encoding="utf-8").read()
    assert "<html" in html.lower(), "index.html 缺少 <html> 標籤"
    assert "</html>" in html.lower(), "index.html 缺少 </html> 結尾（檔案可能被截斷）"
    # 前台資料來源（Task1 Phase 1 收緊）：必須引用 products.js，
    # 且不得殘留 fetchSheet / gviz 公開讀取（合併後 Sheet 為私有，個資保護）。
    assert 'src="products.js"' in html, \
        "index.html 必須以 <script src=\"products.js\"> 引用正式資料來源"
    assert "fetchSheet" not in html, "index.html 殘留 fetchSheet（gviz 讀取應已移除）"
    assert "/gviz/" not in html, "index.html 殘留 gviz URL（公開讀取應已移除）"
    assert "docs.google.com/spreadsheets" not in html, \
        "index.html 殘留 Google Sheets 直接讀取 URL"
    record("Smoke-6 index.html 基本檢查", "PASS", "資料來源：products.js（無 gviz 殘留）")
except AssertionError as e:
    record("Smoke-6 index.html 基本檢查", "FAIL", str(e))
except Exception:
    record("Smoke-6 index.html 基本檢查", "FAIL", traceback.format_exc(limit=3))

try:
    pj_path = os.path.join(LAITEN_DIR, "products.js")
    assert os.path.exists(pj_path), "laiten_public/products.js 不存在"
    text = open(pj_path, encoding="utf-8").read().strip()
    prefix = "const PRODUCTS_DATA ="
    assert text.startswith(prefix), \
        "products.js 開頭不是 const PRODUCTS_DATA =（與 admin 同步格式不符）"
    payload = text[len(prefix):].strip().rstrip(";")
    data = json.loads(payload)   # 可解析 = 語法層級沒壞
    assert isinstance(data.get("brand"), dict), "products.js 缺少 brand 物件"
    # Phase 1 起 products.js 是前台正式資料來源：brand 必含前台必需 key
    REQUIRED_BRAND_KEYS = {"tagline", "subtitle", "cta_text", "cta_url_bazi", "cta_url_tea"}
    missing_keys = REQUIRED_BRAND_KEYS - set(data["brand"].keys())
    assert not missing_keys, f"products.js brand 缺少前台必需 key：{sorted(missing_keys)}"
    assert isinstance(data.get("lines"), list) and data["lines"], \
        "products.js 缺少 lines 或為空"
    line_ids = set()
    for line in data["lines"]:
        assert "id" in line and isinstance(line.get("products"), list), \
            f"產品線結構異常：{line.get('id', '?')}"
        line_ids.add(line["id"])
    assert {"bazi-cake", "afternoon-tea"} <= line_ids, \
        f"products.js 缺少必要產品線：{line_ids}"
    record("Smoke-6 products.js 可解析", "PASS",
           f"{len(data['lines'])} 條產品線，brand key 完整")
except AssertionError as e:
    record("Smoke-6 products.js 可解析", "FAIL", str(e))
except json.JSONDecodeError as e:
    record("Smoke-6 products.js 可解析", "FAIL", f"JSON 解析失敗：{e}")
except Exception:
    record("Smoke-6 products.js 可解析", "FAIL", traceback.format_exc(limit=3))

try:
    img_dir = os.path.join(LAITEN_DIR, "images")
    assert os.path.isdir(img_dir), "laiten_public/images 目錄不存在"
    record("Smoke-6 images 目錄存在", "PASS")
except AssertionError as e:
    record("Smoke-6 images 目錄存在", "FAIL", str(e))

# ─── Smoke 7：外部呼叫防護檢查 ───────────────────────────────────────────────

print("\n=== Smoke 7: 外部呼叫防護 ===")
if violations:
    record("Smoke-7 測試過程無外部呼叫", "FAIL",
           f"以下外部資源在測試中被觸發：{sorted(set(violations))}")
else:
    record("Smoke-7 測試過程無外部呼叫", "PASS",
           "Google Sheets / Claude API / git 均未被真實呼叫")

# ─── 彙整 ────────────────────────────────────────────────────────────────────

print("\n=== 結果彙整 ===")
passed = [r for r in results if r[1] == "PASS"]
failed = [r for r in results if r[1] == "FAIL"]
skipped = [r for r in results if r[1] == "SKIP"]

print(f"PASS: {len(passed)}  FAIL: {len(failed)}  SKIP: {len(skipped)}")

if skipped:
    print("\nSKIP 項目：")
    for name, _, msg in skipped:
        print(f"  - {name}: {msg}")

if failed:
    print("\n失敗項目：")
    for name, _, msg in failed:
        print(f"  - {name}")
        if msg:
            print(f"    {msg}")
    print("\n結論：有問題需修復")
    sys.exit(1)
else:
    print("\n結論：全部通過")
    sys.exit(0)
