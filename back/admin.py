from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
import anthropic
import json
import re
import subprocess
import os
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

CAKE_ROOT    = Path(__file__).parent.parent
LAITEN_DIR   = CAKE_ROOT / "laiten_public"
IMAGES_DIR   = LAITEN_DIR / "images"
IMG_EXTS     = {".jpg", ".jpeg", ".png", ".webp"}

# ── Sheet ID 常數（Task1 Phase 1 根因修復：單一 SHEET_ID 拆成兩個用途常數）──
# 2026-06-13 Sheet 合併後，兩用途指向同一份後台 Sheet「八字蛋糕資料庫」；
# 拆成兩個明名常數，未來若再分家只需各改一處（specs/Task1.impact.md Backend 注意 1）。
LAITEN_SHEET_ID = "1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E"  # gws laiten（品牌設定/產品主檔）
BACK_SHEET_ID   = "1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E"  # db.py 的 orders/ingredients

# db.py 的生命線：必須在 import db 之前設定
os.environ["GOOGLE_SHEETS_ID"] = BACK_SHEET_ID

import db
GWS_CMD      = r"C:\Users\chin3\AppData\Roaming\npm\gws.cmd"

# ── Google Sheets 存取層 ──────────────────────────────────────────────
# 錯誤語意（Task1 Phase 1）：
#   空資料 = 合法（tab 存在但範圍無值 → 回空 list）
#   API / CLI 錯誤 = 拋 GwsError（不再靜默吞掉造成「存檔顯示 ok 但沒寫入」假成功）
# gws 實測（2026-06-13）：錯誤時 stdout 印 {"error": {...}} JSON 且 exit code 非 0。


class GwsError(RuntimeError):
    """gws CLI / Sheets API 錯誤（讀寫失敗必須讓使用者看見）"""


def _gws(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cmd", "/c", GWS_CMD] + list(args),
        capture_output=True, text=True, encoding="utf-8"
    )

def _gws_json(*args) -> dict:
    """執行 gws 並解析 JSON 回應；任何錯誤一律拋 GwsError"""
    r = _gws(*args)
    stdout = (r.stdout or "").strip()
    combined = stdout + (("\n" + r.stderr.strip()) if r.stderr else "")
    payload = None
    idx = stdout.find('{')
    if idx != -1:
        try:
            payload = json.loads(stdout[idx:])
        except json.JSONDecodeError:
            payload = None
    if isinstance(payload, dict) and "error" in payload:
        err = payload["error"]
        raise GwsError(f"Sheets API 錯誤 {err.get('code', '?')}：{err.get('message', '')}")
    if r.returncode != 0:
        raise GwsError(f"gws 指令失敗（exit {r.returncode}）：{combined[:400]}")
    if payload is None:
        raise GwsError(f"gws 回應無法解析：{combined[:400]}")
    return payload

def _gws_read(range_: str) -> list:
    payload = _gws_json("sheets", "spreadsheets", "values", "get",
                        "--params", json.dumps({"spreadsheetId": LAITEN_SHEET_ID, "range": range_}))
    return payload.get("values", [])

def _gws_write(range_: str, values: list):
    _gws_json("sheets", "spreadsheets", "values", "update",
              "--params", json.dumps({"spreadsheetId": LAITEN_SHEET_ID, "range": range_,
                                      "valueInputOption": "RAW"}),
              "--json", json.dumps({"values": values}))

def _gws_clear(range_: str):
    _gws_json("sheets", "spreadsheets", "values", "clear",
              "--params", json.dumps({"spreadsheetId": LAITEN_SHEET_ID, "range": range_}))

app = Flask(__name__, template_folder=str(CAKE_ROOT / "templates"))

