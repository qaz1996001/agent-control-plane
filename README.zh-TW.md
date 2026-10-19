*[English](README.md) ｜ 繁體中文*

# agent-control-plane — 讓模型在步驟「裡面」做判斷，不要讓它決定步驟「之間」怎麼走

一個可以直接執行的小專案，用來示範一個主張：**Agent 的控制普通的程式碼。** 路由、權限、預算、人工核可分別就是一張查找表、一份白名單、一個計數器、一次中斷——不是拿去問模型、期待它每次都答對的東西。

```bash
uv run --with pytest --with langgraph pytest -q      # 44 passed
```

執行層用 LangGraph（節點執行、checkpoint，以及讓「等人核可」成為真正暫停的 interrupt）。但路由策略是一個吃 state 的普通函式，**不建圖也測得出來**。

程式實際怎麼跑的四個視圖——程式流程、資料流、資料狀態、使用情境——在 [docs/architecture.zh-TW.md](docs/architecture.zh-TW.md)。

領域選的是軟體交付流水線——Ticket → 規劃 → 審查 → 部署——因為在這個領域，「是 Agent 自己決定要部署的」是一句你不會想講出口的話。

---

## 問題

把控制流交給 LLM，你會得到一個這樣的系統：

- 同一個輸入明天可能走不同的路，所以失敗的執行**無法重放比對**；
- 路由走錯是「提示詞的 bug」——你得改措辭、重跑評測，而不是讀一行程式碼；
- 「這一步可以用哪些工具」寫在提示詞裡，那是**請求**，不是檢查；
- 部署可能只是因為模型被說服了應該部署。

這些都不是反對使用模型，而是在講**用在哪裡**。

## 決策

| | 模型決定路由 | 查找表決定路由 |
|---|---|---|
| 同一 trigger，明天 | 可能不同 | 完全相同 |
| 路由錯了是 | 提示詞的 bug | 一行表格的 bug |
| 重放失敗的執行 | 近似 | 精確 |
| 證明「這裡沒有跑過模型」 | 做不到 | 一條測試 |

需要判斷的工作仍然交給模型——分類這張 ticket、審查這份 diff。那些是可注入的 callable（`Judge`），而這同時讓「**把所有模型進入點都弄壞，控制平面照樣跑完**」從一句宣稱變成一條斷言。

### 四個性質，四個機制

**路由** — `ROUTE_TABLE` 把 trigger 對應到代理。未知的 trigger 直接拋錯，**不退回預設值**。一個打錯字的 trigger 靜靜地路由到 `deployer`，正是最該防的那種失敗。

**權限** — `ACCESS` 把代理對應到可用工具，在 `invoke` 裡**緊貼著呼叫點**檢查。提供給模型的 schema 由同一張表生成，所以「宣告可用」與「實際允許」不可能各走各的。工具拋錯會被收斂成 `{"error": ...}`，讓一個壞掉的工具只降級一個步驟，而不是殺掉一個正握著人工核可的執行。

**預算** — `BudgetedStream` 逐塊計數，一跨過預算就在**串流中途**拋錯。它用估算，因為它必須在真實用量回來之前就做決定；`settle()` 之後再用供應商的真實數字覆寫，稽核紀錄不會停留在那個近似值上。

**核可** — graph 以 `interrupt_before=["approval_gate"]` 編譯。執行走到閘門就停住並存檔。在有人帶著決定恢復它之前，什麼都不會部署；而**帶著「沒有決定」恢復一樣會拒絕**——沒有決定不等於同意。

---

## 怎麼跑

```bash
uv run --with langgraph python examples/run_pipeline.py            # 六個情境全跑
uv run --with langgraph python examples/run_pipeline.py approve    # 只跑一個
```

六個情境，每個都把實際發生的事印出來：

| 情境 | 展示什麼 |
|---|---|
| `approve` | 執行暫停、人核可、**然後才**部署 |
| `reject`  | 在閘門被拒 —— `deploy` 從未被呼叫 |
| `ignore`  | 不帶決定恢復 —— 一樣拒絕 |
| `rework`  | 審查退回；迴圈停在步數上限 |
| `budget`  | 過長的回應在中途被切斷，之後真實用量覆寫估算值 |
| `gate`    | 發布被評測閘門擋下、修好後放行；同一指標的漂移偵測 |

`approve` 的輸出（節錄）：

```
--------------------------------------------------------------------------
approve -- a human says yes, and only then does it deploy
--------------------------------------------------------------------------
  paused at    ('approval_gate',)          <- 執行停住了，不是在輪詢
  deployed?    False

  ...a reviewer approves in Slack / the web UI...

  trail        triage -> planner -> reviewer -> approval_gate -> deployer
  steps        5 / 8
  deploy_report {'deployed': True, 'result': {'workflow': 'deploy.yml', ...}}

  tools called ['read_ticket', 'write_plan', 'read_diff', 'deploy']
```

