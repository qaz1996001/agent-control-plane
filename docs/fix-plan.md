# 修正計畫 —— 依 Knuth 哲學框架

> 本文件是一份修正計畫，不是宣告。每一項都附上「現在是什麼」的實測證據，
> 以及「改完之後要如何證明它成立」的驗收方式。
>
> **文中所有 `file:line` 引用都固定在 commit `eb66c3d`**——也就是這份計畫被寫下來
> 的那一刻。修正落地後程式位移，這些行號就不再指向原處；它們是**當時的座標**，
> 不是現在的。刻意不更新：一份記錄如果會跟著被記錄的東西一起移動，就不是記錄。
> 同樣的理由寫在 [`errata.md`](errata.md) 開頭。

---

## 為什麼用 Knuth 的框架來看這些問題

這個 repo 的問題不是程式不會跑——97 個測試全綠、10 個情境全部可執行。問題是
**文件宣稱的性質比程式做到的更強**。在一般專案裡這叫文件過期；但在這個專案裡，
文件就是產品本身——它存在的目的是把一組設計決策講清楚給人看。

Knuth 第二原則 2.1：

> 程式的首要讀者是人類，其次才是編譯器。
> 「程式 = 文檔 + 程式碼，兩者是一體的，不可分割。」

照這個標準，**一句說謊的文件就是一個程式 bug**，而且是比功能缺陷更嚴重的 bug：
功能缺陷讓程式少做一件事，假宣稱讓讀者把一條不存在的保證當成存在。

第三原則 3.3 精確性：

> 不容許模糊——如果你無法精確描述，你就不理解。

`docs/architecture.md:66-69` 寫「沒有代理能設定它，這就是⋯⋯**結構性質而非慣例**的原因」。
這句話不精確，而不精確正是它會錯的原因：作者想說的是「目前沒有節點這樣做」，
寫出來的卻是「不可能有節點這樣做」。

### 本計畫的決策規則

每一個缺口只有三種處理方式，選哪一種由宣稱的**種類**決定，不由修起來的難易決定：

| 宣稱的是 | 處理方式 | 依據 |
|---|---|---|
| 一個**機制** | 把機制做成結構性的，讓它不依賴任何人記得 | 6.3「內建診斷機制，而非事後添加」 |
| 一個**範圍** | 把範圍寫精確，明確說出做到哪裡、哪裡沒做 | 3.3 精確性 |
| 一個**願望** | 刪掉，或移進 `scope.md` 並寫明重新打開的條件 | 第四原則、反模式 4 |

**三種都不包含「加一個新功能」。** 第四原則 4.2：「優化一切會讓你不快樂」——
在示範性專案裡，為了讓一句話成真而長出一個半成品功能，會讓整份論證更難讀，
付出的代價大於贏回來的形容詞。

---

## 第 0 部分：錯誤日誌（先做，而且要公開）

Knuth 第六原則 6.1：

> 記錄你犯的每一個錯誤。即使這很可能相當尷尬，這些資訊是無價的。

他公開發表了 TeX 開發期間全部 850+ 個錯誤。6.2 更進一步——他為每個被找到的錯誤
付 $2.56，把被挑錯當成榮譽。反模式第 5 條：**隱藏錯誤才是恥辱，犯錯不是。**

所以這份計畫的第一個動作不是修程式，是**新增 `docs/errata.md`**，公開記錄這次審查
找到的每一個「宣稱強過證據」的實例，照 6.1 的要求分類。

### `docs/errata.md` 的內容骨架

每一筆記錄四件事：宣稱原文（含 file:line）、程式實際做的事、證明落差的實驗（指令與輸出）、
以及它屬於哪一類錯誤。

分類（照 6.1「分類錯誤」的要求，用這個專案自己的語彙）：

- **A 類：把慣例說成結構**——目前沒有程式碼違反它，但沒有任何東西阻止違反。
- **B 類：裝飾性測試**——測試的設定看起來在證明 X，但拔掉機制後斷言照樣通過。
- **C 類：無人抵達的機制**——程式與測試都在，但沒有任何執行路徑會走到它。
- **D 類：說得比做到的廣**——宣稱是通則，程式只在較窄的情況下成立。

