# SYSTEM_MAP — 萊點（Laiten）系統依賴地圖

> 由 SA 手動撰寫於 2026-06-13（純靜態程式分析，未實際連線 Sheets / Claude API）。
> SA agent：影響分析以此檔為準；結構有變動時手動更新本檔（本專案暫不建自動生成腳本，理由見文末）。
> 本專案無資料庫；持久層是兩份 Google Sheets，存取方式有四種異質管道（gspread / gws CLI / gviz CSV / GAS appendRow）。

## 兩份 Google Sheets（資料層全貌）

| Sheet | ID | 實際存在的工作表（2026-06-13 gws 唯讀實查） | 誰在讀寫 |
|-------|----|--------------|---------|
| 後台 Sheet「八字蛋糕資料庫」 | `1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E` | `orders`、`ingredients`（db.py via gspread）、`monthly`（無程式引用） | back/admin.py（經 db.py） |
| 前台 Sheet「Laiten 系統主檔」 | `1xtuKyod3lOQUmp_D10AhDDGSD4bVxG3TmZudO2S9AMo` | `品牌設定`、`產品主檔`（前台 gviz 讀）、`八字蛋糕訂單`、`下午茶訂單`（GAS 寫） | laiten_public/index.html（讀）、gas_order_handler.js（寫） |

> ⚠️ 已實查確認（2026-06-13）：**後台 Sheet 並沒有 `品牌設定` / `產品主檔` 兩張 tab**（兩張 tab 只存在於前台 Sheet）。
> 但 admin.py 的 laiten 功能（brand / products / sync）用同一個 `SHEET_ID = 1oYJ7…` 走 gws 讀寫這兩張 tab
> → API 回 400「Unable to parse range」，被 `_gws_read`（回空 list）與 `_gws_write/_gws_clear`（不檢查錯誤）整個吞掉。
> 結果：後台品牌/產品頁**讀到的是程式預設值、存檔顯示 ok 但實際什麼都沒寫入**——自 2026-06-06 14:41 commit e5d27b9
> 把 SHEET_ID 從前台 Sheet 改成後台 Sheet 起就壞了（改的目的是讓 db.py 的 orders/ingredients 讀對 Sheet，
> 但 SHEET_ID 一個常數同時餵 gws laiten 功能與 GOOGLE_SHEETS_ID 環境變數，兩個用途需要的是不同 Sheet）。

### 工作表欄位結構

**orders（後台 Sheet，db.py 管理，14 欄）**
`id, 建立時間, 姓名, 電話, 生日, 時辰, 心願主項, 心願細項, 備註, 狀態, 八字分析, 選用食材, 小卡文案, 五行建議`
- 程式碼中出現的狀態值流轉：`待處理` →（/admin/api/analyze）→ `分析完成` →（/admin/api/generate_card）→ `文案完成`
- `選用食材`、`五行建議` 存 JSON 字串（detail 頁解析 `suggestion` JSON）

**ingredients（後台 Sheet，db.py 管理，9 欄）**
`食材名稱, 主五行, 副五行, 用途, 季節, 顏色分析, 氣味分析, 屬性分析, 備注`
- 食材名稱為唯一鍵（save 前查重、update/delete 以名稱定位列）

**品牌設定（key-value 兩欄，A2:B20）**
keys：`tagline, subtitle, cta_text, cta_url_bazi, cta_url_tea, {line_id}_name, {line_id}_subtitle`
- `cta_url_bazi` / `cta_url_tea` 存的是 GAS 部署 URL，前台訂單送出端點由此動態取得

**產品主檔（12 欄，A2:L500）**
`line_id, product_id, name, badge, description, price, discount, unit, active, sort_order, images, category`
- line_id 僅兩種：`bazi-cake`、`afternoon-tea`（寫死在 `_load_laiten` 與前台）
- 前台跳過 `active=FALSE` 的列；`images` 逗號分隔多值

**八字蛋糕訂單（前台 Sheet，GAS 寫入，10 欄）**
`時間, name, phone, birthdate, birth_hour, product, quantity, pickup_date, delivery, notes`

**下午茶訂單（前台 Sheet，GAS 寫入，8 欄）**
`時間, company, contact, phone, items, event_date, total_qty, notes`

---

## 後台路由 → 依賴（back/admin.py，port 5001）

