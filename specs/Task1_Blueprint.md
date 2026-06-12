# Task1 Blueprint — 萊點（Laiten）前台修復 × Sheet 合併 × 訂單橋接 × 死碼清理

> PM 撰寫於 2026-06-13。依據：`specs/SYSTEM_MAP.md`（2026-06-13 SA 深度調查，已 gws 唯讀實查 + git 考古驗證）與 Olina 2026-06-13 拍板決策。
> **2026-06-13 更新**：Olina 拍板 D1（下午茶獨立管理 tab）、D4（orders 擴欄 18 欄）、D7（送單失敗備援電話 0918-235-714）。詳見文末「已拍板決策」與各 Phase 對應段落。
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
- 收件匣（Phase 2）對下午茶單提供「一鍵轉入下午茶管理 tab」，轉入時把前台 8 欄完整搬過去，並補一個「狀態」欄供師傅追蹤（待處理 / 處理中 / 已完成等，狀態值見 D8，下午茶不阻擋 Phase 2）。
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
| 1 | id | id | 系統產生 | ✅ |
| 2 | 建立時間 | created_at | 轉單當下時間 或 前台下單時間（**仍待 D3 拍板**；create_order 已預留 `created_at=None` 選填參數，兩種都支援） | ✅ |
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

## 欄位映射（八字蛋糕訂單 → orders，18 欄）
前台 `八字蛋糕訂單`（10 欄）：`時間, name, phone, birthdate, birth_hour, product, quantity, pickup_date, delivery, notes`
後台 `orders`（18 欄，見上表）。映射規則：前台 10 欄中 8 欄直接落位（name/phone/birthdate/birth_hour/product/quantity/pickup_date/delivery/notes），心願主項/細項由師傅補填，建立時間依 D3 結論（待拍板），id 系統產生，分析 4 欄留空。轉單複用 `create_order`（依裁定一），故 backend 對 `create_order` 擴參數後，convert 端點直接以新參數帶入前台四欄。

## 業務規則
1. 轉單後需標記該前台單為「已轉入」，避免重複轉單（標記方式待確認 D5：在來源 tab 加狀態欄？還是後台記已轉 id？）。八字蛋糕單與下午茶單各自獨立判定已轉。
2. 心願主項/心願細項為八字分析必要輸入，八字蛋糕單轉單時「心願主項」必填。
3. 收件匣只讀前台訂單 tab + 寫目標 tab（八字→orders、下午茶→下午茶管理），不修改前台訂單原始資料（除標記已轉外）。
4. **下午茶單一律不得寫入 orders**；八字蛋糕單一律不得寫入下午茶管理 tab。兩條轉向互斥。

## 邊界條件 / 錯誤處理
- 同一列被重複轉單 → 需擋下或警告（依 D5 機制）。
- 收件匣 tab 為空 → 顯示「目前無待轉訂單」，不報錯。
- 轉單寫目標 tab 失敗 → 回明確錯誤，不可標記為已轉。
- 八字蛋糕轉單：前台 product/quantity/pickup_date/delivery 任一為空 → 照空值帶入 orders 對應欄（不阻擋，這些欄非必填）。

## 驗收條件（QA 可執行）
1. `/admin/inbox` 正確列出 `八字蛋糕訂單` 與 `下午茶訂單` 的單，分區顯示（以測試資料驗證，不污染正式資料）。
2. 八字蛋糕一鍵轉單：補填心願主項後，orders tab 新增一列，**18 欄映射正確**（含品項/數量/取貨日期/外送四新欄有值）、狀態為「待處理」、建立時間為轉單當下時間。
3. 轉入的單可在 `/admin/order/<id>` 開啟，並能正常跑 `/admin/api/analyze`（心願欄位有值，分析不缺輸入；analyze 寫回第 10–14 欄未受擴欄影響）。
4. 重複轉單被擋下 / 警告（八字、下午茶各驗一次）。
5. 下午茶一鍵轉單：下午茶單轉入 `下午茶管理` tab，8 欄＋狀態欄正確；**確認下午茶未誤寫進 orders**（orders 列數不因下午茶轉單增加）。
6. （回歸）擴欄後既有後台訂單列表 `/admin`、`/admin/order/<id>`、`/admin/print` 照常顯示（_row_to_order 補欄未破壞既有 14 欄讀取）。

---

# Phase 3 — 品牌頁存檔防呆 + 前台送單失敗顯示

## 功能描述
兩個獨立但相關的防呆：（A）後台品牌設定整份覆寫的特性下，欄位留空會清掉 `cta_url_bazi/cta_url_tea`（GAS URL）→ 需空值警告；（B）前台 `sendToGAS` 失敗時，客人必須看到失敗訊息 + 備援聯絡方式，不可假成功。