為什麼這件事要**排在修程式之前**：一旦先修好程式，這些錯誤就會從歷史裡消失，
而 6.1 說那些資訊是無價的。先寫下來，修正時再在每一筆後面補上「如何修好的」。

這同時解決一個信任問題：一個把自己的誇大公開列出來的 repo，比一個看起來從未犯錯的
repo 更可信——因為讀者知道它用什麼標準檢查自己。

---

## 第 1 部分：文件的修正

這一部分只動文字，不動程式。原則是 3.3：把每一句話收窄到程式真正做到的範圍。

### 1.1 把「結構性質」改回「目前的慣例」——暫時的

`docs/architecture.md:66-69`、`src/agentcp/state.py:43-45`、`README.md:336-338`、
`docs/design.md:199`，以及生成圖 `docs/src/state.json` 的 `f3` / `f4` 節點
（「只有 resume 寫入 → human_decision」「沒有人能寫」）。

**實測**：一個節點把 `human_decision` 寫進自己的 patch，然後用
`app.invoke(None, cfg)`——也就是「不帶決定恢復」那條路——結果：

```
paused at      : ('approval_gate',)
resumed with   : None
human_decision : {'approve': True, 'reason': 'the agent decided'}
deploy_report  : {'deployed': True, ... 'env': 'production'}
```

另一個節點設 `next_agent = 'deployer'`：

```
trail         : triage -> deployer
ever paused   : ()
deploy_report : {'deployed': True, ... 'env': 'production'}
```

**處理方式**：這是一個**機制**宣稱，所以終局是第 4 部分的結構性修正。但文件的修正
要先做，而且順序很重要——在機制修好之前，文件必須說實話。兩段式：

1. 立刻把這些句子改成「目前沒有節點寫入它；下一節說明為什麼這還不夠」，
   並在 `docs/errata.md` 立下 A 類第一筆。
2. 第 4 部分的 reducer 與 key 剝除落地後，再把句子改成結構性的敘述——
   這次有測試背書，並在 errata 那一筆補上修正方式。

**不要跳過第 1 步直接做第 2 步。** 6.1 要的是記錄，不是掩蓋。

### 1.2 收窄預算與配額的花費宣稱

`README.md:91-95` 目前寫：「真正能限制花費的是租戶配額」。

**實測**：`trial` 租戶限額 500，一次呼叫回報 1,000,000 tokens：

```
這一次呼叫計費   : 1000000
ledger 事後餘額  : 0
這一次被拒絕了嗎 : True（事後）
```

`LEDGER.charge` 在 judge 回傳**之後**才發生（`agents.py:199`），所以配額擋的是
**下一次**，不是這一次。那句話是在修正一個誇大時寫下的另一個誇大。

**正確的說法**：預算與配額都是**呼叫前的閘門**，結構上完全對稱
（`agents.py:142` 與 `agents.py:150-151`）。對一個一次性回傳的 judge，
**沒有任何機制能擋住已經在途的那一次**；兩者能擋的都只有後續呼叫。
`BudgetedStream` 的逐塊守衛是為一個它還沒被餵的串流而寫的。

同時修 `docs/scope.md:46`「The budget bites mid-response」那一列，
以及 `src/agentcp/agents.py:30-32` 的註解「Chunk size the provider's prose is
streamed in」——那段散文不是串流來的，`_chunks` 是把一份已經完整抵達的回覆重新切塊。
這是 `src/` 裡最誤導的一行註解。

### 1.3 收窄「一個壞工具只降級一步」

`README.md:73-75`、`docs/design.md:88`、`docs/architecture.md:43-44`。

**實測**：讓 `read_diff` 拋 `RuntimeError('GitHub 503')`，跑 `approve`：

```
judge 被要求審查的內容 : {'text': 'error: RuntimeError: GitHub 503'}
review_report         : {'approved': True, 'comments': [], ...}
deployed              : True
tools actually called : ['read_ticket', 'write_plan', 'deploy']
```

