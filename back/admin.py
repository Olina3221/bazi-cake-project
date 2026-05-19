from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import anthropic
import json
import db

app = Flask(__name__)

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


@app.route("/admin/order/<int:order_id>")
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
        model="claude-opus-4-5",
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
        model="claude-opus-4-5",
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
        model="claude-opus-4-5",
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


if __name__ == "__main__":
    app.run(debug=True, port=5001)
