# 台股資訊圖卡

頁首使用「台股資訊圖卡」，不顯示專案縮寫。個股以中文簡稱為主、原報告英文名稱為小字副標；ETF 使用證券簡稱，避免將投信公司名稱當成基金名稱。沿用共用股票名稱表，尚未收錄且原文也沒有中文名稱時保留原名，不猜譯。

此 Fork 使用同一次股票／市場分析的資料製作資訊圖卡，不額外呼叫 AI。圖卡是重點摘要，完整新聞、財務表格與推論放在 Email 報告中；歷史報告與分析數據不因產圖改變。

## 官方行情日期備援

加權指數主來源使用 TWSE OpenAPI `exchangeReport/FMTQIK`；主來源沒有資料、失敗或落後於要求的交易日時，改查證交所 `rwd/zh/afterTrading/FMTQIK?response=json&date=YYYYMMDD`。備援必須含唯一的指定日期列，回應日期及「元、股」單位也須正確；無法確認時保留缺漏，不借用其他交易日。

月資料只提供可取得的歷史列；月初不足前五個交易日樣本時，不顯示五日量值比較。備援不會重新產生 AI 分析或重送通知。

其他資料來源於 2026-10-14 核對：

| 資料 | 指定日期能力及本次處理 |
| --- | --- |
| 上市法人 | BFI82U 已用 `dayDate`，核對回應日及元單位 |
| 上市漲跌家數／類股 | MI_INDEX 已用 `date`，核對回應日及指定表格 |
| 上櫃類股 | indexSummary 已用 `date`，核對回應日及表格日 |
| 櫃買指數 | OpenAPI 最新日；indexSummary 可查歷史指數，但沒有同口徑的成交股數／金額，未直接替換完整行情 |
| 上櫃法人 | OpenAPI 最新日；官網 insti/summary 可查指定日，但涵蓋鉅額等交易，與現有來源範圍不同，未直接替換 |
| 上櫃漲跌家數 | OpenAPI 最新日；官網 highlight 可查指定日，但註記涵蓋股票及換股權利證書等口徑，未直接替換 |

可查到同一日期不代表可任意互換來源；替換前須確認統計範圍與單位一致。尚未接入的備援仍維持日期不符即缺失，不混用舊資料或不同口徑。

## 接收方式

- Telegram：成功產圖時只發圖片；產圖工具不可用或內容超過上限時，沿用文字備援。圖片傳送失敗會記錄失敗，不宣稱通知成功。
- Email：同一封信上方顯示圖卡，下方保留完整報告及可點擊的資料來源。純文字郵件閱讀器仍能讀到完整報告。
- Email 沿用 `EMAIL_SENDER`、`EMAIL_PASSWORD`、`EMAIL_RECEIVERS`；寄件驗證資料必須放在 Secrets。程式修改不會自動建立信箱或取得寄件授權。

### Gmail 設定

在 GitHub 的 **Settings → Secrets and variables → Actions** 設定：

- `EMAIL_SENDER`：寄件 Gmail 地址。
- `EMAIL_RECEIVERS`：收件地址；多個地址用逗號分隔，留空則寄給自己。
- `EMAIL_PASSWORD`：Google 應用程式密碼，放在 Secret；不使用一般登入密碼。

建立應用程式密碼需要先啟用 Google 兩步驟驗證，部分帳戶可能不提供此選項；請參考 [Google 官方說明](https://support.google.com/mail/answer/185833?hl=zh-Hant)。信箱地址與驗證資料不寫入程式碼或提交紀錄。

## 圖卡內容

台股總覽呈現實際交易日、盤勢一句話、加權／櫃買指數、成交金額與前日比較、上市／上櫃法人買賣超、股票漲跌家數、強弱類股、下次觀察與風險。上市與上櫃分開；法人單位為新臺幣金額。

個股圖卡呈現名稱與代碼、分析結論、價格與漲跌幅、支撐／現價／壓力價位軸、主要依據、法人動向、行動條件與風險。個股法人數據與市場總覽可能採不同單位，以圖中標示為準。

缺資料時顯示未取得，不當成零。行動條件保留原報告，例如「跌破且無法收復時，考慮減倉」，不改成「跌破就停損」。圖卡無法顯示所有細節，需搭配 Email 完整報告查閱。

## GitHub Actions

此 Fork 的每日分析預設：

| Variable | 預設值 | 用途 |
| --- | --- | --- |
| `MARKDOWN_TO_IMAGE_CHANNELS` | `telegram,email` | 圖片接收管道；設為 `none` 改回文字 |
| `MD2IMG_ENGINE` | `playwright` | 使用 Chromium 產圖 |
| `MARKDOWN_TO_IMAGE_MAX_CHARS` | `15000` | 原報告超過上限時改用文字 |
| `SINGLE_STOCK_NOTIFY` | `true` | 每檔個股各發一張卡 |

既有同名 Variable／Secret 會優先於預設值。預設工作流程在 `apps/dsa-web` 安裝既有 Node 依賴、Playwright Chromium 與 Noto CJK 字型。安裝失敗仍可繼續分析並嘗試文字備援。

本機測試可沿用 `MD2IMG_ENGINE=playwright`，先於 `apps/dsa-web` 安裝依賴與 Chromium，再使用既有 `src.md2img.markdown_to_image`。預覽檔與測試截圖不提交至原始碼倉庫。