| 路由 | Template | db.py 函式 | Sheets 讀寫 | Claude API |
|------|----------|-----------|------------|-----------|
| `GET /` | —（redirect /admin） | — | — | — |
| `GET /admin` | admin/index.html | load_orders | 讀 orders | — |
| `GET /admin/order/<id>` | admin/detail.html | load_orders | 讀 orders | — |
| `GET /admin/ingredients` | admin/ingredients.html | — | — | — |
| `GET /admin/api/ingredients` | —（JSON） | load_ingredients | 讀 ingredients | — |
| `POST /admin/api/classify` | —（JSON） | — | — | sonnet：食材五行判斷 |
| `POST /admin/api/ingredient/save` | —（JSON） | save_ingredient | 寫 ingredients（append） | — |
| `POST /admin/api/ingredient/update` | —（JSON） | update_ingredient | 寫 ingredients（整列 A:I） | — |
| `POST /admin/api/ingredient/delete` | —（JSON） | delete_ingredient | 刪 ingredients 列 | — |
| `POST /admin/api/analyze` | —（JSON） | update_order_fields | 寫 orders：八字分析/五行建議/狀態 | opus：八字主分析 ＋ sonnet：JSON 萃取 |
| `POST /admin/api/generate_card` | —（JSON） | update_order_fields | 寫 orders：選用食材/小卡文案/狀態 | sonnet：小卡文案 |
| `GET /admin/print` | admin/print.html | load_orders | 讀 orders（篩有 card_text 者） | — |
| `GET /admin/laiten` | —（redirect brand） | — | — | — |
| `GET/POST /admin/laiten/brand` | admin/laiten_brand.html | — | gws 讀寫 品牌設定 | — |
| `GET/POST /admin/laiten/products/<line_id>` | admin/laiten_products.html | — | gws 讀寫 品牌設定＋產品主檔 | — |
| `GET/POST /admin/laiten/images` | admin/laiten_images.html | — | —（本機 laiten_public/images/ 上傳/刪除） | — |
| `GET /admin/laiten/image/<filename>` | —（檔案） | — | —（本機 images 目錄） | — |
| `GET/POST /admin/laiten/sync` | admin/laiten_sync.html | — | gws 讀 品牌設定＋產品主檔 → 產 products.js → git add/commit/push（觸發 Netlify 部署） | — |

> 注意：`laiten_brand` / `laiten_products` 的 POST 都呼叫 `_save_laiten`，是 **clear + 整份重寫** `品牌設定!A1:B20`、`產品主檔!A1:L500` 兩張 tab——改任一頁面都會覆寫兩張 tab 全部內容，且上限 500 列。

### 模型對照（admin.py 內呼叫點）
| 呼叫點 | 模型 | 用途 |
|--------|------|------|
| `/admin/api/classify` | claude-sonnet-4-6 | 食材五行 JSON 判斷（system prompt 內含五行體系） |
| `/admin/api/analyze` 第一段 | claude-opus-4-8 | 八字命盤主分析（文字） |
| `/admin/api/analyze` 第二段 | claude-sonnet-4-6 | 從分析文字萃取設計建議 JSON（base_color/layer1/layer2/topping/avoid） |
| `/admin/api/generate_card` | claude-sonnet-4-6 | 小卡文案（100 字內） |

API 金鑰來源：`anthropic.Anthropic()` 預設讀環境變數 `ANTHROPIC_API_KEY`（專案根有 `API_Key.txt`，與程式無 import 關係）。

---

## Template / 前端 JS → 後台 API 呼叫