`rework`，審查一直退回的情況：

```
  trail        triage -> planner -> reviewer -> planner -> reviewer -> planner
  steps        6 / 6
  the loop did not run forever; max_steps decided when to stop
```

### 選用：把真的模型插進判斷的那個縫

上面六個情境不需要模型、不需要網路。第七個情境 `gemma` 跑的是和 `approve`
完全相同的流程，只是判斷由真的模型來做——本地 Ollama 上的 Gemma 4 E4B：

```bash
ollama pull gemma4:e4b                                           # 約 6.6 GB
uv run --with langgraph python examples/run_pipeline.py gemma
```

它不在預設執行清單裡；模型沒裝的話情境會說明原因並跳過，而不是爆掉。

接法在 [`examples/gemma_judge.py`](examples/gemma_judge.py)，約 200 行、
全部用標準庫——**沒有新增任何依賴**，因為 `Judge` 就是
`(prompt, context) -> dict`，契約只有這樣。
**adapter 刻意住在 `examples/`，不在 `src/agentcp` 裡。**
在 `src/` 下 import 一個供應商，等於把測試對控制平面做出的那個斷言撤回；
模型應該和 `adapters.py` 裡其他的整合縫放在一起。

實際由 Gemma 4 E4B 作答的輸出（節錄）：

```
  model said  '{"severity": "critical"}'
  model said  '{"approved": true, "comments": ["Small, focused change across
                only two files. Looks ready to merge."]}'

  trail        triage -> planner -> reviewer -> approval_gate -> deployer
  steps        5 / 8

  severity     'normal' (default)  ->  'critical' (Gemma)
  same trail?  True        <- routing is code, not a prompt
  same steps?  5 vs 5
  deployed?    True         <- still only because a human said yes

  model calls  2
  rejected     0   every reply matched the schema
```

模型對嚴重度的判斷和預設值不同——登入噴 500 確實不該是 `normal`——
而路徑一步都沒變，因為沒有任何地方把路徑交給它決定。

這個情境特意要展示兩件事：

- **它把流程跑兩次**——一次用確定性預設值、一次用 Gemma——然後比對。
  路徑與步數完全相同，改變的只有判斷的**內容**。路由兩種情況下都是一張查找表。
- **模型的回覆在邊界被型別檢查。** 兩個呼叫點的輸出形狀是已知的，所以直接以
  JSON schema 送出去、再拿回來驗證。嚴重度不在列舉內、verdict 不是布林、
  回覆是空的：一律拒收、計數、換成預設值。**降級的是那個步驟，路徑不會動。**
  這就是「模型在步驟*裡面*做判斷」與「模型決定步驟*之間*怎麼走」的差別。

## 真的要上線怎麼接

`examples/adapters.py` 就是整合面。裡面每個工具都是會記錄「它本來要呼叫什麼」的 stub，所以**接縫是可以數的——總共七個**。

| stub | 真實環境換成什麼 |
|---|---|
| `read_ticket`、`label_ticket` | Jira / Linear REST client |
| `read_diff`、`post_comment` | GitHub / GitLab API |
| `write_plan`、`read_plan` | 你自己的儲存——一張表、一個 wiki 頁 |
| `deploy` | CI 觸發：Actions dispatch、Argo、Jenkins |

換一個就是換一個函式；註冊表不知道、也不需要知道憑證從哪來。

**什麼驅動一次執行。** 一個 webhook 把進來的事件對應成 `Trigger`，然後帶著 thread id 呼叫 `invoke`——thread id 通常就用 ticket 或 PR 編號，這樣**重送的 webhook 會恢復同一次執行，而不是開第二次**。trigger 的詞彙刻意是封閉集合，就是為了讓這個對應是一本讀得懂的字典，而不是一段提示詞。

**人在哪裡看到這個暫停。** 執行停住時，`app.get_state(cfg).next` 是 `("approval_gate",)`，而 state 裡帶著審查代理的報告。這些資訊足以算繪出一則 Slack 訊息或一個網頁，附上證據與兩顆按鈕；按鈕用同一個 thread id 呼叫 `invoke` 並帶上 `Command(update={"human_decision": ...})`。**沒有任何輪詢，而且暫停期間不花成本。**

**上線前要換掉的三件事。** 持久化的 checkpointer，暫停才撐得過重啟——`MemorySaver` 會掉。工具要有行程或容器隔離，因為白名單是授權、不是隔離。還有評測閘門後面要接一個真的計分器，它目前是吃指標、不是產生指標。


