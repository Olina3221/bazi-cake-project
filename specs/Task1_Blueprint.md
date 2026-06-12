# Task1 Blueprint — 萊點（Laiten）前台修復 × Sheet 合併 × 訂單橋接 × 死碼清理

> PM 撰寫於 2026-06-13。依據：`specs/SYSTEM_MAP.md`（2026-06-13 SA 深度調查，已 gws 唯讀實查 + git 考古驗證）與 Olina 2026-06-13 拍板決策。
> **2026-06-13 更新**：Olina 拍板 D1（下午茶獨立管理 tab）、D4（orders 擴欄 18 欄）、D7（送單失敗備援電話 0918-235-714）。詳見文末「已拍板決策」與各 Phase 對應段落。
> **2026-06-13 二次更新（Phase 0/1 已上線驗收完成）**：Olina 拍板 D2（訂單編號改日期前綴 `YYYYMMDD-NN`）、D3（轉單建立時間用前台下單時間）、D5（防重轉＝來源 tab 加「已轉入」欄）、D6（品牌頁 cta_url 空值禁止存檔）。**D2 推翻了 SA 裁定一「get_next_order_id 直接複用」的前提，取號邏輯需改寫**——詳見 Phase 2「D2 拍板：訂單編號日期前綴」。D8（訂單完整狀態流程）仍未拍板，Phase 2 狀態欄採暫定可擴充設計。
> 本 Blueprint 涵蓋多個交付物，**以 Phase 標示交付順序**。Phase 0（P0 修復）必須最先單獨跑完 pipeline 並上線驗收，不得被後面的大合併卡住。

---

## 交付順序總覽（重要）

| Phase | 主題 | 性質 | 上線優先序 |
|-------|------|------|-----------|
| **Phase 0** | 正式站 hero TypeError 修復（P0） | 前端純修 bug | **最高，獨立出貨** |
| **Phase 1** | Sheet 架構合併（四 tab 搬入後台 Sheet、admin.py 雙常數拆分、前台改吃 products.js、GAS 改指向） | 後端為主，含 Olina 手動步驟 | 高 |
| **Phase 2** | 訂單橋接：後台「前台訂單收件匣」轉單頁 | 後端 + 前端 | 中 |
| **Phase 3** | 品牌頁存檔防呆 + 前台送單失敗顯示 | 後端 + 前端 | 中 |
| **Phase 4** | 死碼刪除 + 孤兒函式清理 + orders 標題列修正 + bazi_cake.xlsx 處置 | 後端為主 | 低（但 Phase 1 完成後可並行） |

> **給 SA / backend 的指示**：Phase 0 影響分析與實作優先處理，先讓 Phase 0 走到 `Task1.tested` 並請 Olina 驗收 + 推版上線，再回頭做 Phase 1–4。若 SA 判斷拆成獨立 Task 信號更利於並行，可在 impact 報告建議 PM 拆分，但**預設以單一 Task1 依 Phase 順序交付**。

---

## 涉及範圍