`tools.invoke` 確實把例外收斂成 `{"error": ...}`，但**沒有任何呼叫端檢查那個 key**
（`grep -n '"error"' src/ examples/` 只找到生產者）。步驟沒有降級，
它在零資料上回報成功然後部署。

這是機制宣稱，終局在第 2 部分。文件先改成精確敘述：
`invoke` 保證的是**例外不會穿透進圖**，不是**步驟會降級**——後者需要呼叫端配合，
而目前沒有呼叫端配合。

### 1.4 收窄 `schemas_for`、`restore`、供應商健康視圖

三個都是 **C 類：無人抵達的機制**。處理方式一律是「寫精確」，不是接線
（接線就是第四原則警告的範圍膨脹）。

- **`schemas_for`**（`README.md:71-78`、`:329`、`:486-487`、`docs/scope.md:35`、
  `docs/design.md:56-60`、`:84`、`:96-98`）：改成——`allowed()` 是單一來源，
  `invoke` 對它**做檢查**、`schemas_for` 對它**做算繪**；這個 repo 沒有任何節點
  讓模型選工具，所以 `schemas_for` 是那件事未來要接上的縫，而測試先釘住
  「同一張表的兩種讀法一致」。
- **`restore` / `Viewer` / `Consultation.mapping`**（`privacy.py:1-23`
  「三個端點⋯⋯只有成套才有用」、`docs/design.md:102` 的流程圖、`README.md:106-111`）：
  `.mapping` 零消費者；而且流水線產出的「遮罩後答案」裡**根本沒有佔位符可還原**
  （遮罩的是 context，verdict 是模型自己的話）。`docs/scope.md:71` 已經誠實寫了
  「在行程內回傳後被丟棄」——把 README 與 design 的圖對齊到這句話。
- **供應商健康視圖**（`docs/scope.md:162`「`choose` 接受呼叫端相信還活著的集合」）：
  `agents.HEALTHY` 是硬編模組常數，`build_graph` **沒有任何參數**能注入。
  所以那句話對流水線的呼叫端不成立。改成：健康視圖目前是模組層級常數，
  真實部署要接的是這裡；並在 `scope.md` 的條件表裡寫明什麼情況會讓它變成參數。

### 1.5 修文件之間的矛盾與零碎不實

- `docs/design.md:39` 的 reject 路徑圖畫成「resume with approve=False → 直接 END」，
  實際行為是走到 `deployer`（`reject` / `ignore` 的輸出都證明了）。
  `docs/architecture.md:23-25` 寫對了。順帶：`approval_gate_node`（`agents.py:333-341`）
  **根本不讀 `human_decision`**，它只清一個旗標——所以 README 表格裡
  「declined at the gate / 在閘門被拒」這個說法本身不準，拒絕發生在 `deployer`。
- `docs/architecture.md:64`「18 個欄位每個都有唯一的寫入者，而且圖裡標明了」：
  18 這個數字對，但 `next_agent` 由四個節點寫、`step_count` / `completed` 由五個節點寫、
  `calls` / `tokens_used` 由兩個節點寫；而圖（`docs/src/state.json` 的 `f2`）
  是把它們歸成「節點寫入」而非指名——所以連「圖裡標明了」也過度宣稱。
- `examples/adapters.py:2-3`「每個 stub 都會**印出**它本來要呼叫什麼」：
  它只 append 到 `CALLS`，什麼都不印。`README.md:265-266` 寫對了（「records the call」）。
- `src/agentcp/state.py:4-5`「永遠不讀另一個代理的內部」：
  `deployer_node`（`agents.py:318`）讀 `state.get("plan_report")`。
  如果 `*_report` 算契約而非內部，就把這句話寫成那樣。

### 1.6 四個視圖的文件要跟著第 2～4 部分一起改

`docs/architecture.md` 的四個視圖與 `docs/src/*.json`（生成圖的來源）是同一份宣稱的
不同表現。第 2～4 部分每一項結構修正落地時，對應的視圖與 JSON 必須同時更新，
否則就會製造新的 A 類錯誤。中英兩版都算——**雙語是每一項文字工作的 2 倍成本，要先編進預算。**

---

## 第 2 部分：程式流程的修正