# ── 食材資料（UI 用，不存 DB）────────────────────────────────────────
FOOD_DATA = {
    "底色": {
        "缺木": ["米白", "奶油白"],
        "缺火": ["暖白", "珊瑚粉", "蜜桃橘"],
        "缺土": ["奶茶色", "焦糖米"],
        "缺金": ["純白", "珍珠白", "奶白"],
        "缺水": ["淡霧藍", "淡紫灰", "珍珠灰白"],
    },
    "夾層": {
        "木": ["檸檬凝乳"],
        "火": ["草莓果醬", "覆盆子果凍", "草莓庫利凍", "火龍果果凍", "玫瑰鮮奶油", "櫻桃果醬"],
        "土": ["芋頭泥", "焦糖奶油", "布丁", "南瓜泥", "栗子泥"],
        "金": ["香草籽鮮奶油", "白桃果醬", "奶酪"],
        "水": ["藍莓庫利凍", "藍莓果醬", "小藍莓罐頭", "黑芝麻鮮奶油"],
    },
    "秀面": {
        "木": ["抹茶碎", "檸檬皮絲", "薄荷葉", "奇異果", "青葡萄", "青蘋果", "檸檬", "萊姆"],
        "火": ["草莓果醬", "覆盆子果醬", "玫瑰花瓣", "紅麴粉", "草莓", "荔枝果肉", "紅心火龍果", "櫻桃"],
        "土": ["焦糖脆片", "肉桂粉", "黃豆粉", "紅豆", "芒果", "鳳梨", "南瓜", "栗子", "地瓜"],
        "金": ["食用金箔", "珍珠糖", "香草籽鮮奶油", "水蜜桃罐頭", "水梨", "蘋果醬", "迷迭香", "黃金奇異果", "柚子"],
        "水": ["藍莓", "小藍莓罐頭", "銀珠糖", "藍莓果醬", "藍莓果凍", "紫葡萄", "紫薯"],
    },
    "點綴": ["薄荷葉", "檸檬皮絲", "玫瑰花瓣", "食用金箔", "銀珠糖", "珍珠糖", "迷迭香"],
    "點綴五行": {
        "薄荷葉": "木", "檸檬皮絲": "木",
        "玫瑰花瓣": "火",
        "食用金箔": "金", "銀珠糖": "金", "珍珠糖": "金", "迷迭香": "金",
    },
}


# ── 路由 ─────────────────────────────────────────────────────────

@app.route("/")
def root():
    return redirect(url_for("admin_index"))


@app.route("/admin")
def admin_index():
    orders = db.load_orders()
    return render_template("admin/index.html", orders=orders)


@app.route("/admin/order/<order_id>")  # Task1 D2：id 改字串日期前綴，路由不可再用 <int:>
def admin_order_detail(order_id):
    orders = db.load_orders()
    order = next((o for o in orders if str(o["id"]) == str(order_id)), None)
    if not order:
        return "訂單不存在", 404
    suggestion = {}
    if order.get("suggestion"):
        try:
            suggestion = json.loads(order["suggestion"])
        except Exception:
            suggestion = {}
    return render_template("admin/detail.html", order=order,
                           food_data=FOOD_DATA, suggestion=suggestion)


# ── 食材管理 ──────────────────────────────────────────────────────

@app.route("/admin/ingredients")
def admin_ingredients():
    return render_template("admin/ingredients.html")


@app.route("/admin/api/ingredients")
def api_ingredients_list():
    return jsonify(db.load_ingredients())