- [x] 後端（admin.py / db.py / GAS 副本 / qa_smoke_test.py / Sheets 結構）
- [x] 前端（laiten_public/index.html、templates/admin/* 新增收件匣頁與防呆 UI）
- [x] **需要 Olina 手動操作的步驟**（集中列於文末「Olina 手動操作清單」，spec 內以 ⚠️OLINA 標記）

---

# Phase 0 — 正式站 hero TypeError 修復（P0）

## 功能描述
修復 `laiten_public/index.html:367-368` 對已不存在的 `hero-tagline` / `hero-desc` 元素賦值造成的 TypeError。此錯誤自 2026-06-06 20:46（commit 9f1f676）起，使 `loadData()` 在崩潰點後的 `renderProducts / buildBaziSelect / buildTeaItems` 全部不執行，導致正式站八字蛋糕品項下拉為空（required 擋送出）、下午茶品項清單為空（總數 0 < 30 擋送出）——**客人目前完全送不出單**。

## 修復內容
- `loadData()` 中對 `hero-tagline` / `hero-desc` 的賦值，改為「先取元素、元素存在才賦值」的防護寫法（避免任一元素被移除就整個 `loadData` 崩潰）。
- 同步審視 `loadData()` 內所有 `document.getElementById(...).xxx = ` 形式的賦值，凡指向 HERO 改版後可能不存在的元素者，一律改為存在性檢查後再賦值（根除同類 TypeError，而非只補這兩行）。
- 不改動 HERO 的 banner 圖設計（9f1f676 的視覺改版保留），只修 JS 對 DOM 的存取。

## 驗收條件（QA 可執行）
1. 本機開啟 `laiten_public/index.html`，瀏覽器 Console **無 TypeError**。
2. 八字蛋糕表單的「品項」下拉**有選項**（來源：產品主檔 active 列）。
3. 下午茶品項清單**有列出品項**，可累加數量。
4. `renderProducts` 已執行：產品卡片區塊有渲染內容（非空白）。
5. （回歸）GAS_URL 仍正確載入（賦值在原崩潰點之前，本就正常，確認未被改壞）。
6. ⚠️OLINA：QA 驗收後，由 Olina 執行 Netlify 推版（見手動清單 M1），上線後實測能送出一張測試單。

> **注意**：Phase 0 只解 TypeError 讓既有 gviz 流程恢復；前台改吃 products.js 是 Phase 1 的事，兩者不可混在 Phase 0 做，以免拖慢 P0 上線。

---

# Phase 1 — Sheet 架構合併（一步到位）

## 功能描述
將前台 Sheet（`1xtuKyod3lOQUmp_D10AhDDGSD4bVxG3TmZudO2S9AMo`）的四張 tab（`品牌設定`、`產品主檔`、`八字蛋糕訂單`、`下午茶訂單`）搬入後台 Sheet「八字蛋糕資料庫」（`1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E`），合併為**單一私有 Sheet**。同時拆解 admin.py 單一 `SHEET_ID` 常數同時服務兩用途的根因，並將前台改為讀 products.js（不再公開 gviz 讀取），GAS 改指向合併後 Sheet。

## 合併後目標狀態
合併後的後台 Sheet 應含以下 tab：
| tab | 來源 | 用途 |
|-----|------|------|
| `orders` | 原後台 Sheet（保留） | 後台正式訂單 |
| `ingredients` | 原後台 Sheet（保留） | 食材庫 |
| `monthly` | 原後台 Sheet（保留，零程式引用，人工參考） | 月份備料建議 |
| `品牌設定` | 由前台 Sheet 搬入 | admin laiten brand 讀寫 |
| `產品主檔` | 由前台 Sheet 搬入 | admin laiten products 讀寫 |
| `八字蛋糕訂單` | 由前台 Sheet 搬入 | 前台 GAS 寫入、後台收件匣讀取（Phase 2） |
| `下午茶訂單` | 由前台 Sheet 搬入 | 前台 GAS 寫入、後台收件匣讀取（Phase 2） |

## 後端變更（admin.py）
1. **拆分常數根因**：移除「單一 `SHEET_ID` 同時餵 gws laiten 功能與 `GOOGLE_SHEETS_ID`」的設計。合併後兩用途指向同一份 Sheet，但 backend 必須讓「gws laiten tab 存取」與「db.py 的 `GOOGLE_SHEETS_ID`」明確指向合併後的後台 Sheet ID（`1oYJ7…`），消除 6/6 e5d27b9 起讀寫不存在 tab 的問題。
2. **錯誤吞噬修正**：`_gws_read`（讀失敗回空 list）、`_gws_write`/`_gws_clear`（不檢查錯誤）目前會把「tab 不存在」整個吞掉，造成「存檔顯示 ok 但什麼都沒寫」。合併後 tab 已存在，但仍應讓 gws 寫入/清除在 API 回非 200 時**拋出可見錯誤**（至少 log + 回傳失敗狀態給前端），不得再靜默假成功。

## 前台變更（index.html）
3. **改吃 products.js，停用公開 gviz 讀取**：
   - index.html 改為 `<script src="products.js">` 引用 + 讀取 products.js 暴露的資料結構（品牌設定 + 產品主檔），渲染品牌文案 / 產品卡 / 表單選項 / GAS URL。
   - 移除 index.html 對前台 Sheet gviz CSV export 的即時讀取。
   - products.js 由既有 `/admin/laiten/sync` 管線生成（sync 讀合併後 Sheet 的 品牌設定 + 產品主檔 → 產 products.js → git push 觸發 Netlify）。Phase 1 起 products.js 從「死產物」轉為「正式資料來源」。
   - **sync 的 git add/commit/push 功能不可動**（它同時是 images / index.html 部署到 Netlify 的唯一管道）。
4. products.js 的資料結構需涵蓋前台目前從 gviz 取得的全部欄位：品牌設定的 `tagline / subtitle / cta_text / cta_url_bazi / cta_url_tea / {line_id}_name / {line_id}_subtitle`，產品主檔 12 欄（且維持 active=FALSE 跳過、images 逗號分隔的既有行為）。

## GAS 變更（副本 + 部署）
5. repo 的 `gas_order_handler.js` 是副本，**真正執行的程式在 Google Apps Script 編輯器**。
   - repo 副本：將 `SHEET_ID` 改為合併後 Sheet（`1oYJ7…`），保持 repo 與線上一致。
   - ⚠️OLINA：實際生效需在 Apps Script 編輯器改 `SHEET_ID` 並**重新部署（新增版本）**（見手動清單 M3）。

## ⚠️OLINA 手動 / 權限前置
6. **tab 搬移權限**：合併動作（把前台 Sheet 四 tab 複製進後台 Sheet）需確認 `service_account` 對**前台 Sheet 有讀取權限、對後台 Sheet 有寫入權限**。
   - backend 在影響分析 / 實作前先確認 service_account 權限現況並回報。
   - 若 service_account 無前台 Sheet 權限 → 列為 Olina 手動搬移（見手動清單 M2）；若有權限，backend 可寫一次性搬移腳本（純複製，不刪除前台 Sheet 原資料，保留為備援直到驗收通過）。
7. **GAS 重新部署**（M3）、**Netlify 推版**（M1）由 Olina 操作。

## 業務規則
- 合併為**私有** Sheet：完成後前台不再透過 gviz 公開讀取，客人個資（八字蛋糕訂單 tab 的姓名/電話/生日）不再因「知道連結者可檢視」而外洩。此為本 Phase 的關鍵安全目的。
- 前台 Sheet 原四 tab 在驗收通過前**保留不刪**，作為回滾備援。確認合併版正常運作後，由 Olina 決定何時關閉前台 Sheet 公開權限 / 清理（不在本 Task 自動刪除前台 Sheet）。

## 邊界條件 / 錯誤處理
- 搬移時若後台 Sheet 已存在同名 tab（理論上不會，但需防呆）→ 中止並回報，不可覆寫既有 `orders`/`ingredients`。
- products.js 生成失敗（sync 讀不到資料）→ sync 頁需顯示明確錯誤，不可推一份空的 products.js 上線（會讓前台全空）。
- 前台改吃 products.js 後，若 products.js 載入失敗 → 前台需有可見的降級提示（不可整頁空白且無訊息）。

## 驗收條件（QA 可執行）
1. 合併後台 Sheet 含上表 7 張 tab，`品牌設定`/`產品主檔` 內容與前台 Sheet 原資料一致（逐欄比對）。
2. 後台 `/admin/laiten/brand`：讀到的是 Sheet 真實值（非程式預設值）；存檔後重讀，值確實寫入 Sheet。
3. 後台 `/admin/laiten/products/<line_id>`：讀寫指向合併後 Sheet 的 `產品主檔`，存檔生效。
4. gws 寫入遇 API 非 200 時，前端可見失敗訊息（不再假成功）——以一個刻意造錯案例驗證。
5. `/admin/laiten/sync` 生成的 products.js 含完整品牌設定 + 產品主檔資料，且 git push 功能正常（images/index.html 部署管道未壞）。
6. 前台 index.html 改吃 products.js 後：品牌文案、產品卡、八字/下午茶表單選項、GAS URL 均正確渲染；Console 無 gviz 請求。
7. ⚠️OLINA 推版後實測：前台能正確顯示產品並送出測試單，GAS 寫入合併後 Sheet 的訂單 tab。

---

# Phase 2 — 訂單橋接：後台「前台訂單收件匣」轉單頁

## 功能描述
新增後台頁面「前台訂單收件匣」，列出合併後 Sheet 的 `八字蛋糕訂單` / `下午茶訂單` 兩張 tab（前台 GAS 寫入的單）。**兩種訂單的處理路徑不同（D1 拍板）**：
- **八字蛋糕訂單**：提供「一鍵轉入 orders」，依欄位映射寫入後台 `orders` tab，轉單時補填前台沒收集的欄位（最關鍵是**心願主項 / 心願細項**——八字分析的必要輸入），轉入後進既有八字分析流程。
- **下午茶訂單**：**不轉入 orders**（orders 是八字蛋糕專用 schema，下午茶結構不符、且不走八字分析）。改為「轉入下午茶自己的管理 tab」——在合併後的單一後台 Sheet 裡，下午茶訂單有獨立的管理頁籤，收件匣的下午茶單一鍵轉入該管理 tab。

解決目前「前台訂單與後台 orders / 管理流互不相通、前台單永遠不進後台」的斷點。

## D1 拍板：下午茶管理 tab（同一份後台 Sheet 內的獨立頁籤）
Olina 2026-06-13 拍板：下午茶訂單在**合併後的單一後台 Sheet（`1oYJ7…`）內開獨立頁籤**管理，不塞進八字的 orders tab。

- 合併後 Sheet 已含「下午茶訂單」tab（前台搬入，GAS 寫入的原始收件來源）。本 Phase 另立一個**下午茶管理 tab**（建議名 `下午茶管理`，最終命名以 backend/SA 為準），作為師傅已受理 / 處理中的下午茶單管理區，與「下午茶訂單（原始收件）」分離，避免收件匣與管理狀態混在同一張表。
- 收件匣（Phase 2）對下午茶單提供「一鍵轉入下午茶管理 tab」，轉入時把前台 8 欄完整搬過去，並補一個「狀態」欄供師傅追蹤。
  - **狀態欄暫定設計（D8 未拍板）**：轉入時狀態**固定填單一預設值「待處理」**。完整狀態清單（處理中 / 已完成 / 已交付 / 取消等）留待 D8 拍板。此設計**暫定、可擴充**——backend **不要自己編狀態值**，Phase 2 只用「待處理」這一個值即可（師傅暫無切換狀態的 UI 需求，下午茶管理 tab 本 Phase 僅檢視 + 標記轉入）。D8 拍板後再補狀態切換功能，屬後續 Task。
- 下午茶**不**經過八字 analyze / generate_card；它是純訂單管理（檢視、標記狀態），無 AI 流程。

## 頁面與路由（建議，最終以 backend/SA 命名為準）
- `GET /admin/inbox`：列出八字蛋糕訂單 + 下午茶訂單未轉單的列，分區顯示（八字蛋糕區 / 下午茶區），各列顯示來源 tab、下單時間、客人資訊。
- `POST /admin/inbox/convert`：八字蛋糕單轉入 `orders`，附帶師傅補填欄位（心願主項必填）。
- `POST /admin/inbox/convert_tea`：下午茶單轉入 `下午茶管理` tab（或以同一 convert 端點加 `type` 參數區分，由 backend 決定；規格要求兩種轉向行為明確分離，不可把下午茶寫進 orders）。

## D4 拍板：orders 擴欄至 18 欄（後台收的資料與前台一致）
Olina 2026-06-13 拍板：orders **擴充欄位**，讓後台訂單檔與網站收的資料一致——前台八字蛋糕單有、舊 orders 沒有的欄位（**品項 / 數量 / 取貨日期 / 外送**）全部進 orders，**不再併入備註**。

### orders 最終欄位清單與順序（草案，18 欄）
| # | 欄位名（中文標題） | db.py 內部 key | 來源 | 必填 |
|---|----|----|----|----|
| 1 | id | id | 系統產生（**D2：`YYYYMMDD-NN` 日期前綴**，日期取前台下單時間之日期） | ✅ |
| 2 | 建立時間 | created_at | **前台下單時間（D3 拍板）**——轉單時帶入前台「八字蛋糕訂單」tab 的下單時間，非轉單當下。create_order 用 `created_at` 選填參數帶入，未傳時才 fallback `datetime.now()` | ✅ |
| 3 | 姓名 | name | 前台 name | ✅ |
| 4 | 電話 | phone | 前台 phone | ✅ |
| 5 | 生日 | birthday | 前台 birthdate | ✅ |
| 6 | 時辰 | shichen | 前台 birth_hour | |
| 7 | 心願主項 | wish_main | **師傅補填**（轉單表單必填，八字分析必要輸入） | ✅ |
| 8 | 心願細項 | wish_sub | **師傅補填**（轉單表單可選） | |
| 9 | 備註 | note | 前台 notes（**只放 notes，不再塞 product/quantity 等**） | |
| 10 | 狀態 | status | 固定「待處理」 | ✅ |
| 11 | 八字分析 | bazi_result | 留空，由 analyze 產生 | |
| 12 | 選用食材 | ingredients | 留空，由 generate_card 產生 | |
| 13 | 小卡文案 | card_text | 留空，由 generate_card 產生 | |
| 14 | 五行建議 | suggestion | 留空，由 analyze 產生 | |
| 15 | 品項 | product | 前台 product（**新增**） | |
| 16 | 數量 | quantity | 前台 quantity（**新增**） | |
| 17 | 取貨日期 | pickup_date | 前台 pickup_date（**新增**） | |
| 18 | 外送 | delivery | 前台 delivery（**新增**） | |

**為什麼新欄位追加在尾端（15–18），而非插在中段**：`update_order_fields` 的 `col_map` 把分析結果欄位寫死為第 10–14 欄；若把新欄插在中段會動到 col_map 全部數字，牽動 analyze / generate_card 寫入位置，高風險。追加在第 14 欄之後 → **col_map（10–14）完全不變，既有八字分析流程零影響**，只在尾端擴 4 欄。閱讀順序上「客人填的品項資料」排在分析結果之後，純屬版面，程式無感。

### ⚠️ orders 欄位順序契約：五處必須同步擴欄（backend 一次改完，缺一處即錯位）
SYSTEM_MAP 已警告 orders 欄位順序是隱性契約，散布在 db.py 多處。擴成 18 欄時，下列**五處**必須同步：

1. **`ORDERS_HEADER`**（db.py:65-69）：尾端加 `"品項", "數量", "取貨日期", "外送"` → 共 18 欄。
2. **`_row_to_order`**（db.py:72-90）：尾端加 `"product": g(14), "quantity": g(15), "pickup_date": g(16), "delivery": g(17)`。
3. **`create_order`**（db.py:135-145）：函式簽名加 4 個選填參數（預設空字串）`product="", quantity="", pickup_date="", delivery=""`，append 的 list 尾端對應補 4 值。**既有呼叫者不傳新參數時行為不變**（向後相容）。
4. **`update_order_fields` 的 `col_map`**（db.py:153-156）：**不需改數字**（10–14 不動）；若未來要讓師傅在後台編輯品項等欄，再把 15–18 加進 col_map，本 Task 不做。
5. **`init_sheets`**（db.py:263-264, 272-276）：`add_worksheet(cols=14)` → `cols=18`；標題列寫入沿用更新後的 `ORDERS_HEADER`（自動跟著變 18 欄）。

> 另：Phase 4.4 的「orders tab 標題列修正」原本要把舊 18 欄標題改成 14 欄；**D4 拍板後改為：標題列改成『新版 18 欄 ORDERS_HEADER』**（巧合也是 18 欄，但欄名與舊版完全不同，須以 db.py 最終 `ORDERS_HEADER` 為準，不可沿用舊 18 欄標題）。詳見 Phase 4.4 更新。

## D2 拍板：訂單編號改日期前綴（推翻 SA 裁定一「get_next_order_id 直接複用」前提）

Olina 2026-06-13 拍板：orders `id` 由整數流水號改為**日期前綴格式**。

### 新編號格式
- 格式：`YYYYMMDD-NN`（例：`20260613-01`）。
  - `YYYYMMDD`：建立日期（依 D3，**取前台下單時間的日期**，非轉單當下日期——見下方與 D3 連動）。
  - `NN`：該日期序號，從 `01` 起，**補零至兩位**（01、02…09、10…）。
- 當日序號進位規則：同一 `YYYYMMDD` 下，新單序號 = 該日期既有最大序號 + 1。
  - 若當日已達 `99`（第 100 筆）→ 序號改為三位 `100`（不限制位數，超過 99 自然進位為 3 位，不報錯、不阻擋）。極端情況，正常營運不會觸發。
  - 不同日期各自獨立從 01 起算（跨日歸零）。

### ⚠️ 這推翻了 SA 裁定一的前提——取號邏輯需改寫
SA 影響分析裁定一原假設「Phase 2 轉單複用 `create_order` / `get_next_order_id`，封裝完全吻合（取號＋append＋狀態）」。**D2 拍板後，`get_next_order_id` 的整數流水號邏輯不再適用，必須改寫**。但裁定一「保留 create_order，不刪、不在 Phase 4 刪除」的結論**仍成立**——只是 create_order 內部取號方式要換成日期前綴版。

backend 需處理以下連動點（db.py 內，逐一同步，缺一即錯）：

| # | 位置 | 現況（流水號） | D2 後需改 |
|---|------|---------------|-----------|
| 1 | `get_next_order_id`（db.py:119-132） | `int(row[0]) + 1` 回傳整數 | 改寫為「依目標日期 `YYYYMMDD` 掃描既有 id、找出同日期最大序號 + 1、組成 `YYYYMMDD-NN`」。函式需接收「建立日期」參數（因 D3 用前台下單日期，非今天），回傳字串。建議改名或新增 `get_next_order_id_by_date(date_str)`，由 backend 定。 |
| 2 | `create_order`（db.py:135-145） | `new_id = get_next_order_id()`、回傳 `int` | 改用日期前綴取號；`created_at`（D3）的日期部分即 `NN` 取號依據的日期；回傳型別改 `str`。 |
| 3 | `load_orders` auto_id 補位（db.py:103-114） | `int(r[0]) + 1` 對空 id 列自動補流水號 | 此邏輯依賴整數遞增。新格式下無法用 `int()`。需改為：空 id 列的容錯處理（建議跳過 int 運算，或對舊整數 id 維持相容、對新格式不做遞增推算）。**注意舊資料相容**（見下）。 |
| 4 | `update_order_fields` 查找（db.py:160-161） | `str(row[0]) == str(order_id)` 字串比對 | **字串比對本身相容**，新舊 id 都是字串可比。但呼叫端傳入的 `order_id` 來源（路由 `<id>`）需確認型別一致——`/admin/order/<id>` 路由若宣告 `<int:id>` 會無法匹配 `20260613-01`，**須改為 `<id>`（字串）或 `<path:id>`**。backend 須一併檢查 admin.py 所有以 order id 為路由參數的端點。 |

### 既有舊 id 資料的相容處理（重要）
- 現行 orders 已有舊資料：`id=1`（整數流水號）。改格式後**不回頭改寫舊資料**（不遷移、不重新編號），舊 `1` 保持原樣共存。
- 相容要求：
  - `load_orders` / `_row_to_order` 讀取時，舊整數 id 與新日期前綴 id 都當**字串**處理，照常顯示與查找。
  - `update_order_fields`、`/admin/order/<id>`、analyze、generate_card 等以 id 定位的流程，對舊 `1` 與新 `20260613-01` 都要能正確命中（統一走字串比對，不可再 `int(id)`）。
  - 取號（`get_next_order_id` 新版）掃描既有 id 時，**遇到無法解析為 `YYYYMMDD-NN` 的舊 id（如 `1`）一律略過**，不納入當日序號計算（舊整數 id 不屬於任何 `YYYYMMDD` 群組）。
- backend 實作後，須在 qa_smoke_test 基線涵蓋「舊整數 id 與新日期 id 並存時，讀取/查找/更新皆正確」的案例。

### D2 與 D3 的連動
- `NN` 序號的「當日」依據 = **D3 的建立時間日期**（前台下單時間）。
  - 例：客人 6/13 23:50 下單，師傅 6/14 才轉單 → 建立時間用前台下單時間（D3），日期為 `20260613`，id 取 `20260613-NN`（依 6/13 當日序號），**不是** `20260614`。
- 因此取號函式必須吃「建立日期」參數，不能寫死 `datetime.now()`。

## 欄位映射（八字蛋糕訂單 → orders，18 欄）
前台 `八字蛋糕訂單`（10 欄）：`時間, name, phone, birthdate, birth_hour, product, quantity, pickup_date, delivery, notes`
後台 `orders`（18 欄，見上表）。映射規則：前台 10 欄中 8 欄直接落位（name/phone/birthdate/birth_hour/product/quantity/pickup_date/delivery/notes），心願主項/細項由師傅補填，**建立時間用前台下單時間（D3）**，**id 用日期前綴 `YYYYMMDD-NN`（D2，日期取前台下單時間之日期）**，分析 4 欄留空。轉單複用 `create_order`（裁定一保留 create_order 的結論不變），故 backend 對 `create_order` 擴參數（4 個新欄 + `created_at` 帶前台下單時間）並改寫其內部取號（D2 日期前綴）後，convert 端點直接以新參數帶入前台欄位。

## 業務規則
1. **防重轉標記（D5 拍板）：在來源 tab 加「已轉入」欄**。八字蛋糕訂單、下午茶訂單**兩個前台 tab 各加一欄**（建議欄名「已轉入」，置於各 tab 既有欄位之後），預設空白；轉單**成功後**才把該列此欄標記（建議寫入轉單時間或轉入後的目標 id，最終值由 backend 定，至少能判定「已轉/未轉」）。收件匣（`/admin/inbox`）列出時，**只顯示「已轉入」欄為空的列**（已轉入的不再出現於待轉清單）。八字蛋糕單與下午茶單各自獨立判定已轉。
   - ⚠️標記時機：必須在「寫入目標 tab 成功」之後才標記來源欄；若目標寫入失敗，來源欄維持空白（不可標記），避免單子既沒進 orders/管理 tab、又被當成已轉而消失。
   - ⚠️此為對前台訂單來源 tab 的**結構變更**（各加一欄）。合併後 Sheet 的「八字蛋糕訂單」「下午茶訂單」兩 tab 需新增「已轉入」欄；GAS 寫入新單時不會填此欄（保持空白＝未轉），與 GAS 寫入欄位順序不衝突（追加在尾端）。backend 須確認加欄後 GAS append 的欄位對位不受影響（GAS 按固定欄數 append，新欄在其右側即可）。
2. 心願主項/心願細項為八字分析必要輸入，八字蛋糕單轉單時「心願主項」必填。
3. 收件匣只讀前台訂單 tab + 寫目標 tab（八字→orders、下午茶→下午茶管理），不修改前台訂單原始資料（除標記已轉外）。
4. **下午茶單一律不得寫入 orders**；八字蛋糕單一律不得寫入下午茶管理 tab。兩條轉向互斥。

## 邊界條件 / 錯誤處理
- 同一列被重複轉單 → 收件匣已過濾「已轉入」欄非空的列（D5），實務上不會出現在待轉清單；若仍發生（並發等），轉單前再檢查來源欄已標記則擋下並警告。
- 收件匣 tab 為空（或全部已轉入）→ 顯示「目前無待轉訂單」，不報錯。
- 轉單寫目標 tab 失敗 → 回明確錯誤，**不可標記來源「已轉入」欄**（標記必須在目標寫入成功之後）。
- 八字蛋糕轉單：前台 product/quantity/pickup_date/delivery 任一為空 → 照空值帶入 orders 對應欄（不阻擋，這些欄非必填）。
- D2 取號：前台下單時間若缺失 / 無法解析日期 → backend 須定 fallback（建議用轉單當下日期組 `YYYYMMDD-NN`，並 log 警告），不可讓取號崩潰。
- 舊整數 id（如 `1`）與新日期 id 並存 → 讀取/查找/更新皆須正確（取號掃描時略過無法解析的舊 id）。

## 驗收條件（QA 可執行）
1. `/admin/inbox` 正確列出 `八字蛋糕訂單` 與 `下午茶訂單` **未轉入**的單，分區顯示（已轉入的不顯示；以測試資料驗證，不污染正式資料）。
2. 八字蛋糕一鍵轉單：補填心願主項後，orders tab 新增一列，**18 欄映射正確**（含品項/數量/取貨日期/外送四新欄有值）、狀態為「待處理」、**id 為 `YYYYMMDD-NN` 日期前綴格式（D2，日期＝前台下單日期）**、**建立時間為前台下單時間（D3，非轉單當下）**。
3. 轉入的單可在 `/admin/order/<id>` 開啟（路由能接受日期前綴字串 id），並能正常跑 `/admin/api/analyze`（心願欄位有值，分析不缺輸入；analyze 寫回第 10–14 欄未受擴欄影響）。
4. 重複轉單被擋下：轉單成功後，來源 tab 該列「已轉入」欄被標記，且該單不再出現於收件匣（八字、下午茶各驗一次）。
5. 下午茶一鍵轉單：下午茶單轉入 `下午茶管理` tab，8 欄＋狀態欄（值為「待處理」）正確；**確認下午茶未誤寫進 orders**（orders 列數不因下午茶轉單增加）。
6. （回歸）擴欄後既有後台訂單列表 `/admin`、`/admin/order/<id>`、`/admin/print` 照常顯示（_row_to_order 補欄未破壞既有讀取）。
7. **D2 取號序號進位**：同一日期連續轉兩單 → id 為 `YYYYMMDD-01`、`YYYYMMDD-02`（序號 +1、補零兩位）；不同日期的單各自從 01 起算。
8. **舊資料相容**：既有 `id=1` 的舊訂單，在擴欄 + 改編號後仍能於 `/admin`、`/admin/order/1` 正常讀取與更新；新日期 id 取號不受舊整數 id 干擾。

---

# Phase 3 — 品牌頁存檔防呆 + 前台送單失敗顯示

## 功能描述
兩個獨立但相關的防呆：（A）後台品牌設定整份覆寫的特性下，欄位留空會清掉 `cta_url_bazi/cta_url_tea`（GAS URL）→ 需空值警告；（B）前台 `sendToGAS` 失敗時，客人必須看到失敗訊息 + 備援聯絡方式，不可假成功。

## A. 品牌頁空值警告（後端 + 後台 UI）
- `_save_laiten` 是 clear + 整份重寫，任一欄留空都會寫入空值覆蓋舊值。
- `cta_url_bazi` / `cta_url_tea` 是前台送單端點開關，清空 = 前台靜默送單失敗。
- **規則（D6 拍板：禁止存空值）**：品牌設定存檔時，若 `cta_url_bazi` 或 `cta_url_tea` 為空 → **直接擋下存檔，不寫入**，並回明確錯誤訊息（建議：「『八字蛋糕送單網址 / 下午茶送單網址』為前台送單端點，不可留空，否則前台將無法送單。請填入有效網址後再儲存。」），明確指出是哪一個欄位為空。
  - 攔截點：須攔在 `_save_laiten` 的 **clear 之前**（`_save_laiten` 是 clear + 整份重寫，一旦 clear 就會清掉舊值；驗證必須在清除前做，驗證不過則整個存檔中止、舊值保留）。
  - 不提供「強制存空」的繞過選項——D6 拍板為硬性禁止，非警告後可強制。

## B. 前台送單失敗顯示（前端）
- 目前 `sendToGAS` 對空 URL 只 `console.warn`，客人仍看到成功畫面（假成功）。
- 規則：
  - GAS URL 為空 / 送出 request 失敗（no-cors 限制下以可偵測的方式，如 fetch reject、timeout）→ 客人看到明確失敗訊息 + 備援聯絡方式。
  - **備援聯絡方式（D7 拍板）**：顯示電話 **0918-235-714**。失敗訊息建議文案：「送出失敗，請來電 0918-235-714 由專人為您處理訂單。」（前端可微調用語，但電話號碼須為 0918-235-714，且需可點擊撥號 `tel:0918235714` 為佳）。
- no-cors 模式無法讀回應狀態的技術限制需在 impact 評估：若無法可靠偵測 GAS 端寫入成功與否，至少要覆蓋「URL 為空」「網路層 reject」兩種可偵測失敗，並在這些情況顯示備援電話 0918-235-714。

## 驗收條件（QA 可執行）
1. 後台品牌頁將 `cta_url_bazi`（或 `cta_url_tea`）清空後存檔 → **被擋下、不寫入、舊值保留**，並顯示指出哪一欄為空的明確錯誤訊息（D6 禁止存空）。
2. 前台 GAS URL 為空時送單 → 客人看到失敗訊息 + 備援電話 0918-235-714（非成功畫面）。
3. 前台網路層送單失敗（模擬）→ 同樣顯示失敗 + 備援電話 0918-235-714。
4. 正常送單成功路徑不受影響（仍顯示成功）。

---

# Phase 4 — 死碼刪除 + 孤兒清理 + orders 標題列修正 + xlsx 處置

## 功能描述
清理已確認零有效引用的死碼與其連動孤兒，修正後台 orders tab 標題列錯位，並依比對結果處置 bazi_cake.xlsx。

## 4.1 死碼刪除（已掃描確認零有效引用，Olina 批准）
刪除以下四件套：
- `back/app.py`（舊版前台訂單表單，引用不存在的 template）
- `ingredient_web.py`（舊版食材判斷，寫 Excel，port 與 admin.py 衝突）
- `ingredient_classifier.py`（ingredient_web.py 依賴，prompt 已複製進 admin.py）
- `setup_excel.py`（建 bazi_cake.xlsx 的一次性腳本）

## 4.2 連動孤兒函式清理（db.py）
- `create_order`：Phase 2 轉單複用（裁定一）→ **保留，不刪**。
- `get_next_order_id`：Phase 2 轉單需取號 → **保留，但 D2 拍板後須改寫為日期前綴版（見 Phase 2「D2 拍板」）**，不刪。
- ⚠️**D2 後更新**：SA 裁定一原假設「直接複用 get_next_order_id（流水號）」，**D2 推翻了流水號前提**，但「保留 create_order / get_next_order_id、Phase 4 不刪這兩函式」的結論**仍成立**——只是 get_next_order_id 的內部實作由流水號改為日期前綴取號（backend 在 Phase 2 改寫）。Phase 4 刪除清單維持只刪 `back/app.py`、`ingredient_web.py`、`ingredient_classifier.py`、`setup_excel.py` 四檔。

## 4.3 qa_smoke_test.py 基線同步
- 死碼刪除後，更新 `qa_smoke_test.py`：移除對已刪檔案 / 已刪函式的引用與測試，使冒煙基線與新現況一致。

## 4.4 orders tab 標題列修正（D4 連動：改為新版 18 欄）
- 後台 Sheet `orders` tab 標題列是**舊版 18 欄**（訂單編號/建立日期/取件日期/出生地/底色/夾層…）、資料列原是新版 14 欄（db.py 跳過標題列按位置讀，程式無感，但人工對標題填資料必錯位）。
- **D4 拍板後，orders 擴成新版 18 欄**（id…五行建議＋品項/數量/取貨日期/外送）。
- 修正：把標題列改為**擴欄後的 `ORDERS_HEADER`（db.py 定義的新版 18 欄）**。⚠️注意：舊標題剛好也是 18 欄，但欄名與新版完全不同，**不可沿用舊 18 欄標題**，必須以 db.py 最終 `ORDERS_HEADER` 逐欄為準。
- 執行順序：此步須在 Phase 2 的 db.py 擴欄（ORDERS_HEADER 改 18 欄）完成後做，標題列才會與資料列一致。
- ⚠️OLINA 或 backend：此為 Sheet 內容修改。service_account 對後台 Sheet canEdit=True（SA 已實測），backend 可程式修正。**只改標題列第 1 列，不可動資料列**。

## 4.5 bazi_cake.xlsx 處置
- 步驟：(1) 比對 xlsx 內食材資料 與 Google Sheets `ingredients` tab 哪邊完整；(2) 確認系統實際讀哪邊（依 SYSTEM_MAP：現行食材管理走 Sheets，xlsx 為舊 Excel 時代產物）。
- 決策樹：
  - 若 Sheets ingredients 已完整涵蓋 xlsx → 刪 bazi_cake.xlsx。
  - 若 xlsx 較完整 → 先把差異資料整理進 Sheets `ingredients`（正確位置），驗證後再刪 xlsx。
- backend 在實作時輸出比對結果（哪邊完整、差異筆數），交 Olina 確認後才刪（**xlsx 刪除前需 Olina 點頭**，列待確認 D8 的驗證點）。

## 驗收條件（QA 可執行）
1. 四個死碼檔案已刪除，全 repo 無殘留 import / 引用。
2. `create_order` / `get_next_order_id` **保留**（Phase 2 複用，D2 後 get_next_order_id 已改寫為日期前綴版）；其餘確認的孤兒已清。
3. `qa_smoke_test.py` 更新後可正常執行通過（無對已刪物件的引用）。
4. orders tab 標題列為**新版 18 欄 `ORDERS_HEADER`**（D4，非舊 18 欄、非 14 欄），資料列未被更動。
5. bazi_cake.xlsx 比對結果有輸出；若刪除，已取得 Olina 確認且差異資料（如有）已併入 ingredients。

---

## Olina 手動操作清單（集中）

| 編號 | 動作 | 時機 | 說明 |
|------|------|------|------|
| **M1** | Netlify 推版 | Phase 0 驗收後 / 各前台變更後 | 前台 index.html、products.js 變更需推上 Netlify 才生效（部分經 `/admin/laiten/sync` 的 git push，部分可能需手動確認部署） |
| **M2** | 手動搬移前台 Sheet 四 tab → 後台 Sheet | Phase 1，**僅當 service_account 無前台 Sheet 權限時** | backend 先回報權限現況；無權限則 Olina 手動複製四 tab 內容進後台 Sheet |
| **M3** | Apps Script 編輯器改 GAS `SHEET_ID` + 重新部署（新增版本） | Phase 1 | repo 的 gas_order_handler.js 只是副本，線上 GAS 需 Olina 在 script.google.com 改 SHEET_ID 指向合併後 Sheet 並重新部署 |
| **M4** | 手動修 orders 標題列（僅當 service_account 無寫入權限時） | Phase 4 | 只改標題列為 14 欄，不動資料列 |
| **M5** | 確認 bazi_cake.xlsx 刪除 | Phase 4 | backend 輸出比對結果後，Olina 點頭才刪 |
| **M6** | 驗收通過後決定何時關閉前台 Sheet 公開權限 / 清理前台 Sheet 原 tab | Phase 1 之後 | 前台 Sheet 原四 tab 保留作回滾備援，確認合併版穩定後由 Olina 清理 |

---

## 已拍板決策（2026-06-13 Olina）

| 編號 | 決策 | 規格落點 |
|------|------|---------|
| **D1** ✅ | 下午茶訂單**不轉入 orders**，改在合併後的單一後台 Sheet 內開**獨立管理 tab**（建議名 `下午茶管理`）；收件匣同時涵蓋兩種訂單檢視，下午茶轉入自己的管理 tab、八字轉入 orders。下午茶不走八字分析。 | Phase 2「功能描述」「D1 拍板」「路由」「業務規則 4」「驗收 1/4/5」 |
| **D4** ✅ | orders **擴欄至 18 欄**，前台有的 品項/數量/取貨日期/外送 全進 orders（不併入備註）。新欄追加在第 15–18 欄（尾端），保 col_map 10–14 不變。欄位順序契約五處同步。 | Phase 2「D4 拍板 / 18 欄清單 / 五處同步」、Phase 4.4 標題列改 18 欄 |
| **D7** ✅ | 前台送單失敗顯示備援電話 **0918-235-714**。 | Phase 3-B、Phase 3 驗收 2/3 |
| **D2** ✅ | orders `id` 改**日期前綴 `YYYYMMDD-NN`**（如 `20260613-01`），日期取前台下單時間之日期，序號當日從 01 起、補零兩位、+1 進位。**推翻 SA 裁定一「流水號直接複用」前提——get_next_order_id 須改寫**；舊整數 id（如 `1`）不遷移、共存、取號時略過。連動 db.py 五處（取號/create_order/load_orders/update查找/路由型別）。 | Phase 2「D2 拍板」、Phase 4.2、Phase 2 驗收 2/3/7/8 |
| **D3** ✅ | 轉單後 orders「建立時間」用**前台下單時間**（非轉單當下）；create_order 以 `created_at` 選填參數帶入。同時是 D2 序號的「當日」依據。 | Phase 2「D2/D3 連動」、18 欄清單第 2 欄、Phase 2 驗收 2 |
| **D5** ✅ | 防重轉＝**來源 tab 加「已轉入」欄**（八字蛋糕訂單、下午茶訂單兩 tab 各加一欄），轉單成功才標記；收件匣只列「已轉入」為空的列。標記須在目標寫入成功之後。 | Phase 2「業務規則 1」、Phase 2 驗收 1/4 |
| **D6** ✅ | 品牌頁 `cta_url` 空值**禁止存檔**（直接擋下 + 明確錯誤訊息），攔在 `_save_laiten` clear 之前，無強制繞過。 | Phase 3-A、Phase 3 驗收 1 |

## 待確認（業務規則空白，未腦補，請 Olina 拍板）

| 編號 | 問題 | 影響 Phase |
|------|------|-----------|
| **D8** | 訂單 `狀態` 欄完整業務流程：除程式出現的 待處理/分析完成/文案完成，是否有人工狀態（已交付/取消等）？**同時影響下午茶管理 tab 的狀態值設計**。**Phase 2 暫定處理**：下午茶管理 tab 狀態欄只用單一預設值「待處理」、orders 沿用現有三狀態，此暫定設計可擴充，backend 不自行編狀態值；D8 拍板後補狀態切換，屬後續 Task。 | Phase 2（暫定不阻擋）／後續 |

> D8 不阻擋 Phase 2——Phase 2 狀態欄採暫定可擴充設計（只用「待處理」）。Phase 2、Phase 3 業務規則已全部拍板（D1–D7），可開工。

---

## 影響範圍分析（SA）

> SA 完成於 2026-06-13。完整版（含基線逐項清單、權限實測證據、Backend/Frontend 注意事項全文）見 `specs/Task1.impact.md`，本區為摘要。

### 三項裁定 / 確認結論

1. **create_order / get_next_order_id：保留，不刪**。Phase 2 轉單複用（封裝完全吻合：取號＋14 欄 append＋狀態=待處理）；Phase 4 刪除清單修正為只刪 back/app.py、ingredient_web.py、ingredient_classifier.py、setup_excel.py 四檔。若 D3 拍板用前台下單時間，create_order 加選填參數 `created_at=None`。
2. **Phase 0 可獨立出貨，但與 Phase 1 動同一個 `loadData()`，必須序列化**：Phase 0 上線 commit 落定後 Phase 1 才能動 index.html；Phase 1 重寫時必須保留「元素存在才賦值」防護。已逐一核對：loadData 引用的 DOM id 只有 `hero-tagline`/`hero-desc` 不存在，其餘 8 個都在。Phase 0 對 36 項冒煙基線**零影響**。
3. **M2 不需 Olina 手動搬**（已唯讀實測）：service_account（bazi-cake-service@bazi-cake.iam.gserviceaccount.com）對前台 Sheet 可讀（canEdit=False）、對後台 Sheet 可寫（canEdit=True）→ backend 寫一次性搬移腳本即可。注意 M6（關公開權限）必須在搬移完成後執行，否則腳本讀不到前台 Sheet。M4（orders 標題列）同理可程式修正。

### 受影響的既有功能

| 功能 | 頁面 / 函式 | 影響說明 | 需迴歸測試 |
|------|------------|---------|-----------|
| 前台整站渲染與送單 | index.html loadData/sendToGAS | Phase 0 修復、Phase 1 換資料來源、Phase 3 失敗顯示——三個 Phase 動同一檔案，依序執行 | ✅ |
| 後台 brand/products/sync 三頁 | admin.py SHEET_ID、_gws_* | 常數拆分＋錯誤不再吞噬，從「假正常」變真讀寫 | ✅ |
| 後台訂單/食材全功能 | db.py（經 GOOGLE_SHEETS_ID） | admin.py 17-19 行是唯一來源，拆常數不可改值 | ✅ |
| sync 部署管道 | /admin/laiten/sync git push 段 | products.js 轉正式來源；git push 不可動 | ✅ |
| orders 流程 | create_order→analyze→generate_card | Phase 2 轉單寫入後進既有流程 | ✅ |
| 冒煙基線 | qa_smoke_test.py | Phase 4 打破 9 項（import 失敗會整套中斷），刪檔後基線 36→28；Phase 1/2 另有 4＋4 個同步點 | ✅ |

### Backend / Frontend / QA 注意事項

詳見 `specs/Task1.impact.md`：含 Phase 1-4 逐項基線影響表、_save_laiten 警告需攔在 clear 之前、no-cors 可偵測失敗的技術上限、Phase 0 信號流跑完一圈後 Phase 1 的開工協調建議（建議 Olina 驗收 Phase 0 後由 main 直接委派 backend 續作 Phase 1-4）。

---

## 不在本次範圍

- 前台 Sheet 的刪除 / 公開權限關閉自動化（保留為 Olina 手動，M6）。
- FOOD_DATA（admin.py 寫死）與 ingredients tab 的同步（SYSTEM_MAP 已知技術債，非本 Task）。
- monthly tab 的程式化使用（維持零引用、人工參考）。
- ingredients `季節 / 用途` 欄位的業務邏輯化（目前僅 UI 顯示）。
- 純視覺 / 排版調整（不涉及欄位、流程、資料者）。