對應 `docs/architecture.md` 第 1 個視圖。這一部分處理「執行怎麼從一個節點走到下一個」。

### 2.1 工具錯誤必須讓步驟真的降級

**處理方式：結構性修正。** 這是 6.3「內建診斷機制」的典型案例——把檢查放在
**唯一的那道門**，而不是指望每個節點記得。

`consult`（`agents.py:85`）已經是所有判斷的單一入口，而且已經有四種拒絕
（無合格供應商、無租戶配額、無執行預算、回覆被切斷）。工具錯誤是第五種，
應該走同一條路：

- `consult` 在遮罩之前檢查 `context` 是否帶 `"error"` key，是則回傳 refusal，
  理由寫明是上游工具失敗、附上錯誤內容。
- 節點已經全部處理 `call.refused`（`triage` → `severity: unknown` 並停止，
  `reviewer` → `approved: False` 並停止），所以**節點不需要改**。
  這正是單一道門的回報。

**為什麼放在 `consult` 而不是每個節點**：`agents.py:12-13` 自己寫了
「一條每個節點都必須記得遵守的規則，就是一條新節點不會遵守的規則」。
把它放進節點就是製造下一個 A 類錯誤。

**驗收（3.2：證明與測試都要）**：
- 測試：`read_diff` 拋錯 → `review_report` 含 `refused`、`deploy_report` 不存在。
- **拔掉機制要會紅**：把 `consult` 的錯誤檢查註解掉，這條測試必須失敗。
  這是 B 類錯誤的解藥——每一條新測試都要通過這個檢驗。

### 2.2 讓毒化測試真的有牙齒

**問題**：`tests/test_routing.py:27` `test_routing_touches_no_model` 把兩個模型入口
換成會爆的函式，然後只呼叫 `route(trigger)`。而 `route()` 是三行字典查詢、
不呼叫任何東西——**實測：拿掉那兩行 monkeypatch，斷言照樣通過。**

**處理方式**：刪掉它，換成兩條**行為**測試，放進新檔 `tests/test_judgement_boundary.py`
（讓 `test_routing.py` 保持它 docstring 說的樣子：一個查表測試）。

- **對抗性 judge**：judge 回傳一個企圖奪權的 verdict——`next_agent: 'deployer'`、
  `requires_approval: True`、`human_decision: {'approve': True}`，同時 `approved: False`。
  **實測今天就會過**，而且是為了對的理由：

  ```
  trail          : triage -> planner -> reviewer -> planner
  next_agent     : reviewer       ← 節點自己設的，不是 judge 要的 deployer
  human_decision : None
  deployed?      : False
  ```

  圍堵它的是 state 欄位紀律：`reviewer_node` 把 verdict 整包寫進 `review_report`，
  然後自己設 `next_agent`。這是「我們把方向盤交給模型，它動不了車」——
  presence 式的證明，比 absence 式的「沒有東西呼叫模型」強得多。

  順帶一個發現：judge 的奪權 key 會被存進 `review_report` 並進 checkpoint
  （`review_report` 的 keys 會出現 `human_decision`、`next_agent`、`requires_approval`）。
  惰性無害，但讀 state 的人會看到 `human_decision: {'approve': True}` 躺在裡面。
  `consult` 已經會剝掉 `tokens` / `provider` 兩個 meta key，同一個位置順手剝掉
  控制平面自己的欄位名就解決了。

- **間諜 judge**：記錄每次被呼叫的 `prompt`，走完整張圖含恢復後的部署段，
  斷言 `prompts == ["classify severity", "review diff"]`，且 `completed`
  與不注入 judge 的執行逐項相同。這是「控制平面不依賴模型」的誠實形式：
  模型被呼叫兩次、在兩個指名的位置，而路線與它無關。

**為什麼不用原始碼檢查**：`graph.py:86` 的 `lambda s, _fn=fn: _fn(s, judge)`
本來就必須把 judge 交給節點——那是 graph 的職責。所以對 `graph.py` 做
「不得出現通往 judge 的路徑」的斷言，要嘛誤報，要嘛鬆到連節點呼叫 judge 都放行。
**這個宣稱無法表達成對 `graph.py` 的 grep。**