@app.route("/admin/api/classify", methods=["POST"])
def api_classify():
    data       = request.get_json()
    name       = data.get("name", "").strip()
    hint_types = data.get("hint_types", [])

    if not name:
        return jsonify({"error": "請輸入食材名稱或描述"})

    hint_str = ""
    if hint_types:
        hint_str = f"\n【用途提示】師傅說這個食材主要用於：{', '.join(hint_types)}，請依此調整判斷優先順序。"
        type_hints = {
            "底色": "底色以顏色維度為最高優先級，五行判斷要偏向「這個顏色給人的感覺」，食材名稱欄位可以直接用輸入的描述詞（如：淡紫灰）。",
            "夾層": "夾層以屬性（口感、溫涼補瀉）維度為最高優先級。",
            "秀面": "秀面兼顧顏色與屬性，兩者並重。",
            "點綴": "點綴以顏色維度為最高優先級。",
        }
        for t in hint_types:
            if t in type_hints:
                hint_str += f"\n{type_hints[t]}"

    system_prompt = """你是一位有二十年實戰經驗的八字命理師，同時也是資深烘焙食材研究者。
你深諳五行學理，並將其應用在蛋糕食材的能量設計上。你的判斷被台灣多位知名八字蛋糕師傅視為業界標準。

## 你的判斷哲學

五行歸屬不是機械配對，而是理解食材的「能量本質」：
- 食材的**天然本質**（原始植物/動物屬性）優先於加工形態
- **複合食材**（如「藍莓庫利凍」）以主食材為核心，加工方式為輔助修正
- 加工形態的影響：凍/果凍（稍帶金的收斂，但不改變主五行）、醬（加熱濃縮，略帶土）、泥（土性更強）、乾燥（金性增強）
- 當食材同時具備多種五行特質時，以「在蛋糕中最主要呈現的能量感」為準

## 五行對應體系（資深判斷版）

### 木🌿
- 顏色：翠綠、嫩綠、青色、黃綠
- 氣味：清新草香、茶香、青草、微酸爽
- 屬性：生發向上、酸涼清爽、疏肝理氣
- 代表食材：抹茶、薄荷、檸檬、奇異果、青蘋果、百香果（酸爽為主）

### 火🔥
- 顏色：鮮紅、桃紅、珊瑚橘、玫瑰粉
- 氣味：甜香花香、果香濃郁、溫暖馥郁
- 屬性：溫熱活化、促進循環、開心醒神
- 代表食材：草莓、覆盆子、荔枝、玫瑰、紅心火龍果、櫻桃

### 土🏔️
- 顏色：米黃、棕色、大地色、橙黃
- 氣味：甜膩奶香、焦糖、麥芽、樸實甘甜
- 屬性：滋養補中、厚重紮實、安神穩定
- 代表食材：芋頭、焦糖、南瓜、芒果、栗子、肉桂、香草（奶香重的）

### 金✨
- 顏色：純白、乳白、金色、銀色、透明
- 氣味：清淡高雅、辛香收斂、輕盈潔淨
- 屬性：收斂精緻、清肺潤燥、質感高雅
- 代表食材：香草籽奶油、白桃、水梨、奶酪、食用金箔、迷迭香

### 水💧
- 顏色：深藍、深紫、黑色、深色系
- 氣味：深邃沉靜、微苦、無味或淡味
- 屬性：涼性滋潤、沉降收藏、補腎深養
- 代表食材：藍莓、紫葡萄、黑芝麻、紫薯、藍莓系製品

## 複合食材判斷範例（你的判斷標準）

- 「藍莓庫利凍」→ 主食材藍莓（水），庫利凍是打碎過濾後的濃縮果汁凍，保留藍莓深紫色澤與酸甜滋味，主五行=水，副五行=木（酸味）
- 「草莓庫利凍」→ 草莓（火），庫利凍形態，主五行=火，副五行=木
- 「焦糖奶油」→ 焦糖（土），奶油（金/土），主五行=土，副五行=金
- 「香草籽鮮奶油」→ 香草（金/土）+鮮奶油（金），主五行=金
- 「黑芝麻鮮奶油」→ 黑芝麻（水）+鮮奶油（金），主五行=水，副五行=金
- 「玫瑰鮮奶油」→ 玫瑰（火）+鮮奶油（金），主五行=火，副五行=金

## 輸出格式

判斷完成後，只回傳以下 JSON，不要加任何說明或 markdown 包裝：
{
  "食材名稱": "...",
  "主五行": "木/火/土/金/水",
  "副五行": "木/火/土/金/水 或空字串",
  "用途": "底色/夾層/秀面/點綴（可複選，逗號分隔）",
  "季節": "常備/春/夏/秋/冬（可複選，逗號分隔）",
  "顏色分析": "一句話說明顏色對應",
  "氣味分析": "一句話說明氣味對應",
  "屬性分析": "一句話說明屬性對應",
  "備注": "有特殊說明才填，否則空字串"
}"""

    user_msg = f"請判斷食材：{name}{hint_str}"

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}]
        )
        raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/admin/api/ingredient/save", methods=["POST"])
def api_ingredient_save():
    data = request.get_json()
    if not data.get("食材名稱", "").strip():
        return jsonify({"error": "食材名稱不可為空"})
    try:
        status = db.save_ingredient(data)
        return jsonify({"status": status})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/admin/api/ingredient/update", methods=["POST"])