| Template | fetch 呼叫的 API |
|----------|-----------------|
| admin/index.html | —（純連結導覽：/admin、/admin/ingredients、/admin/print、/admin/laiten/*、Netlify 前台網址） |
| admin/detail.html | `/admin/api/analyze`、`/admin/api/generate_card` |
| admin/ingredients.html | `/admin/api/ingredients`、`/admin/api/classify`、`/admin/api/ingredient/save`、`/admin/api/ingredient/update`、`/admin/api/ingredient/delete` |
| admin/print.html | —（伺服器端渲染） |
| admin/laiten_brand.html / laiten_products.html / laiten_images.html / laiten_sync.html | —（傳統 form POST 回自身路由） |

detail.html 另接收 server 端注入的 `FOOD_DATA`（admin.py 內寫死的五行→食材選項字典）與 `suggestion` JSON，供師傅勾選食材。
**FOOD_DATA 是寫死在 admin.py 的，與 ingredients 工作表内容互相獨立、不同步**——食材管理頁新增的食材不會自動出現在訂單詳情的選項裡。

---

## 前台（laiten_public，Netlify 靜態部署）依賴鏈

```
index.html
 ├─ 讀：前台 Sheet(1xtuK…) gviz CSV export（品牌設定、產品主檔）→ 渲染品牌文案/產品卡/表單選項
 ├─ 從 品牌設定 取 cta_url_bazi / cta_url_tea（= GAS Web App URL）
 ├─ 八字蛋糕表單 → POST(no-cors) GAS_URL_BAZI（欄位：name, phone, birthdate, birth_hour, product, quantity, pickup_date, delivery, notes, type=bazi）
 └─ 下午茶表單 → POST(no-cors) GAS_URL_TEA（欄位：company, contact, phone, event_date, notes, items, total_qty, type=tea；前端檢核最低 30 份）

gas_order_handler.js（部署在 Google Apps Script，不在本 repo 執行）
 ├─ doPost：type=bazi → appendRow 八字蛋糕訂單；type=tea → appendRow 下午茶訂單
 └─ MailApp 寄通知信到 yuchin@ulinjia.net
```

> ⚠️ `laiten_public/products.js`（由 /admin/laiten/sync 生成、隨 git push 部署）**目前 index.html 並未引用**，前台一律走 gviz 即時讀取。products.js 疑似死產物或備援，用途**待 Olina 確認**。

---

## db.py 函式 → 被誰依賴（改這裡會波及誰）

| 函式 | 操作的 tab / 欄位 | 呼叫者 |
|------|------------------|--------|
| load_orders | orders 全表讀 | /admin、/admin/order/<id>、/admin/print |
| get_next_order_id | orders 第 1 欄 | create_order |
| create_order | orders append（14 欄） | back/app.py `/submit`（疑似停用，見人工補充區） |
| update_order_fields | orders 第 10–14 欄（status/bazi_result/ingredients/card_text/suggestion） | /admin/api/analyze、/admin/api/generate_card |
| load_ingredients | ingredients 全表讀 | /admin/api/ingredients |
| ingredient_exists | ingredients 第 1 欄 | save_ingredient |
| save_ingredient | ingredients append | /admin/api/ingredient/save |
| update_ingredient | ingredients 整列 A:I | /admin/api/ingredient/update |
| delete_ingredient | ingredients 刪列 | /admin/api/ingredient/delete |
| init_sheets | 建 orders / ingredients tab 與標題列 | 無呼叫者（部署時手動執行一次） |

> orders 欄位順序是隱性契約：`ORDERS_HEADER`（db.py）、`_row_to_order` 的索引、`update_order_fields` 的 `col_map`（10–14）、`create_order` 的 append 順序，四處必須同步改。ingredients 同理（9 欄、A:I）。

---

## 疑似遺留（legacy）檔案

| 檔案 | 狀態 | 證據 |
|------|------|------|
| back/app.py | 疑似停用的舊版前台訂單表單（port 5000） | 引用的 `order_form.html`、`success.html` 不存在於 templates/；未設定 `GOOGLE_SHEETS_ID` 環境變數（db 連線會拿到空 ID）；現行客戶下單走 laiten_public + GAS |
| ingredient_web.py | 舊版食材判斷工具（寫 Excel，port 5001 與 admin.py 衝突） | 寫入 bazi_cake.xlsx，而現行食材管理走 /admin/ingredients + Google Sheets |
| ingredient_classifier.py | 舊版 CLI / ingredient_web.py 的依賴 | 同上，寫 bazi_cake.xlsx；其 system prompt 已被複製進 admin.py `/admin/api/classify` |
| setup_excel.py | 建 bazi_cake.xlsx 的一次性腳本 | 其 orders 欄位（18 欄含取件日期/出生地）與現行 Sheets orders（14 欄）不一致，僅為舊 Excel 時代產物 |
| laiten_public/products.js | 由 sync 生成但前台未引用 | index.html 無 `<script src="products.js">` 也無 `PRODUCTS_DATA` 引用 |

是否可刪除——**待 Olina 確認**，SA 不擅自處置。

---

## 人工補充區（此區由 SA 手動維護）

記錄程式碼掃描抓不到的「業務層級」依賴與已知技術債。

### 跨系統耦合
- **GAS 端點是隱性依賴**：前台表單欄位（index.html）↔ gas_order_handler.js 的 `e.parameter` 欄位名必須一致；但 GAS 程式碼部署在 script.google.com，repo 內這份只是副本。改前台表單欄位時，必須同步重新部署 GAS（新增版本），且 repo 副本要跟著更新。
- **品牌設定的 cta_url_bazi / cta_url_tea 是前台訂單功能的開關**：清空或填錯 → 前台送單靜默失敗（sendToGAS 對空 URL 只 console.warn，客人看到的仍是成功畫面 →「假成功」風險）。後台 brand 頁改這兩欄要特別小心。
- **gviz CSV 讀取要求前台 Sheet 對「知道連結的任何人」可讀**：權限被改動會讓前台整頁產品/品牌資料消失（程式碼看不出權限設定，營運面依賴）。
- **/admin/laiten/sync 會執行 git add laiten_public + commit + push**：images 上傳/刪除也靠這條路徑部署到 Netlify。git remote / Netlify 綁定是程式外依賴。