而且現有那條用同一招的測試本身就是可繞過的：`tests/test_audit.py:184-192` 用
`"(judge or " in inspect.getsource(fn)` 做子字串比對。**實測**：複製 `agents.py`、
加一個 `verdict = judge(state, {})` 的節點，`callers == ['consult']` 依然通過。
所以那不是可以沿用的成功範例，它是第四個同類問題——而 `docs/scope.md:66` 稱它是
「如果只能留一個決定，我會留這個」。

**同時要修那條測試**：把子字串比對改成對 `agents.py` 做 AST 走訪，
收集任何 callee 為 `Name("judge")` 的 `Call`（含包在 `BoolOp` 裡的），
並補一條行為測試——用計數 wrapper 包住 `consult`，斷言
`spy_judge.calls == consult_wrapper.calls`。同數才是真正的宣稱：
每一次 judge 呼叫都經過那道門。

可以保留的小 tripwire：只對 `router.py` 斷言它的 import 集合
⊆ `{agentcp.state, __future__}`。`router.py` 不像 `graph.py`，它確實不該認識 `agents`。
這條抓的是迴歸，不是當下的 bug。

### 2.3 把三張表釘在一起

`graph.py:25` 宣告 `NODE_NAMES`、`router.py:21` 宣告 `ROUTE_TABLE`、
`agents.py:354` 宣告 `NODES`。**沒有任何測試 import 過 `NODE_NAMES`**。

一條路由指向一個不是節點的代理，目前會在 `invoke` 時才炸，也就是在生產環境而不是 CI。
`test_every_trigger_in_the_type_has_a_route` 已經釘住了「trigger 型別 ↔ 路由表」，
這是同一條縫的另一半：

```python
set(ROUTE_TABLE.values()) <= set(graph.NODE_NAMES)
set(agents.NODES) == set(graph.NODE_NAMES)
set(Agent.__args__) == set(graph.NODE_NAMES)
```

六行，零風險（三條斷言今天都成立）。它賣的是這個 repo 已經賣過兩次的
同一類主張（「兩張表不可能各自漂移」），所以讀者零學習成本。

---

## 第 3 部分：資料流的修正

對應 `docs/architecture.md` 第 2 個視圖。這一部分處理「資料從哪裡來、被誰看到、去了哪裡」。

### 3.1 把遮罩印出來

`README.md:113-116` 叫讀者去 `approve` 與 `gemma` 的輸出裡觀察
「reviewer 的 call record 是 `masked: True`」。**那件事是真的**
（實測 `('reviewer', 'local-small', True, ...)`），但 `run_pipeline.show()`（`:44-66`）
印 trail、steps、報告、`model calls`、`tokens`——**從來不印 `masked`**。

對照 `README.md:16`：「底下每一項主張都對應那十個情境裡的一個，而每個情境都會把
**實際發生的事**印出來。」這是唯一一處 README 把讀者送去看證物、而證物沉默的地方。

兩行程式碼。這是整個 repo 裡最便宜的可信度。

### 3.2 重寫遮罩地圖那條測試

**問題**：`tests/test_audit.py:166-181` 斷言 `"pairs" not in repr(state)` 且
沒有 token 以 `<EMAIL` 開頭。兩個問題，都經實測：

```
測試的兩條斷言:
   "pairs" not in blob        -> True
   no token starts with <EMAIL -> True
但真實 email 在 checkpoint 裡嗎 -> True
它在哪                        -> {'ticket': 42, 'pr': 7, 'reporter': 'sam.okafor@example.com'}
```

1. 它檢查的是 `Mapping` dataclass 的**缺席**——而 `Consultation` 本來就不會把它
   放進 patch。所以這條測試釘不住任何關於遮罩的事（把 `privacy.mask` 換成 no-op，
   斷言照樣過）。
2. 文件真正在意的性質——「checkpoint 不得持有真實值」——**被這條測試自己的
   fixture 違反了**，因為 `payload` 是原封不動被 checkpoint 的。