def api_ingredient_update():
    data = request.get_json()
    if not data.get("食材名稱", "").strip():
        return jsonify({"error": "食材名稱不可為空"})
    try:
        status = db.update_ingredient(data)
        if status == "not_found":
            return jsonify({"error": "找不到該食材"})
        return jsonify({"status": status})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/admin/api/ingredient/delete", methods=["POST"])
def api_ingredient_delete():
    data = request.get_json()
    name = data.get("食材名稱", "").strip()
    if not name:
        return jsonify({"error": "食材名稱不可為空"})
    try:
        status = db.delete_ingredient(name)
        if status == "not_found":
            return jsonify({"error": "找不到該食材"})
        return jsonify({"status": status})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── 八字分析 ──────────────────────────────────────────────────────

@app.route("/admin/api/analyze", methods=["POST"])
def api_analyze():
    data      = request.get_json()
    birthday  = data.get("birthday", "")
    shichen   = data.get("shichen", "不填")
    wish_main = data.get("wish_main", "")
    wish_sub  = data.get("wish_sub", "")

    prompt_analysis = f"""你是一位八字蛋糕分析師，請根據以下客人資料進行八字命盤分析：

出生日期：{birthday}
出生時辰：{shichen}
心願：{wish_main} {wish_sub}

請依序輸出（使用繁體中文）：

1. **八字命盤**（年柱、月柱、日柱，有時辰則加時柱）
2. **五行分佈**（列出各五行數量，標示最缺、第二缺、過旺）
3. **心願衝突判斷**（對照五行缺旺，說明設計方向：補強／平衡／以心願為主）
4. **設計建議摘要**（底色方向、夾層補什麼五行、秀面走什麼大運五行）

格式要清楚，師傅看得懂即可，不用太學術。接近節氣時請提醒。"""

    client = anthropic.Anthropic()
    msg1 = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt_analysis}]
    )
    result = msg1.content[0].text

    prompt_extract = f"""根據以下八字分析結果，萃取蛋糕食材設計建議。

分析結果：
{result}

請只輸出 JSON，不要加任何說明或 markdown 包裝：
{{
  "base_color_wuxing": "水",
  "layer1_wuxing": "木",
  "layer2_wuxing": "火",
  "topping_wuxing": "水",
  "avoid_wuxing": ["火", "土"]
}}

規則：
- base_color_wuxing：底色對應的五行（缺什麼填什麼）
- layer1_wuxing：第一夾層建議補的五行
- layer2_wuxing：第二夾層建議補的五行
- topping_wuxing：秀面建議的五行（對應大運或心願）
- avoid_wuxing：過旺需避免的五行，陣列格式
- 五行值只能是：木、火、土、金、水 其中之一"""

    msg2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt_extract}]
    )
    raw = msg2.content[0].text.strip().replace("```json", "").replace("```", "").strip()

    try:
        suggestion = json.loads(raw)
    except Exception:
        suggestion = {}

    db.update_order_fields(data.get("order_id"), {
        "bazi_result": result,
        "suggestion":  json.dumps(suggestion, ensure_ascii=False),
        "status":      "分析完成"
    })

    return jsonify({"result": result, "suggestion": suggestion})


@app.route("/admin/api/generate_card", methods=["POST"])
def api_generate_card():
    data        = request.get_json()
    order_id    = data.get("order_id")
    name        = data.get("name", "")
    birthday    = data.get("birthday", "")
    wish_main   = data.get("wish_main", "")
    wish_sub    = data.get("wish_sub", "")
    bazi_result = data.get("bazi_result", "")
    selected    = data.get("selected_ingredients", {})

    ing_desc = f"""底色：{selected.get('base_color', '')}
第一夾層：{selected.get('layer1', '')}
第二夾層：{selected.get('layer2', '')}
秀面：{selected.get('topping', '')}
點綴：{selected.get('garnish', '')}"""

    prompt = f"""你是一位八字蛋糕品牌文案師，請根據以下資料產出小卡文案。

## 客人資料
姓名：{name}
生日：{birthday}
心願：{wish_main} {wish_sub}

## 八字分析結果
{bazi_result}

## 師傅選用食材
{ing_desc}

## 文案審美底線（必須嚴格遵守）
1. 嚴禁出現品牌名、主廚字樣、自我推銷語句
2. 開頭直接切入意象或祝願，不說客套話
3. 五行能量要藏在意象與食材裡，不說破「你缺X補X」
4. 結尾不用勵志金句，要收在具體畫面或感官細節上
5. 總字數嚴格100字以內
6. 最後一行單獨一行寫：生日快樂

請直接輸出文案本文，不要加標題、不要解釋。"""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    card_text = message.content[0].text.strip()

    db.update_order_fields(order_id, {
        "ingredients": json.dumps(selected, ensure_ascii=False),
        "card_text":   card_text,
        "status":      "文案完成"
    })

    return jsonify({"card_text": card_text})


