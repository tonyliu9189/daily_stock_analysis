# 此 Fork 的上游版本自動更新

此流程追蹤 GitHub 所記錄的原始 Fork 來源之最新正式 Release。定期準備候選合併，完成測試後才更新正式分支。沒有新版時安靜結束。它不會使用 AI 修復合併衝突，也不會呼叫股票分析模型。

## 啟用前

1. 將 `.github/workflows/upstream-update.yml`、`scripts/upstream_update.py` 與相關測試發布到預設分支。
2. 不需新增長期更新憑證。只有發布工作使用 GitHub 內建的臨時 `GITHUB_TOKEN`，明確要求 `contents: write`；準備與測試仍為唯讀。由於 `.github` 全部受保護，自動更新不接受任何工作流程變更，也不要求 Workflows 寫入權限。若組織或分支規則限制更新，流程停止而不繞過權限。
3. 通知沿用 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID`。缺少憑證、機器人被封鎖或 Telegram 故障時，通知本身會失敗；此時從 Actions 查看結果。不能保證任何錯誤都能送達 Telegram。
4. 先在 Actions → **上游版本自動更新** → Run workflow，保留「只演練」勾選。演練會測試候選版本，可能送出一則結果通知，但不更新正式分支、不建立遠端備份。
5. 演練通過後，再新增 Repository Variable `UPSTREAM_SYNC_ENABLED=true` 開啟自動更新。移除或設為 `false` 可停用排程更新。手動測試仍可使用。

排程預定為每日台灣時間 **07:23**（UTC 23:23）；GitHub 可能延遲，這不是保證執行時間。股票分析原本的排程不變。手動取消「只演練」會嘗試真正更新。內建權杖推送不會自動觸發一般 push 工作流程；本流程已在推送前完成自己的檢查，股票分析仍依原排程觸發。

## 如何保留客製與正式版本

- 準備步驟在暫時的本機 Git 分支合併，產生 Git bundle（含候選提交的封裝），不推送正式分支。
- `PROTECTED` 清單位於 `scripts/upstream_update.py`。台股資料、圖卡、共用分析及通知客製程式、既有回歸測試、工作流程、模型設定、環境檔、依賴、測試設定與載入鏈、更新程式及治理規則只要有差異，就停止並要求人工檢查。
- 這是刻意保守的限制：上游即使做了合理調整，只要碰到受保護檔案也可能被擋住。不可為了自動更新而直接移除保護或略過失敗測試。
- 其他未受保護程式可以合併，但須通過保留的台股／通知測試、完整離線 Python 測試、Web lint 與建置。必要台股測試還會核對 JUnit 結果，避免只收集測試、全部跳過或漏跑某個必要模組卻宣稱通過。測試無法證明所有行為完全正確。
- 所有測試在不持有發布、Telegram 或模型金鑰的獨立工作環境執行。更新與通知在另外的工作環境，使用原正式版的程式。
- 更新前重新核對正式分支是否仍為測試時的基線，推送時再以明確的 `--force-with-lease=refs/heads/<正式分支>:<原 SHA>` 做伺服器端條件鎖。候選提交必須以原正式版為第一父提交，因此不允許用這個選項覆寫不同版本或倒退歷史；即使主分支只是在最後讀取後變動，也會停止。
- GitHub 最後使用原子推送，同時建立 `upstream-backups/<舊版完整 SHA>` 備份分支與更新正式分支；其中任何一項被拒絕就不更新。
- 正式分支若受保護而不允許此憑證直接更新，流程會停止；不要自動關閉分支保護。此版本不使用 PR 自動合併，因此不需要開啟 GitHub 的 Allow auto-merge。

## 結果與還原

Actions 保留每次執行紀錄，候選封裝保留七天。無新版不通知；合併衝突、受保護檔案改動、測試失敗或憑證問題會嘗試傳 Telegram 通知並附執行連結。

測試及更新流程本身也可能被取消或遇到 GitHub 故障，通知可能來不及執行。錯誤發生在推送後的遠端核對階段時，不能說「一定沒更新」，必須查實際分支 SHA。

備份分支只是還原點，不會自動回退。若更新後的正式股票分析出現問題，先停用排程更新，再檢查備份與最新提交，經使用者授權以新提交回復相關變更；不要直接強制覆寫正式分支。

## 驗證界線

Python 回歸在獨立 Linux 網路命名空間執行，只開啟本機迴路、不提供外網介面，並降低到無法重新取得管理員權限的原執行使用者。環境也不提供模型或通知金鑰。隔離設定失敗就停止，不退回有外網的測試。依賴安裝與 Web 建置仍需要外網，但不提供模型或通知金鑰。

不做付費模型與真實寄報測試。圖片渲染與實際 Telegram／Email 傳送仍需獨立驗證，不能因 Python／Web 測試通過就宣稱正式通知正常。

如果目前版本的既有離線測試失敗，更新也會停止；應查明測試失敗原因，不直接排除測試來讓更新通過。

## English summary

This fork can stage the latest stable release from its verified parent, test a pinned candidate without write or notification secrets, and atomically publish an old-version backup plus the tested default branch. Protected fork files stop automation on any change. Enable only after a successful rehearsal using `UPSTREAM_SYNC_ENABLED=true`. Only the publish job requests Contents write permission for the built-in temporary GITHUB_TOKEN; workflow changes are blocked and no long-lived personal token is needed. There is no paid model call, guaranteed Telegram delivery, automatic conflict repair, or automatic rollback. Native PR auto-merge is not used.