諷刺的是 `examples/adapters.py:56-59` 的註解明確警告過「ticket fixture 放 PII
會被寫進 checkpoint」，而這條測試的 fixture 做的正是那件事。

**處理方式**：
- 測試改成斷言**真實值不在 checkpoint 裡**（而不是 Mapping 不在），
  並且要通過「拔掉機制會紅」的檢驗：把 `mask` 換成 no-op 必須讓它失敗。
- 然後面對一個真問題：`payload` 確實會被 checkpoint。兩個選項，建議**後者**——
  - (a) 讓 `new_state` 遮罩 `payload`：動到資料狀態語意，且 `payload` 是呼叫端
    給的識別資訊（ticket / PR 編號），遮掉會讓 thread id 的重放語意變混亂。
  - (b) **把範圍寫精確**：遮罩的邊界是**模型**，不是儲存。ticket 來自 Jira，
    你自己的資料庫早就有它了；遮罩要防的是把 PII 送給第三方模型，不是防自己存自己的資料。
    `docs/architecture.md:53-56`「checkpoint 持有真實值會讓遮罩在資料靜止處失效」
    這句話要收窄成：**不得把還原映射寫進 checkpoint**（這是真的，且有 `Consultation`
    的設計背書），而**來源資料本來就在你的系統裡**。

### 3.3 讓供應商選擇在真實路徑上被走到

**問題**：每一次呼叫、每一個情境都是 `("open", "low", 四個都健康)` → `local-small`。
否決從未觸發、健康過濾從未排除任何東西、第二層從未被選中
（`HIGH_COMPLEXITY_CHARS = 200`，而 `approve` 的遮罩後 context 長度是 61 與 105）。
`scenario_residency` 直接呼叫 `providers.choose`——沒有圖、沒有節點、沒有 `consult`。

機制是真的（強制條件下驗證過它端到端成立：`restricted` + 只有遠端健康，
走圖會得到 `severity: unknown` 與 `provider: 'none'`），但 README 把它當成
「十個情境示範的六個性質之一」，而沒有任何情境在流水線路徑上走到它。

**處理方式**：讓 `residency` 情境在直接呼叫之後再補一段走圖的執行。
這不是加功能——機制已經存在，只是從來沒被示範在它該被示範的抽象層次上
（第五原則 5.1 雙重視角：高層與低層都要看得見）。

同時照 1.4 收窄健康視圖的說法。

---

## 第 4 部分：資料狀態的修正

對應 `docs/architecture.md` 第 3 個視圖。**這是整份計畫裡唯一真正的程式缺陷**，
前面幾部分大多是文字與測試。

### 4.1 受保護的欄位必須在結構上受保護

**問題**：`PipelineState` 是裸 `TypedDict`，沒有 reducer、沒有驗證；
`graph.py:86` 把節點 patch 原封不動灌進 state。於是：

- 任何節點可以寫 `human_decision` → 偽造人工同意，連「不帶決定恢復」都會部署。
- 任何節點可以寫 `next_agent: 'deployer'` → 完全跳過閘門，一次 `invoke()` 部署。
- 任何節點可以改寫 `max_steps`（放鬆跑牆）、`sensitivity`（丟掉地域否決）、
  `tenant`（逃出租戶的 `TENANT_DENY` 與配額）、`trace_id`（重綁遮罩命名空間）。

**六個頭號機制有四個可以從這一個洞繞過。** 而 `docs/architecture.md:71-73` 寫
「這四個欄位⋯⋯**執行期間沒有任何東西可以放鬆它們**」。

**處理方式：結構性修正，而且 LangGraph 免費提供機制。** 兩層：

1. **`graph.py:86` 的 wrapper 剝掉受保護的 key。** 那一行已經是每個節點 patch
   的唯一出口（`lambda s, _fn=fn: _fn(s, judge)`），改成在回傳前濾掉
   `human_decision`、`max_steps`、`sensitivity`、`tenant`、`trace_id`。
   節點寫了也不會生效。

   這裡要做一個精確性決定（3.3）：**靜默剝除還是拋錯？** 建議**拋錯**——
   一個節點試圖寫 `human_decision` 是程式 bug，不是需要被容忍的狀況；
   靜默剝除會讓那個 bug 永遠不被發現。這和 `router.py` 對未知 trigger
   「直接拋錯，不退回預設值」是同一個判斷。