@app.route("/admin/print")
def admin_print():
    orders    = db.load_orders()
    printable = [o for o in orders if o.get("card_text")]
    return render_template("admin/print.html", orders=printable)


# ── 前台訂單收件匣（Task1 Phase 2）─────────────────────────────────

@app.route("/admin/inbox")
def admin_inbox():
    """列出兩個前台訂單 tab 中「已轉入」欄為空的單，分區顯示。"""
    err = None
    bazi_orders, tea_orders = [], []
    try:
        bazi_orders = db.load_inbox_bazi(only_unconverted=True)
        tea_orders  = db.load_inbox_tea(only_unconverted=True)
    except Exception as e:
        err = f"讀取收件匣失敗：{e}"
    # 轉單結果（由 convert 端點 redirect 帶回）
    flash_status = request.args.get("msg")      # ok / warn / err
    flash_detail = request.args.get("detail", "")
    return render_template("admin/inbox.html",
                           bazi_orders=bazi_orders, tea_orders=tea_orders, err=err,
                           flash_status=flash_status, flash_detail=flash_detail)


@app.route("/admin/inbox/convert", methods=["POST"])
def admin_inbox_convert():
    """八字蛋糕單一鍵轉入 orders（複用 create_order，D2/D3/D4 連動）。
    心願主項必填；轉單成功後才標記來源 tab「已轉入」欄（D5）。"""
    try:
        row_idx   = int(request.form.get("row", 0))
    except ValueError:
        row_idx = 0
    wish_main = request.form.get("wish_main", "").strip()
    wish_sub  = request.form.get("wish_sub", "").strip()

    if row_idx < 1:
        return _inbox_redirect("err", "轉單參數錯誤（缺少來源列）")
    if not wish_main:
        return _inbox_redirect("err", "心願主項為八字分析必填，請補填後再轉單")

    src = db.get_inbox_bazi_row(row_idx)
    if src is None:
        return _inbox_redirect("err", "找不到來源訂單（可能已被處理）")
    # 防重轉：來源「已轉入」欄非空則擋下（並發保險，收件匣已過濾過）
    if str(src.get("converted", "")).strip():
        return _inbox_redirect("warn", "此單已轉入，請勿重複轉單")

    try:
        new_id = db.create_order(
            name=src.get("name", ""),
            phone=src.get("phone", ""),
            birthday=src.get("birthdate", ""),
            shichen=src.get("birth_hour", ""),
            wish_main=wish_main,
            wish_sub=wish_sub,
            note=src.get("notes", ""),
            created_at=src.get("created_at", "") or None,  # D3：前台下單時間
            product=src.get("product", ""),
            quantity=src.get("quantity", ""),
            pickup_date=src.get("pickup_date", ""),
            delivery=src.get("delivery", ""),
        )
    except Exception as e:
        # 目標寫入失敗 → 不標記來源「已轉入」，單子留在收件匣
        return _inbox_redirect("err", f"轉入 orders 失敗，未標記已轉入：{e}")

    # 目標寫入成功後才標記來源（D5）
    try:
        db.mark_inbox_bazi_converted(row_idx, f"orders:{new_id}")
    except Exception as e:
        return _inbox_redirect(
            "warn", f"已建立訂單 {new_id}，但標記來源失敗（請手動確認，避免重複轉單）：{e}")
    return _inbox_redirect("ok", f"已轉入 orders，訂單編號 {new_id}")