## A. 品牌頁空值警告（後端 + 後台 UI）
- `_save_laiten` 是 clear + 整份重寫，任一欄留空都會寫入空值覆蓋舊值。
- `cta_url_bazi` / `cta_url_tea` 是前台送單端點開關，清空 = 前台靜默送單失敗。
- 規則：品牌設定存檔時，若 `cta_url_bazi` 或 `cta_url_tea` 為空 → 後台需**警告並要求確認**（「此欄為前台送單端點，清空將使前台無法送單，確定要儲存空值嗎？」），不可無聲覆寫。
- 待確認 D6：是「警告後仍可強制存」還是「禁止存空值」？預設前者（警告 + 二次確認），請 Olina 拍板。

## B. 前台送單失敗顯示（前端）
- 目前 `sendToGAS` 對空 URL 只 `console.warn`，客人仍看到成功畫面（假成功）。
- 規則：
  - GAS URL 為空 / 送出 request 失敗（no-cors 限制下以可偵測的方式，如 fetch reject、timeout）→ 客人看到明確失敗訊息 + 備援聯絡方式。
  - **備援聯絡方式（D7 拍板）**：顯示電話 **0918-235-714**。失敗訊息建議文案：「送出失敗，請來電 0918-235-714 由專人為您處理訂單。」（前端可微調用語，但電話號碼須為 0918-235-714，且需可點擊撥號 `tel:0918235714` 為佳）。
- no-cors 模式無法讀回應狀態的技術限制需在 impact 評估：若無法可靠偵測 GAS 端寫入成功與否，至少要覆蓋「URL 為空」「網路層 reject」兩種可偵測失敗，並在這些情況顯示備援電話 0918-235-714。

## 驗收條件（QA 可執行）
1. 後台品牌頁將 `cta_url_bazi` 清空後存檔 → 出現警告 / 二次確認（依 D6）。
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
- `create_order`：唯一呼叫者是 `back/app.py /submit`，刪 app.py 後成孤兒 → 刪除。
- `get_next_order_id`：唯一呼叫者是 `create_order`，連動成孤兒 → 刪除。
- ⚠️**與 Phase 2 衝突檢查**：Phase 2 的轉單需要「產生 orders 新列 + 新 id」。**若 Phase 2 的轉單複用 `create_order` / `get_next_order_id`，則這兩個函式不是孤兒，不可刪**。
  - **決議**：Phase 4 執行前必須先確認 Phase 2 轉單的實作方式。建議 Phase 2 轉單**複用** `create_order` / `get_next_order_id`（避免重寫 append + 取號邏輯），如此這兩函式保留，Phase 4 只刪 app.py / ingredient_* / setup_excel.py。SA 在影響分析時裁定，並在 impact 明確標示「create_order / get_next_order_id 最終去留」。

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
2. db.py 孤兒函式去留符合 SA 在 impact 的裁定（若 Phase 2 複用則保留，否則刪除且無殘留引用）。
3. `qa_smoke_test.py` 更新後可正常執行通過（無對已刪物件的引用）。
4. orders tab 標題列為 14 欄現行 schema，資料列未被更動。
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

## 待確認（業務規則空白，未腦補，請 Olina 拍板）

| 編號 | 問題 | 影響 Phase |
|------|------|-----------|
| **D2** | orders `id` 取號規則：沿用 get_next_order_id（流水號）即可，還是有業務編碼規則（如日期前綴）？ | Phase 2 / 4 |
| **D3** | 轉單後 orders「建立時間」用轉單當下，還是用前台下單時間？（create_order 已預留 `created_at=None` 選填參數，兩種皆可，僅需拍板取哪個） | Phase 2 |
| **D5** | 防重複轉單的標記方式：在來源 tab 加「已轉入」狀態欄？還是後台記錄已轉來源列？（八字、下午茶兩條轉向都需此機制） | Phase 2 |
| **D6** | 品牌頁存空值：警告後仍可強制存（預設），還是禁止存空 cta_url？ | Phase 3 |
| **D8** | 訂單 `狀態` 欄完整業務流程：除程式出現的 待處理/分析完成/文案完成，是否有人工狀態（已交付/取消等）？**同時影響下午茶管理 tab 的狀態值設計**（D1 拍板後下午茶管理 tab 也需狀態欄）。 | Phase 2（次要） |

> 剩餘 D2/D3/D5/D6/D8 不阻擋 Phase 0。Phase 2 開工前需 D3/D5（D2 可並行）；Phase 3 開工前需 D6。D8 可並行，建議與下午茶管理 tab 狀態欄一起拍板。

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