2. **`completed` 與 `calls` 加 `Annotated[list, operator.add]` reducer。**
   文件稱它們「append-only，後面的節點無法改寫稽核軌跡」
   （`state.py:48`、`:61-63`、`docs/architecture.md:38-39`），
   實際上 append-only 完全靠 `_advance` / `_bill` 自己寫 `[*state.get(...), x]`。
   加上 reducer 之後，一個節點回傳 `completed=["planner"]` 會變成**附加**而非取代。

   注意這會改變 `_advance` / `_bill` 的寫法（它們目前自己做拼接，加了 reducer
   會變成雙重拼接）——這是這整份計畫裡唯一一處需要小心的程式修改。

**`approval_gate_node` 順帶要修**：它目前**根本不讀 `human_decision`**，只清旗標
（`agents.py:333-341`）。既然閘門是這個 repo 的頭號機制，閘門節點應該是驗證
那個決定來自恢復而非來自節點的地方。

**驗收（每一條都要通過「拔掉機制會紅」）**：
- 節點寫 `human_decision` → 拋錯；移除剝除邏輯，測試必須紅。
- 節點寫 `next_agent: 'deployer'` → 閘門仍然攔住；
  移除剝除邏輯，測試必須紅（這條目前會綠，也就是會抓到今天的 bug）。
- 節點改寫 `max_steps` / `sensitivity` / `tenant` / `trace_id` → 四條，各自拋錯。
- 節點回傳 `completed=["x"]` → 前面的紀錄仍在；移除 reducer，測試必須紅。

這四組測試加起來，就是把 `docs/architecture.md` 第 3 個視圖從**散文**變成**斷言**。
在那之前，1.1 的文件修正必須已經落地——文件不能在機制之前就宣稱勝利。

### 4.2 `durability="require"` 的宣稱要收窄

`graph.py:49-52` 說它「拒絕編譯，除非 checkpointer 能活過行程」。
實際上（`graph.py:67-77`）它只拒絕 `None` 與 `MemorySaver` 的實例——是一張
只有一個項目的黑名單。而 `tests/test_durability.py:35-39` 的正向測試傳進去的
`FakeDurableSaver` 是一個裸 `BaseCheckpointSaver` 子類，docstring 寫
「代表一個活過行程的儲存」，實際上它沒有任何儲存，真的跑起來會 `NotImplementedError`，
而斷言只有 `is not None`——對那個守衛來說是套套邏輯。

**處理方式：寫精確**（這是範圍宣稱，不是機制宣稱）。
「拒絕假裝」的部分是真的也有價值——改成說它**拒絕已知的行程內儲存**，
而不是**驗證持久性**；後者在型別層面做不到。順帶修正那個正向測試的 docstring，
別讓它說自己是它不是的東西。

### 4.3 刪掉死掉的匯出 API

反模式第 4 條「浮於表面」的反面：一個讀者在檢查機制是否為真的時候，
翻到一個寫入但從未被讀的欄位，付出的信任成本遠大於刪掉它的兩行。

- `BudgetedStream.emitted`（`budget.py:56` 宣告、`:63` 寫入）——從未被讀，
  `consult` 自己維護一份（`agents.py:172`）。
- `evals.GoldenCase`（`evals.py:39-45`）——在 `__all__` 裡、零消費者、零測試。
  它的存在暗示有一組 golden set，而 `docs/scope.md:93-98` 正確地說那不在範圍內。
- `privacy.PLACEHOLDER`（`privacy.py:43`）——零消費者、零測試。

---

## 順序、成本與風險

嚴格照這個順序。每一階段都是下一階段的前提。

