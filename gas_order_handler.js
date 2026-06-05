/**
 * Laiten 萊點 — 訂單接收 Google Apps Script
 *
 * 部署步驟：
 * 1. 打開 https://script.google.com → 新增專案，命名「Laiten 訂單接收」
 * 2. 貼上此檔案全部內容
 * 3. 修改下方 SHEET_ID 和 NOTIFY_EMAIL
 * 4. 點「部署 → 新增部署」→ 類型選「網路應用程式」
 *    - 以「我」的身份執行
 *    - 存取權：「所有人（包含匿名使用者）」
 * 5. 複製部署 URL，貼到 Flask 後台「品牌設定」的對應欄位
 * 6. 每次修改程式碼後，要點「新增部署（版本）」才會生效，舊 URL 不用換
 */

const SHEET_ID     = '1xtuKyod3lOQUmp_D10AhDDGSD4bVxG3TmZudO2S9AMo';
const NOTIFY_EMAIL = 'yuchin@ulinjia.net';

function doPost(e) {
  try {
    const p   = e.parameter;
    const ss  = SpreadsheetApp.openById(SHEET_ID);
    const now = Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy/MM/dd HH:mm:ss');

    if (p.type === 'bazi') {
      _writeBazi(ss, now, p);
      _sendBaziEmail(now, p);
    } else if (p.type === 'tea') {
      _writeTea(ss, now, p);
      _sendTeaEmail(now, p);
    }
  } catch (err) {
    Logger.log(err);
  }

  // 固定回傳 200（mode: no-cors 收不到 response，這只是備用）
  return ContentService
    .createTextOutput(JSON.stringify({ status: 'ok' }))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── 八字蛋糕 ────────────────────────────────────────────────────

function _writeBazi(ss, now, p) {
  const sheet = ss.getSheetByName('八字蛋糕訂單');
  sheet.appendRow([
    now,
    p.name        || '',
    p.phone       || '',
    p.birthdate   || '',
    p.birth_hour  || '',
    p.product     || '',
    p.quantity    || '',
    p.pickup_date || '',
    p.delivery    || '',
    p.notes       || '',
  ]);
}

function _sendBaziEmail(now, p) {
  const subject = `【萊點｜八字蛋糕】新預約 — ${p.name}`;
  const body =
    `時間：${now}\n` +
    `姓名：${p.name}\n` +
    `電話：${p.phone}\n` +
    `品項：${p.product} × ${p.quantity}\n` +
    `取貨日期：${p.pickup_date}\n` +
    `取貨方式：${p.delivery}\n` +
    `出生日期：${p.birthdate || '未填'}\n` +
    `出生時辰：${p.birth_hour || '未填'}\n` +
    `備註：${p.notes || '無'}`;
  MailApp.sendEmail({ to: NOTIFY_EMAIL, subject, body });
}

// ── 精選下午茶 ───────────────────────────────────────────────────

function _writeTea(ss, now, p) {
  const sheet = ss.getSheetByName('下午茶訂單');
  sheet.appendRow([
    now,
    p.company    || '',
    p.contact    || '',
    p.phone      || '',
    p.items      || '',
    p.event_date || '',
    p.total_qty  || '',
    p.notes      || '',
  ]);
}

function _sendTeaEmail(now, p) {
  const subject = `【萊點｜精選下午茶】新洽詢 — ${p.company}`;
  const body =
    `時間：${now}\n` +
    `公司：${p.company}\n` +
    `聯絡人：${p.contact}\n` +
    `電話：${p.phone}\n` +
    `需求日期：${p.event_date}\n` +
    `品項與數量：${p.items}\n` +
    `總份數：${p.total_qty}\n` +
    `備註：${p.notes || '無'}`;
  MailApp.sendEmail({ to: NOTIFY_EMAIL, subject, body });
}