---

## 測試證明了什麼

測試才是這個專案的主體，實作刻意寫得很小。

**路由**（`test_routing.py`）
- `Trigger` 型別裡的每個 trigger 都有路由，每條路由也都有對應的 trigger——型別與表格不可能各自漂移
- 同一個 trigger 查五十次只有一個答案
- 打錯字的 trigger 會拋錯，並列出合法的集合
- **把所有模型進入點 monkeypatch 成拋錯之後，控制平面照樣跑** —— 路由只要碰過模型，這條就會紅
- 步數上限**同時壓過**待處理的交棒與待處理的核可，所以循環投不贏它

**權限**（`test_tool_access.py`）
- 代理呼叫別人的工具會被拒絕
- `deploy` 只有一個代理搆得到，用反查斷言
- 會拋錯的工具回傳 `{"error": ...}`，不往外炸
- **每個代理被提供的 schema 等於它的白名單**，逐一驗過
- 不存在的代理拿到空清單

**核可**（`test_hitl.py`）
- 執行是真的停住：`snapshot.next == ("approval_gate",)` 且此時還沒有 `deploy_report`
- 核可 → 部署；拒絕 → 結束但不部署，並寫明原因
- **不帶決定恢復，照樣拒絕部署**
- 機器判定通過的審查只會設 `requires_approval`，**永遠不會寫 `human_decision`** —— 審查者不能代替人核可

**交棒**（`test_handoff.py`）
- 每個代理只寫自己那一個 `*_report`，不碰別人的
- 審查不通過會交棒回規劃者
- 規劃者 ↔ 審查者的循環**正好停在 `max_steps`**
- 上限觸發後狀態仍然完整、事後查得出來

**預算**（`test_budget.py`）
- 串流停在**跨過預算的那一塊**，不是跑完才算帳
- 例外帶著 used 與 budget，呼叫端才能送出終止訊框並釋放配額
- `settle()` 用供應商的真實數字覆寫估算值
- 一個字元的區塊也不是免費的（估算無條件進位）

**評測閘門**（`test_evals.py`）
- 任一指標低於門檻即擋下，而且失敗訊息會寫出是哪個指標、差門檻多少
- **缺少的指標算 0 分**，不會因為沒出現就矇混過關
- **診斷指標再差也不擋發布**，並且斷言它根本沒有門檻設定
- 判斷函式是純的，不會改到傳進去的 dict

**漂移**（`test_drift.py`）
- 越高越好與越低越好走同一條比較；兩者「變差」一律是負的 z
- 視窗太短回報 `insufficient_data`，**不是 `ok`**
- 基線完全平坦回報 `insufficient_data`，而不是一個無限大的 z

---

## 限制

寫出來是因為一個藏起邊界的示範沒有用。

- **測試不會真的呼叫模型。** 需要判斷的點是可注入的 callable，測試用確定性假物件。這讓整套測試離線可跑、也讓「控制平面沒有模型」那條測試有意義。`gemma` 情境確實會呼叫本地的真模型，但那是**示範那個縫**，不是測試覆蓋：這裡沒有驗證真實 tokenizer 的計數，供應商的故障模式也只處理了「連不上」與「回覆格式錯」兩種。
- **checkpoint 只在記憶體裡。** `MemorySaver` 足以展示 interrupt／resume；真實部署需要持久化的 checkpointer，暫停才撐得過重啟。
- **沒有沙箱。** 工具在同一個行程裡執行。真實的 Agent 執行環境需要行程或容器隔離加上網路政策；這裡的白名單是**授權模型，不是隔離機制**。
- **評測閘門沒有計分器。** 它吃指標、做判斷。從 golden 題庫對真實系統算出那些數字才是比較大的那一半，不在範圍內。
- **單執行緒、單次執行。** 沒有並行、沒有佇列、沒有退避重試。重試語意在另一個 repo（`idemingest`）裡示範，不在這裡重複。

---

## 這是從哪來的

我在工作上做過一套 Agent 平台——七個代理配一個確定性的 supervisor、帶租戶權限的工具層、核可閘門、評測閘門與漂移偵測——那份程式碼是私有的。這個 repo 是把其中的**決策**在另一個領域從零重做一次，讓它們看得見。

**這裡沒有使用該系統的任何程式碼。** 帶過來的是推理過程，寫在 [docs/design.zh-TW.md](docs/design.zh-TW.md)。

工作上用的是 LangGraph，這裡也是，理由一樣：interrupt 是那種不值得自己重造的部分。

MIT 授權。