| 階段 | 內容 | 性質 | 風險 |
|---|---|---|---|
| **0** | `docs/errata.md`，記錄全部四類錯誤 | 新增文件 | 無 |
| **1** | 第 1 部分全部文字收窄（含 1.1 的第一段式） | 只動文字 | 無；但雙語 2 倍工 |
| **2** | 4.1 結構性修正 + 四組「拔掉會紅」的測試 | 動 `src/` | **最高**——動到 `graph.py:86` 與 `_advance` / `_bill` |
| **3** | 2.1 工具錯誤走 refusal | 動 `src/` | 中——會改變 `approve` 在工具失敗時的輸出 |
| **4** | 2.2 重寫毒化與單一道門測試、2.3 三表釘死、3.2 重寫遮罩測試 | 只動測試 | 低 |
| **5** | 3.1 印出 masked、3.3 走圖的受限情境 | 動 `examples/` | 低——會改變貼在 README 裡的輸出 |
| **6** | 1.1 第二段式：把文件改成結構性敘述 | 只動文字 | 無 |
| **7** | 4.2 收窄 durability、4.3 刪死碼、1.6 四個視圖與 `docs/src/*.json` 同步 | 混合 | 低 |

**跨階段的成本**：測試數會從 97 變動，所以 `README.md:12` 與中文版同一處每次都要跟上。
貼在 README 裡的輸出會在階段 3 與 5 之後需要重貼。**中英雙語讓每一項文字工作乘以 2。**

---

## 明確不做的事

第四原則 4.1 / 4.2，以及 `docs/scope.md` 存在的理由——把東西宣告為範圍外，
比半成品地做出來好。

- **不把 `gemma_judge` 改成真串流。** `Judge` 契約 `(prompt, context) -> dict`
  是 README 宣傳的穩定契約。要讓 `BudgetedStream` 中途掐斷生成，live stream
  必須穿過那個邊界 → `Judge` 得回傳 iterator → 動到 `consult`、兩個 `_default_*`、
  12 個測試檔裡每個假 judge，以及 `GemmaJudge` 裡「還沒讀完就無法驗證 schema」
  的那一步。而且光把 `"stream": True` 打開什麼都不會買到——judge 仍得讀完才能回 dict。
  **為了一個散文已經誠實放棄的形容詞，去改唯一一個被宣傳為穩定的契約。**
- **不接 tool-calling loop。** 把 `schemas_for` 餵給 Gemma、讓它選工具，
  是這裡任何人能加的最大一個功能；它會讓 `examples/gemma_judge.py` 翻倍，
  並強迫決定「模型講出一個被禁的工具時怎麼辦」。1.4 的文字收窄買到同一份誠實，
  成本是它的百分之一。
- **不加護欄、計分器、共享配額儲存、持久化 checkpointer。**
  `docs/scope.md:79-141` 已經逐項拒絕，並寫下會讓它重新打開的條件。
  那一頁是這個 repo 最好的資產，每加一個功能都在減損它。
- **不讓 `gemma` 情境更豐富。** 它已經帶著它唯一需要帶的東西：
  `settle()` 差了 14 倍（本機跑過兩次，輸出逐字相同）。那是整個 repo 裡
  最有說服力的一個實證事實。

---

## 一個仍然開放的判斷

`drift.py` 與 `evals.py` 都**沒有接進流水線**——`drift.detect` 除了 `__init__.py`
的 export 之外沒有任何 `src` 呼叫者。`docs/scope.md:16-20` 把這個 repo 的邊界
定義成「控制平面性質——誰可以做什麼、資料可以去哪、執行何時停止」，
而漂移偵測三個都不是。

它不是沒根據的宣稱，是**有根據的無關**——這是示範性 repo 變難讀的另一種方式。

兩個選項，偏後者，但這該由作者定：
- **刪掉** `drift.py`、`test_drift.py`、`scenario_gate` 的漂移那半，以及對應的
  README / scope / design 條目。約 90 行與 7 個測試。
- **留著**，但在 `scope.md` 用一句話說明 `evals.run_gate` 與 `drift.detect`
  都沒有接進流水線——它們是**發布閘門策略，不是執行閘門策略**。
  這樣能一句話堵掉讀者的「等等，誰在呼叫這個？」

偏向留著 `evals`（政策快照、不設門檻的診斷指標、缺少的指標算 0 分，
都是 design doc 真的論證過的決定），並對 `drift` 也採同樣的一句話處理。
