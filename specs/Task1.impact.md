# Task1 影響範圍分析（SA）

> SA 撰寫於 2026-06-13。依據：`specs/Task1_Blueprint.md`、`specs/SYSTEM_MAP.md`、
> 程式碼實查（index.html / db.py / admin.py / qa_smoke_test.py）、
> service_account 權限唯讀實測（Drive API capabilities + Sheets values.get，未寫入任何資料）。

## 涉及範圍標記（pipeline 走向）

- **含 UI**：backend 完成後建 `Task1.backend_done` → frontend → `Task1.done` → QA。
  - 後端：admin.py（常數拆分、錯誤吞噬修正、inbox 路由、品牌存檔警告）、db.py、gas_order_handler.js 副本、qa_smoke_test.py、Sheets 搬移腳本。
  - 前端：laiten_public/index.html（Phase 0 修復、Phase 1 改吃 products.js、Phase 3 送單失敗顯示）、templates/admin/*（Phase 2 收件匣頁、Phase 3 品牌頁警告 UI）。
- **Phase 0 例外**：Phase 0 是純前端 JS 修復，無後端變更。依 Blueprint 指示 Phase 0 先單獨走完 pipeline 上線。實務建議：Phase 0 由 backend 收到 `.sa_done` 後直接建 `.backend_done`（後端零變更）交 frontend 修，或由 main session 協調直接派 frontend——以不卡 P0 上線為原則。

---

## 裁定一：create_order / get_next_order_id 去留（決策 5 vs Phase 2 衝突）

**裁定：保留。Phase 4 不刪這兩個函式，Phase 2 轉單複用它們。**

理由（已實查 db.py:119-145）：
1. `create_order` 正是「取號 + 按 ORDERS_HEADER 14 欄順序 append + 狀態=待處理」的完整封裝，與 Phase 2 轉單需求（spec 欄位映射表）一對一吻合：心願主項/細項即 `wish_main/wish_sub` 參數，八字分析等 4 欄它本來就留空。
2. 重寫一份 append + 取號邏輯，等於把 SYSTEM_MAP 已標記的「orders 欄位順序四處同步」隱性契約擴成五處，純增風險。
3. 「孤兒」的定義在 Phase 2 上線後即不成立——它將獲得新呼叫者 `/admin/inbox/convert`。

**附帶條件**：
- 若 Olina 對 D3 拍板「建立時間用前台下單時間」，backend 需給 `create_order` 加一個**選填參數** `created_at=None`（預設取 now），不可改既有參數順序。
- 取號邏輯（D2）若 Olina 拍板沿用流水號，`get_next_order_id` 原樣複用；若要日期前綴等業務編碼，改動點集中在 `get_next_order_id` 一處即可，這也是保留它的好處。
- Phase 4 的刪除清單修正為：**只刪 back/app.py、ingredient_web.py、ingredient_classifier.py、setup_excel.py 四檔**。db.py 不動（僅 docstring 提到 app.py，順手改掉即可）。

---

## 裁定二：Phase 0 獨立性確認

**結論：可以獨立出貨，但與 Phase 1 動同一個函式，必須序列化，不可平行開發。**

實查 index.html：
- Phase 0 的修復點在 `loadData()`（355-400 行）內 367-368 行。已逐一核對 `loadData` 引用的全部 DOM id：**只有 `hero-tagline` / `hero-desc` 兩個元素不存在**（9f1f676 移除），其餘 `btn-bazi-cake`（121）、`btn-afternoon-tea`（125）、`bazi-subtitle`（133）、`bazi-products`（135）、`tea-subtitle`（149）、`tea-products`（151）、`bazi-product-select`（213）、`tea-items-list`（297）全部存在。Phase 0 的「根除同類 TypeError」即：367-368 加存在性防護＋對 389-392 等其餘賦值套同樣防護寫法，範圍封閉。
- **與 Phase 1 的重疊**：Phase 1 要把同一個 `loadData()` 從 fetchSheet（gviz）改成讀 products.js——會**整段重寫 Phase 0 剛改過的程式碼**。順序執行沒問題（先修後改），平行開發必衝突。
- **與 Phase 3 的重疊**：Phase 3-B 改 `sendToGAS()`（572-579 行）與送單 handler（540-569 行），不同函式但同一個 `<script>` 區塊、同一檔案。
- **與後端 / 冒煙基線**：Phase 0 不動任何 .py；qa_smoke_test 對 index.html 的檢查（Smoke-6）是「products.js 或 fetchSheet 擇一存在」，Phase 0 保留 fetchSheet → **36 項基線零影響**。

**協調建議**：
1. Phase 0 改完 → QA → Olina 推版上線（M1）→ **commit 落定後**才允許 Phase 1 動 index.html。
2. Phase 1 重寫 loadData 時，**必須保留 Phase 0 建立的「元素存在才賦值」防護模式**（Phase 1 仍會對同一批 DOM id 賦值，砍掉防護等於把 P0 bug 的土壤種回去），QA 在 Phase 1 驗收時把「Console 無 TypeError」列為迴歸項。
3. Phase 0 嚴格只做 JS 防護，不順手動 fetchSheet / sendToGAS / 任何 .py（Blueprint 已明示，這裡重申為 QA 檢查點）。

---

## service_account 權限實測結果（決定 M2 走向）

實測方式：Drive API `files.get(capabilities)` + Sheets API `values.get`（皆唯讀 scope，未寫入）。
service_account：`bazi-cake-service@bazi-cake.iam.gserviceaccount.com`

| Sheet | 讀取 | 寫入（canEdit） |
|-------|------|----------------|
| 前台 Sheet（1xtuK…「Laiten 系統主檔」） | ✅ 可讀（已實測讀回 `品牌設定!A1:B3`，四張 tab 名稱確認） | ❌ **False，不可寫** |
| 後台 Sheet（1oYJ7…「八字蛋糕資料庫」） | ✅ | ✅ **True，可寫** |

**結論：M2 不需要 Olina 手動搬。** 搬移需求是「讀前台 + 寫後台」，service_account 兩項都具備。backend 可寫一次性搬移腳本（讀 1xtuK 四 tab → 在 1oYJ7 建同名 tab 寫入；遇同名 tab 中止，不覆寫 orders/ingredients；前台原 tab 不刪，照 Blueprint 保留為回滾備援）。

**兩個注意**：
1. 前台 Sheet 的「可讀」可能來自「知道連結者可檢視」的公開分享（gviz 本來就依賴它），不一定是直接分享給 service_account。因此 **M6（關閉前台 Sheet 公開權限）必須在搬移完成且驗收通過之後執行**，順序顛倒會讓搬移腳本讀不到資料。若 Olina 想提前關公開權限，需先把前台 Sheet 直接分享 viewer 給上述 service_account email。
2. 前台 Sheet 不可寫也意味著：Phase 2 的 D5（防重複轉單標記）若拍板「在來源 tab 加狀態欄」，**搬移後的訂單 tab 已在後台 Sheet（可寫），沒有問題**；但搬移前任何「寫回前台 Sheet」的方案都不可行。D5 兩個選項技術上都通，僅供 Olina 拍板參考。

Phase 4 的 M4（orders 標題列修正）同理：後台 Sheet canEdit=True，**backend 可程式修正標題列，不需 Olina 手動**（仍遵守「只改標題列第 1 列、不動資料列」）。

---

## 受影響的既有功能總表

| Phase | 功能 / 位置 | 影響說明 | 需迴歸測試 |
|-------|------------|---------|-----------|
| 0 | 前台整站（index.html loadData） | 修 TypeError 恢復 renderProducts/buildBaziSelect/buildTeaItems | ✅ 前台送單全流程 |
| 1 | 後台 brand / products / sync 三頁（admin.py `SHEET_ID`、`_gws_*`） | 常數拆分 + 錯誤不再吞噬：三頁從「假正常」變真讀寫；錯誤路徑行為改變 | ✅ 三頁讀寫 + 刻意造錯案例 |
| 1 | db.py 全部函式（經 `GOOGLE_SHEETS_ID`） | 環境變數仍指 1oYJ7 不變，理論零影響，但 admin.py 第 17-19 行是它的唯一來源，拆常數時不可改值 | ✅ /admin 訂單列表、食材管理 |
| 1 | 前台 index.html（fetchSheet → products.js） | 資料來源整段重寫；gviz 移除 | ✅ 品牌文案/產品卡/表單選項/GAS URL 渲染 |
| 1 | /admin/laiten/sync 的 git push 段 | products.js 從死產物變正式來源；**git add/commit/push 不可動**（images/index.html 部署唯一管道） | ✅ sync 全流程 |
| 1 | GAS（線上 + repo 副本） | SHEET_ID 改指 1oYJ7；M3 由 Olina 重新部署 | ✅ 測試單寫入合併後 Sheet |
| 2 | db.py create_order / get_next_order_id | 獲得新呼叫者 /admin/inbox/convert（見裁定一） | ✅ 轉單後 /admin、/admin/order/<id>、analyze |
| 2 | 後台導覽（admin/index.html） | 新增收件匣入口連結 | ❌（純新增） |
| 2 | orders tab | 轉單寫入新列；狀態=待處理 進既有分析流程 | ✅ analyze / generate_card |
| 3 | /admin/laiten/brand POST（`_save_laiten`） | 存檔前加空值警告攔截；clear+整份重寫行為不變 | ✅ 正常存檔路徑 |
| 3 | 前台 sendToGAS + 送單 handler | 失敗路徑從靜默變可見；成功路徑不可變 | ✅ 正常送單成功路徑 |
| 4 | qa_smoke_test.py | 大改（見下方基線清單） | ✅ 全基線重跑 |
| 4 | orders tab 標題列 | 18 欄舊標題 → 14 欄 ORDERS_HEADER；程式按位置讀不受影響 | ✅ /admin 列表照常 |
| 4 | bazi_cake.xlsx | 比對後依 M5 處置；刪除前 Olina 點頭 | — |

---

## qa_smoke_test.py 基線影響清單（現況 36 PASS + 1 SKIP，2026-06-13 實跑確認全綠）

### Phase 0：**零影響**
Smoke-6「index.html 基本檢查」是 `products.js 或 fetchSheet 擇一`，Phase 0 保留 fetchSheet，36 項全部不動。backend/frontend 不需改基線。

### Phase 1：直接打破 0 項，但有 4 個必須同步處的點
| 基線項 | 影響 | backend 同步動作 |
|--------|------|-----------------|
| 攔截器設定段（88-91 行 `admin._gws_read = lambda range_: []` 等） | `_gws_*` 簽名或回傳格式若改（如改回 (ok, data) 或拋例外），mock 立刻失真 | 改 `_gws_*` 介面時同步改 mock；保持「空資料=合法、API 錯誤=可見失敗」兩種語意可區分 |
| Smoke-3 GET /admin/laiten/brand、products/bazi-cake、products/afternoon-tea、sync | 錯誤不再吞噬後，mock 回空 list 的 GET 仍應 200（空資料≠錯誤）；若實作把空讀當錯誤會 FAIL | 區分「讀到空」與「API 非 200」 |
| Smoke-6 index.html 基本檢查 | 仍會 PASS（products.js 出現），但「擇一」斷言在 Phase 1 後形同虛設 | **收緊為必須引用 products.js 且不得殘留 fetchSheet/gviz URL** |
| Smoke-6 products.js 可解析 | products.js 轉正式來源；brand 需含 cta_url_bazi/cta_url_tea、tagline 等前台必需 key | 加斷言：brand 必含 spec 列出的必要 key；資料結構若改名（PRODUCTS_DATA）測試同步 |

### Phase 2：直接打破 1 項（模板），另 3 處需同步
| 基線項 | 影響 | backend 同步動作 |
|--------|------|-----------------|
| Smoke-5 admin.py 模板完整性 | 新路由 render 新模板，**模板沒落地就會 FAIL**（backend_done 前模板由 frontend 補——backend 階段先放最小占位模板或協調好順序） | 確保 inbox 模板與路由同 commit 落地 |
| Smoke-2 admin 路由表 expected 集合 | 只檢缺不檢多，新增路由不會 FAIL，但等於零覆蓋 | expected 加入 `/admin/inbox`、`/admin/inbox/convert` |
| 攔截器段 121 行 `db.create_order = _make_blocker(...)` | 裁定一保留並複用後，若新增 convert 的 POST 冒煙案例，blocker 會誤殺 | 把 create_order 從 blocker 改為回傳假 id 的 mock；get_next_order_id 同理 |
| （新增）讀取訂單 tab 的新 db/gws 函式 | 無現成 mock | 新函式一律加 mock + 新增 GET /admin/inbox 冒煙項 |

### Phase 3：直接打破 0 項
- 品牌頁 POST 目前完全無冒煙覆蓋；警告機制上線後**建議新增** POST /admin/laiten/brand 空 cta_url 的攔截案例（依 D6 結論斷言行為）。
- index.html 的 sendToGAS 變更不在任何基線斷言內，Smoke-6 不受影響。

### Phase 4：直接打破 9 項，其中 import 失敗會讓整套基線中斷
| 基線項 | 現況 | Phase 4 後 |
|--------|------|-----------|
| Smoke-1 import app | PASS | **FAIL 且 sys.exit(1) 整套中斷**（74-76 行 import 失敗即停）——MODULES 必須改為 `["db", "admin"]` |
| Smoke-1 import ingredient_classifier | PASS | 同上，移除 |
| Smoke-1 import ingredient_web | PASS | 同上，移除 |
| Smoke-2 app.py（舊版前台）路由表 | PASS | 移除（含 80-82 行 imported 取用） |
| Smoke-2 ingredient_web 路由表 | PASS | 移除 |
| Smoke-4 GET /（食材判斷頁） | PASS | 整個 Smoke-4 區段移除 |
| Smoke-4 GET /ingredients（唯讀 xlsx） | PASS | 同上（xlsx 若依 M5 刪除，25 行 os.chdir 註解、13 行 openpyxl 說明一併清） |
| Smoke-4 POST /classify（空輸入驗證） | PASS | 同上 |
| Smoke-5 app.py 模板完整性 | SKIP | 移除（KNOWN_LEGACY_MISSING、相關 regex 段一併清） |
- 93 行 `ingredient_classifier.anthropic.Anthropic = _BlockedAnthropic` 也要移除。
- db.create_order / get_next_order_id 依裁定一**保留**，121 行不因 Phase 4 變動（已在 Phase 2 改為 mock）。
- **Phase 4 後基線 PASS 數：36 − 8 = 28**（再加 Phase 1-3 新增項後為最終基線數，backend 在 .done 前實跑一次並把新基線數寫進測試檔頭註解）。

---

## Backend 注意事項

1. **admin.py 第 17-19 行是 db.py 的生命線**：`os.environ["GOOGLE_SHEETS_ID"] = SHEET_ID` 在 import db 之前執行才有效。拆常數時兩個用途最終都指 1oYJ7（合併後），但請拆成兩個明名常數（如 `LAITEN_SHEET_ID` / `BACK_SHEET_ID`）讓未來再分家時只改一處。
2. **搬移腳本**：service_account 讀前台/寫後台權限已實測具備（見上）。腳本要件：同名 tab 存在即中止、不刪前台原資料、輸出逐欄比對結果供 QA 驗收條件 1。
3. **`_save_laiten` 是 clear+整份重寫**（admin.py 482-505），Phase 3-A 的警告要攔在 clear 之前，不可 clear 完才發現要警告。
4. **sync 的 git push 段不可動**（Blueprint 已明示；qa_smoke 95 行有 subprocess blocker 保險）。
5. Phase 2 開工前置：D1/D3/D4/D5 需 Olina 回覆（Blueprint 待確認表）。D3 若選「前台下單時間」→ create_order 加選填參數（見裁定一附帶條件）。
6. orders 標題列修正（4.4）可程式做（canEdit 已實測 True），只動第 1 列。

## Frontend 注意事項

1. Phase 0 只動 index.html 的 `loadData()` 防護，**不碰 fetchSheet/sendToGAS/任何後端**；改完後 Console 無 TypeError、四個渲染函式都執行。
2. Phase 1 重寫 loadData 時保留存在性防護模式（裁定二協調建議 2）。
3. Phase 2 收件匣頁遵循後台既有模板風格（templates/admin/*）；轉單表單「心願主項」必填。
4. Phase 3-B 受 no-cors 技術限制：可偵測的失敗只有「URL 為空」與「fetch reject/timeout」，GAS 端寫入失敗（HTTP 層成功）偵測不到——失敗顯示覆蓋前兩者即可，這是技術上限，QA 驗收條件 3 以「模擬網路層失敗」為準。備援聯絡方式等 D7。

## QA 迴歸測試清單

- [ ] （每 Phase）`python qa_smoke_test.py` 全綠，基線數與測試檔頭註解一致
- [ ] Phase 0：前台 Console 無 TypeError、品項下拉/下午茶清單/產品卡有內容、GAS_URL 已載入
- [ ] Phase 1：後台 brand/products 讀寫真實生效（非預設值）、造錯案例可見失敗、sync 產出完整 products.js 且 git push 正常、前台改吃 products.js 後渲染正確且無 gviz 請求、**Console 無 TypeError（Phase 0 防護未被重寫掉）**
- [ ] Phase 1：/admin 訂單列表與食材管理頁照常（GOOGLE_SHEETS_ID 未被拆壞）
- [ ] Phase 2：轉單後 14 欄映射正確、/admin/order/<id> 可開、analyze 可跑、重複轉單被擋、/admin 既有訂單列表照常
- [ ] Phase 3：空 cta_url 存檔有警告（依 D6）、前台失敗顯示備援、**正常送單成功路徑不變**、正常品牌存檔路徑不變
- [ ] Phase 4：四檔已刪無殘留引用、create_order/get_next_order_id 保留且 grep 確認 inbox 有引用、orders 標題列 14 欄且資料列未動、基線 28+ 項全綠
- [ ] Sheets 驗證一律用測試資料，不污染正式訂單（workflow.md QA 規範）

## 給 PM 的建議（不拆 Task，但有一個信號流風險）

維持單一 Task1 依 Phase 順序交付可行。唯一風險：Phase 0 走完整圈 pipeline（→tested→Olina 驗收）期間，Task1 的信號檔會被 Phase 0 消費掉，Phase 1-4 開工時 backend 沒有觸發信號。建議 main session 協調方式二擇一：(a) Phase 0 驗收後由 PM 重建 `Task1.ready`→SA 快速確認→`Task1.sa_done`（本 impact 已涵蓋，SA 秒回）；(b) 直接約定 Phase 0 的 `.tested` 被 Olina 驗收後，main 口頭委派 backend 進 Phase 1。擇 (b) 較省事。