@app.route("/admin/inbox/convert_tea", methods=["POST"])
def admin_inbox_convert_tea():
    """下午茶單一鍵轉入「下午茶管理」tab（狀態固定「待處理」，D1/D8）。
    下午茶一律不得寫入 orders。轉入成功後才標記來源「已轉入」（D5）。"""
    try:
        row_idx = int(request.form.get("row", 0))
    except ValueError:
        row_idx = 0
    if row_idx < 1:
        return _inbox_redirect("err", "轉單參數錯誤（缺少來源列）")

    src = db.get_inbox_tea_row(row_idx)
    if src is None:
        return _inbox_redirect("err", "找不到來源訂單（可能已被處理）")
    if str(src.get("converted", "")).strip():
        return _inbox_redirect("warn", "此單已轉入，請勿重複轉單")

    try:
        status = db.add_tea_manage_order(src)
    except Exception as e:
        return _inbox_redirect("err", f"轉入下午茶管理失敗，未標記已轉入：{e}")

    try:
        db.mark_inbox_tea_converted(row_idx, f"下午茶管理:{status}")
    except Exception as e:
        return _inbox_redirect(
            "warn", f"已轉入下午茶管理，但標記來源失敗（請手動確認）：{e}")
    return _inbox_redirect("ok", "已轉入下午茶管理（狀態：待處理）")


def _inbox_redirect(status, msg):
    return redirect(url_for("admin_inbox", msg=status, detail=msg))


# ── Laiten 輔助 ───────────────────────────────────────────────────

def _parse_laiten(brand_rows: list, prod_rows: list) -> dict:
    """把 品牌設定 / 產品主檔 的列資料解析成前後台共用的資料結構。

    純函式（不碰 Sheets），同時是 products.js 的資料結構唯一來源：
    /admin/laiten/sync 與 migrate_sheets.gen_products() 都經由此函式生成。
    """
    brand = {row[0]: row[1] for row in brand_rows if len(row) >= 2}

    lines_map = {}
    for row in prod_rows:
        if not row or len(row) < 3:
            continue
        line_id = row[0]
        prod = {
            "id":          row[1]  if len(row) > 1  else "",
            "name":        row[2]  if len(row) > 2  else "",
            "badge":       row[3]  if len(row) > 3  else "",
            "description": row[4]  if len(row) > 4  else "",
            "price":       int(row[5]) if len(row) > 5 and str(row[5]).isdigit() else 0,
            "discount":    int(row[6]) if len(row) > 6 and str(row[6]).isdigit() else 0,
            "unit":        row[7]  if len(row) > 7  else "",
            "active":      (row[8].upper() == "TRUE") if len(row) > 8 else True,
            "images":      [x.strip() for x in row[10].split(",") if x.strip()] if len(row) > 10 and row[10] else [],
            "category":    row[11] if len(row) > 11 else "",
        }
        lines_map.setdefault(line_id, []).append(prod)

    lines = []
    for lid in ["bazi-cake", "afternoon-tea"]:
        lines.append({
            "id":       lid,
            "name":     brand.get(f"{lid}_name", lid),
            "subtitle": brand.get(f"{lid}_subtitle", ""),
            "products": lines_map.get(lid, []),
        })

    return {
        "brand": {
            "name":         "Laiten",
            "chinese":      "萊點",
            "tagline":      brand.get("tagline",      "尋味時光，溫度共享"),
            "subtitle":     brand.get("subtitle",     "每一份甜點，都為你而設計"),
            "cta_text":     brand.get("cta_text",     "立即詢問"),
            "cta_url_bazi": brand.get("cta_url_bazi", ""),
            "cta_url_tea":  brand.get("cta_url_tea",  ""),
        },
        "lines": lines,
    }


def _load_laiten() -> dict:
    """讀合併後 Sheet 的 品牌設定 + 產品主檔；gws 錯誤會拋 GwsError"""
    return _parse_laiten(
        _gws_read("品牌設定!A2:B20"),
        _gws_read("產品主檔!A2:L500"),
    )


def _load_laiten_safe():
    """回傳 (data, err)。讀取失敗時 data 為預設結構（頁面仍可渲染）、err 為錯誤訊息。"""
    try:
        return _load_laiten(), None
    except GwsError as e:
        return _parse_laiten([], []), str(e)