### 隱性契約（改欄位時的迴歸對象）
- orders 欄位順序四處同步（ORDERS_HEADER / _row_to_order / col_map / create_order append）——改 orders 欄位＝全部後台訂單頁迴歸。
- 產品主檔 12 欄順序三處同步：admin.py `_load_laiten`（讀，含 row[8] active、row[10] images）、`_save_laiten`（寫）、index.html `loadData`（gviz 讀，同樣的 index）。
- AI 回傳 JSON schema 是隱性契約：`/admin/api/analyze` 萃取的 `base_color_wuxing/layer1_wuxing/layer2_wuxing/topping_wuxing/avoid_wuxing` 被 detail.html 的食材勾選 UI 使用；改 prompt 要連 detail.html 一起迴歸。
- detail.html 的 FOOD_DATA（admin.py 寫死）與 ingredients 工作表互不同步——未來若要「訂單詳情選項吃食材庫」需專案處理。

### 2026-06-13 調查結論（gws 唯讀實查 + git 考古，已驗證）
- **後台 Sheet 無 品牌設定/產品主檔 tab**：admin laiten 三頁（brand/products/sync 的讀取段）自 6/6 14:41（e5d27b9）起讀寫不存在的 tab，錯誤被吞、看似正常。根因：admin.py 單一 `SHEET_ID` 常數同時服務「gws laiten tab」與「db.py 的 GOOGLE_SHEETS_ID」兩個用途，但兩者需要不同 Sheet。修法：拆成兩個常數（`LAITEN_SHEET_ID = 1xtuK…`、`GOOGLE_SHEETS_ID = 1oYJ7…`），或合併 Sheet 後統一。
- **前台 index.html 自 6/6 20:46 推版後整站下單功能中斷（P0）**：commit 9f1f676 把 HERO 改成 banner 圖、移除了 `id="hero-tagline"` / `id="hero-desc"` 元素，但 `loadData()` 第 367-368 行仍對其賦值 → TypeError → `renderProducts / buildBaziSelect / buildTeaItems` 全部不執行 → 八字表單品項下拉為空（required 擋送出）、下午茶品項清單為空（總數 0 < 30 擋送出）。**目前正式站客人根本送不出單**（已部署的 origin/main 同樣有此 bug）。GAS_URL 賦值在崩潰點之前所以仍會載入，但無濟於事。
- **兩條訂單流互不相通（已驗證）**：前台訂單由 GAS 寫入前台 Sheet `八字蛋糕訂單` / `下午茶訂單`（實查有 2026/6/6 13:59 戴寧一筆，證明 GAS URL 有效、寫入正常）；後台 `/admin` 只讀後台 Sheet `orders`（實查只有 5/18 測試單一筆）。**全 codebase 沒有任何程式讀 `八字蛋糕訂單` / `下午茶訂單` 兩張 tab**——前台訂單永遠不會出現在後台。
- **後台 orders tab 標題列與資料錯位**：標題列是舊版 18 欄 schema（訂單編號/建立日期/取件日期/出生地/底色/夾層…），資料列卻是新版 14 欄 schema（db.py ORDERS_HEADER）。db.py 跳過標題列按位置讀所以程式沒事，但**人工直接在 Sheet 上對著標題填資料必錯位**。
- **前台 Sheet 個資公開風險**：gviz 讀取要求前台 Sheet「知道連結者可檢視」，而客人訂單（姓名/電話/生日）就寫在同一份 Sheet 的訂單 tab——目前任何拿到連結的人都能讀到客人個資。
- **前台訂單表單沒有「心願」欄位**：後台八字分析 prompt 依賴 `心願主項/心願細項`，但前台表單（index.html）完全沒收集心願——就算接通訂單流，分析流程也缺輸入。業務缺口，待 PM/Olina 定義。
- **GAS URL 現況**：`cta_url_bazi` 與 `cta_url_tea` 都有值且為**同一個** GAS 部署 URL（doPost 內依 type 分流，設計上合法）。
- **monthly tab（後台 Sheet）有 12 個月備料建議資料，零程式引用**——setup_excel.py 舊 Excel 時代搬入，純人工參考用。
- **products.js 為死產物**：index.html 未引用；現存內容是 6/6 舊資料（tagline「山交手作」= 當時的程式預設值），與前台 Sheet 現況不符。但 `/admin/laiten/sync` 的 git push 同時是 images/index.html 部署到 Netlify 的唯一管道，**砍 products.js 生成段時不可砍掉 sync 的 git push 功能**。