def _save_laiten(data: dict):
    brand = data["brand"]
    lines = data["lines"]

    # 寫品牌設定
    brand_values = [
        ["欄位", "值"],
        ["tagline",      brand.get("tagline", "")],
        ["subtitle",     brand.get("subtitle", "")],
        ["cta_text",     brand.get("cta_text", "")],
        ["cta_url_bazi", brand.get("cta_url_bazi", "")],
        ["cta_url_tea",  brand.get("cta_url_tea", "")],
    ]
    for line in lines:
        brand_values.append([f"{line['id']}_name",     line["name"]])
        brand_values.append([f"{line['id']}_subtitle", line["subtitle"]])
    _gws_clear("品牌設定!A1:B20")
    _gws_write("品牌設定!A1", brand_values)

    # 寫產品主檔
    prod_values = [["line_id","product_id","name","badge","description",
                    "price","discount","unit","active","sort_order","images","category"]]
    for line in lines:
        for i, p in enumerate(line["products"]):
            prod_values.append([
                line["id"],
                p.get("id", f"prod-{i+1}"),
                p.get("name", ""),
                p.get("badge", ""),
                p.get("description", ""),
                str(p.get("price", 0)),
                str(p.get("discount", 0)),
                p.get("unit", ""),
                "TRUE" if p.get("active", True) else "FALSE",
                str(i + 1),
                ",".join(p.get("images", [])),
                p.get("category", ""),
            ])
    _gws_clear("產品主檔!A1:L500")
    _gws_write("產品主檔!A1", prod_values)


def _list_images() -> list:
    if not IMAGES_DIR.exists():
        return []
    return sorted(f.name for f in IMAGES_DIR.iterdir() if f.suffix.lower() in IMG_EXTS)


# ── Laiten 路由 ───────────────────────────────────────────────────

@app.route("/admin/laiten")
def laiten_index():
    return redirect(url_for("laiten_brand"))


@app.route("/admin/laiten/brand", methods=["GET", "POST"])
def laiten_brand():
    data, err = _load_laiten_safe()
    msg = None
    if request.method == "POST":
        if err:
            err = f"讀取現有設定失敗，未執行儲存（避免用預設值覆寫 Sheet）：{err}"
        else:
            b = data["brand"]
            b["tagline"]      = request.form.get("tagline", "").strip()
            b["subtitle"]     = request.form.get("subtitle", "").strip()
            b["cta_url_bazi"] = request.form.get("cta_url_bazi", "").strip()
            b["cta_url_tea"]  = request.form.get("cta_url_tea", "").strip()
            b["cta_text"]     = request.form.get("cta_text", "").strip()
            # Task1 D6 防呆：cta_url 是前台送單端點，空值禁止存檔。
            # 必須攔在 _save_laiten（clear + 整份重寫）之前，否則 clear 會先清掉舊值。
            empty_cta = [
                label for field, label in
                (("cta_url_bazi", "八字蛋糕送單網址"), ("cta_url_tea", "下午茶送單網址"))
                if not b.get(field, "").strip()
            ]
            if empty_cta:
                err = (f"「{ '、'.join(empty_cta) }」為前台送單端點，不可留空，"
                       "否則前台將無法送單。請填入有效網址後再儲存。")
            else:
                try:
                    _save_laiten(data)
                    msg = "ok"
                except GwsError as e:
                    err = f"儲存失敗（資料可能未寫入或寫入不完整，請重試）：{e}"
    return render_template("admin/laiten_brand.html", brand=data["brand"], msg=msg, err=err)