### 2026-06-13 Task1 影響分析新增（SA 實測）
- **service_account 權限現況（Drive API 唯讀實測）**：`bazi-cake-service@bazi-cake.iam.gserviceaccount.com` 對前台 Sheet（1xtuK…）**可讀不可寫**（canEdit=False，讀取可能依賴「知道連結者可檢視」的公開分享）、對後台 Sheet（1oYJ7…）**可讀寫**（canEdit=True）。營運面依賴：關閉前台 Sheet 公開權限前，任何依 service_account 讀前台 Sheet 的程式（搬移腳本）會先斷。
- **qa_smoke_test.py 基線現況**：36 PASS + 1 SKIP（2026-06-13 實跑全綠）。基線 import 五個模組且 import 失敗即 sys.exit——刪任何 .py 檔必先同步改 MODULES 清單，否則整套基線中斷。
- **Task1 裁定**：db.py 的 `create_order` / `get_next_order_id` 保留（Phase 2 收件匣轉單複用，新呼叫者 `/admin/inbox/convert`）；Phase 4 死碼清單為 back/app.py、ingredient_web.py、ingredient_classifier.py、setup_excel.py 四檔。
- **index.html 三 Phase 共改**：Phase 0（loadData 防護）→ Phase 1（loadData 整段改吃 products.js）→ Phase 3（sendToGAS 失敗顯示）依序動同一個 `<script>` 區塊，不可平行；Phase 1 起 products.js 從死產物轉為前台正式資料來源（本檔上方「products.js 為死產物」的描述屆時失效，Task1 完成後更新）。

### 待 Olina 補充（業務層級，程式碼看不出來）
1. `品牌設定` / `產品主檔` 在兩份 Sheet 各一份：後台編輯的是後台 Sheet（1oYJ7…），前台讀的是前台 Sheet（1xtuK…）。兩份之間如何同步？是手動複製、還是後台 gws 其實該指向前台 Sheet？（若無同步機制，後台編輯功能形同無效）
2. `products.js` 的實際用途（前台未引用）；`/admin/laiten/sync` 的「推送完成」對營運的真正意義。
3. orders `狀態` 欄除了程式碼出現的 待處理/分析完成/文案完成，是否還有人工填寫的其他狀態（如已交付/取消）？狀態的業務流程定義。
4. 前台 GAS 訂單（八字蛋糕訂單/下午茶訂單 tab）與後台 orders tab 之間的關係：目前看是**兩條互不相通的訂單流**——客人 GAS 下單後，師傅是否手動轉謄進後台 orders？
5. back/app.py 舊版下單入口是否確定棄用、可否刪除。
6. ingredients `季節`、`用途` 欄位的業務規則（誰消費這些欄位？目前僅 UI 顯示，未參與任何邏輯）。
7. monthly 工作表（setup_excel.py 舊 Excel 內有「月份備料建議」）在現行 Sheets 是否還存在/使用。