@app.route("/admin/laiten/products/<line_id>", methods=["GET", "POST"])
def laiten_products(line_id):
    data, err = _load_laiten_safe()
    line  = next((l for l in data["lines"] if l["id"] == line_id), None)
    if not line:
        return "產品線不存在", 404
    msg = None
    if request.method == "POST" and err:
        err = f"讀取現有資料失敗，未執行儲存（避免用空資料覆寫 Sheet）：{err}"
    elif request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            line["name"]     = request.form.get("line_name", line["name"])
            line["subtitle"] = request.form.get("line_subtitle", "")
            for i, p in enumerate(line["products"]):
                p["name"]        = request.form.get(f"p{i}_name", p.get("name", ""))
                p["badge"]       = request.form.get(f"p{i}_badge", "")
                p["description"] = request.form.get(f"p{i}_desc", "")
                p["unit"]        = request.form.get(f"p{i}_unit", "")
                p["category"]    = request.form.get(f"p{i}_category", "")
                try:
                    p["price"]    = int(request.form.get(f"p{i}_price", 0))
                    p["discount"] = int(request.form.get(f"p{i}_discount", 0))
                except ValueError:
                    pass
                p["images"] = request.form.getlist(f"p{i}_images")
            msg = "ok"
        elif action == "add":
            line["products"].append({
                "id": f"prod-{len(line['products'])+1}",
                "name": "新產品", "badge": "", "description": "",
                "price": 0, "discount": 0, "unit": "", "images": []
            })
            msg = "added"
        elif action == "delete":
            idx = int(request.form.get("idx", -1))
            if 0 <= idx < len(line["products"]):
                line["products"].pop(idx)
            msg = "deleted"
        try:
            _save_laiten(data)
        except GwsError as e:
            msg = None
            err = f"儲存失敗（資料可能未寫入或寫入不完整，請重試）：{e}"
    images = _list_images()
    return render_template(
        "admin/laiten_products.html",
        line=line, images=images, msg=msg, all_lines=data["lines"], err=err
    )


@app.route("/admin/laiten/images", methods=["GET", "POST"])
def laiten_images():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    msg = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            fname = secure_filename(request.form.get("filename", ""))
            fpath = IMAGES_DIR / fname
            if fpath.exists() and fpath.suffix.lower() in IMG_EXTS:
                fpath.unlink()
                msg = "deleted"
        else:
            uploaded = 0
            for f in request.files.getlist("files"):
                if f and f.filename and Path(f.filename).suffix.lower() in IMG_EXTS:
                    f.save(IMAGES_DIR / secure_filename(f.filename))
                    uploaded += 1
            if uploaded:
                msg = f"uploaded:{uploaded}"
    return render_template("admin/laiten_images.html", images=_list_images(), msg=msg)


@app.route("/admin/laiten/image/<filename>")
def laiten_image_file(filename):
    return send_from_directory(IMAGES_DIR, filename)


@app.route("/admin/laiten/sync", methods=["GET", "POST"])
def laiten_sync():
    import subprocess
    result = None
    if request.method == "POST":
        commit_msg = request.form.get("commit_msg", "update: Laiten 產品資料更新").strip()
        repo_root = CAKE_ROOT
        try:
            # 從 Google Sheets 生成最新的 products.js
            # Phase 1 起 products.js 是前台正式資料來源——讀不到資料時必須中止，
            # 不可推一份空的 products.js 上線（會讓前台全空）。
            latest = _load_laiten()
            if not any(line["products"] for line in latest["lines"]):
                result = ("err", "產品主檔讀回為空，已中止推送（不可推空的 products.js 上線）。"
                                 "請先確認合併後 Sheet 的「產品主檔」有資料。")
                data, _ = _load_laiten_safe()
                return render_template("admin/laiten_sync.html", result=result, data=data)
            products_js = (LAITEN_DIR / "products.js")
            products_js.write_text(
                "const PRODUCTS_DATA = " + json.dumps(latest, ensure_ascii=False, indent=2) + ";\n",
                encoding="utf-8"
            )

            subprocess.run(["git", "add", "laiten_public"], cwd=repo_root, check=True, capture_output=True)
            diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root, capture_output=True)
            if diff.returncode == 0:
                result = ("warn", "沒有偵測到變更，已是最新版本。")
            else:
                subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_root, check=True, capture_output=True)
                subprocess.run(["git", "push"], cwd=repo_root, check=True, capture_output=True)
                result = ("ok", "推送完成！Netlify 會在 1-2 分鐘內自動更新。")
        except GwsError as e:
            result = ("err", f"讀取 Sheet 失敗，已中止（未生成、未推送）：{e}")
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode(errors="replace") if e.stderr else str(e)
            result = ("err", f"操作失敗：{err}")
    data, load_err = _load_laiten_safe()
    if load_err and result is None:
        result = ("err", f"讀取 Sheet 失敗：{load_err}")
    return render_template("admin/laiten_sync.html", result=result, data=data)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
