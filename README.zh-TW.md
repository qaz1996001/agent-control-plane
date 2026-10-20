*[English](README.md) ｜ 繁體中文*

# agent-control-plane — 讓模型在步驟「裡面」做判斷，不要讓它決定步驟「之間」怎麼走

一個可以直接執行的小專案，用來示範一個主張：**Agent 的控制平面應該是普通的程式碼。** 路由、權限、預算、遮罩、供應商選擇、人工核可，分別就是一張查找表、一份白名單、一個計數器、一次字串代換、一道否決、一次中斷——不是拿去問模型、期待它每次都答對的東西。

```bash
uv run --with pytest --with langgraph pytest -q                    # 116 passed
uv run --with langgraph python examples/run_pipeline.py            # 10 個情境
```

底下每一項主張都對應那十個情境裡的一個，而每個情境都會把實際發生的事印出來。多數情境的結尾是**沒有發布**。這正是預期的形狀：對一條收錄發布流水線來說，值得看的是它**拒絕**的時候，而拒絕的方式比放行的方式多。

執行層用 LangGraph（節點執行、checkpoint，以及讓「等人核可」成為真正暫停的 interrupt）。但路由策略是一個吃 state 的普通函式，**不建圖也測得出來**。

程式實際怎麼跑的四個視圖——程式流程、資料流、資料狀態、使用情境——在 [docs/architecture.zh-TW.md](docs/architecture.zh-TW.md)。哪些東西**刻意不做**、以及為什麼，在 [docs/scope.zh-TW.md](docs/scope.zh-TW.md)。

領域選的是檢索語料的收錄與發布流水線——一份文件先被分流，然後建索引、被評斷，扣在人工閘門前，最後才推上線上索引——因為在這個領域，「是 Agent 自己決定要發布的」是一句你不會想講出口的話。而這個域刻意選在**通用的那一層**，理由寫在本頁最後的「這是從哪來的」。

---

## 問題

把控制流交給 LLM，你會得到一個這樣的系統：

- 同一個輸入明天可能走不同的路，所以失敗的執行**無法重放比對**；
- 路由走錯是「提示詞的 bug」——你得改措辭、重跑評測，而不是讀一行程式碼；
- 「這一步可以用哪些工具」寫在提示詞裡，那是**請求**，不是檢查；
- 發布可能只是因為模型被說服了應該發布。

這些都不是反對使用模型，而是在講**用在哪裡**。

## 決策

| | 模型決定路由 | 查找表決定路由 |
|---|---|---|
| 同一 trigger，明天 | 可能不同 | 完全相同 |
| 路由錯了是 | 提示詞的 bug | 一行表格的 bug |
| 重放失敗的執行 | 近似 | 精確 |
| 證明「這裡沒有跑過模型」 | 做不到 | 一條測試 |

需要判斷的工作仍然交給模型——分類這份文件、評斷這份草稿。那些是可注入的 callable（`Judge`），而這同時讓「**把所有模型進入點都弄壞，控制平面照樣跑完**」從一句宣稱變成一條斷言。

### 六個性質，六個機制

**路由** — `ROUTE_TABLE` 把 trigger 對應到代理。未知的 trigger 直接拋錯，**不退回預設值**。一個打錯字的 trigger 靜靜地路由到 `publisher`，正是最該防的那種失敗。

> 在 `rework` 裡看得到：trail 就是那張表選的路線，而迴圈停在步數上限。由 `test_routing.py`、`test_handoff.py` 釘住。

**權限** — `ACCESS` 把代理對應到可用工具，在 `invoke` 裡**緊貼著呼叫點**檢查。`allowed()` 是同一張表的唯一來源，兩種讀法各取所需：`invoke` 拿它**做檢查**，`schemas_for` 拿它**做算繪**，而一條測試對每個 (代理, 租戶) 組合釘住兩者一致。這個 repo 沒有任何節點讓模型自己挑工具，所以那層算繪是「將來要接 tool-calling」的那道縫，不是這條流水線走到的東西——一致性先釘住，因為那是便宜的那一半。工具拋錯會被收斂成 `{"error": ...}`，**保證例外不會穿透進圖**，一個壞掉的整合也就殺不掉一個正握著人工核可的執行。但「那個步驟會降級」是另一句話，而且目前還不成立：沒有任何呼叫端去看那個 key，error 物件就這樣被當成資料傳下去。見 [docs/errata.md](docs/errata.md) 的 D4。

> 在 `approve` 裡看得到：它會印出 `tools called` 清單——四個代理、四個工具。由 `test_tool_access.py` 釘住。

**預算** — `BudgetedStream` 逐塊計數，一跨過預算就在**串流中途**拋錯。它用估算，因為它必須在真實用量回來之前就做決定；`settle()` 之後再用供應商的真實數字覆寫，稽核紀錄不會停留在那個近似值上。**跨過預算是一次拒絕，不是備註**：執行會像配額用盡那樣停住，而被切斷的答案會被丟棄、不會因為「欄位剛好還在」就被採用。

> 跑 `budget`：它先示範守衛本身，再示範在三種預算下對一次執行做了什麼。由 `test_budget.py`、`test_audit.py` 釘住。

**預算與租戶配額都做不到的那件事**，情境裡也寫明了：一次把答案給完的 judge，在任何東西能開始計數之前，就已經生成並被計費了整份回覆。在那個時間點拒絕買到的是**正確性，不是額度**。兩者在結構上完全對稱，在 `consult` 裡隔幾行先後檢查，而且都是**呼叫之前**的閘門：帳本是 judge 回傳之後才扣的，所以配額用盡擋的是**下一次**呼叫，不是這一次。**已經在途的那一份回覆，這裡沒有任何機制擋得住。** `BudgetedStream` 的逐塊守衛是為一個它還沒被餵進來的串流而寫的——`_chunks` 切的是一份早就完整抵達的回覆。

**核可** — graph 以 `interrupt_before=["approval_gate"]` 編譯。執行走到閘門就停住並存檔。在有人帶著決定恢復它之前，什麼都不會發布；而**帶著「沒有決定」恢復一樣會拒絕**——沒有決定不等於同意。

> 三個情境、一個機制：`approve`、`reject`、`ignore`——最後那個就是「不帶決定恢復」。由 `test_hitl.py` 釘住。

**遮罩** — `privacy.mask` 在模型看到之前，把地址、內部主機名、帳號代號換成佔位符；這一半每一次執行都會跑到。`restore` 是同一套機制的另一半，而它是這條流水線**走不到**的那一半：被遮罩的是送給 judge 的**脈絡**，而 verdict 是模型自己的話，所以一次執行的答案裡根本沒有我們放進去的佔位符可還原——`consult` 回傳那份映射，執行就把它丟了。`restore` 只對握有權限的檢視者還原，而且沒有權限時**整段拒絕**，不做「能還原多少算多少」：部分還原照樣外洩，而且讀起來像是什麼都沒被扣住。映射綁定這一次執行，而且永不寫進 state——因為 state 會被 checkpoint。

> 跑 `mask`：它會印出模型看到的佔位符文字，以及 `restore` 被拒絕的兩種方式。它在一般執行裡也會啟動：draft fixture 帶了作者信箱與建置主機，所以 `approve` 與 `gemma` 的 assessor 那筆 call record 是 `masked: True`。由 `test_privacy.py` 釘住。

**供應商選擇** — `providers.choose` 依序套三道過濾：健康狀態、地域**否決**、成本偏好。受限內容碰不到遠端供應商，**即使那是唯一還活著的那個**——答案是「沒有供應商」，不是「就這一次」。容錯可以跨成本偏好，永遠不能跨否決。

> 跑 `residency`。它最後一列才是重點：唯一還活著的供應商是遠端的，答案仍然是拒絕。由 `test_providers.py` 釘住。

這六件事在同一個地方交會。`agents.consult` 是整個套件裡唯一呼叫 `Judge` 的函式，所以遮罩、供應商選擇、預算、租戶配額、稽核紀錄是**結構上**被碰到的，不是靠每個節點記得去碰。有一條測試斷言不存在第二道門。

> `quota` 就是「只有一道門」在租戶配額用盡時的樣子：執行拒絕，而那次嘗試仍然留在紀錄裡（`test_quota.py`）。`gate` 是另一種閘門——評測門檻，加上同一指標的漂移（`test_evals.py`、`test_drift.py`）。第十個 `gemma` 把一個真的模型放在那道門後面，見下。

---

## 怎麼跑

```bash
uv run --with langgraph python examples/run_pipeline.py            # 十個情境全跑
uv run --with langgraph python examples/run_pipeline.py approve    # 只跑一個
```

十個情境，每個都把實際發生的事印出來：

| 情境 | 展示什麼 |
|---|---|
| `approve` | 執行暫停、人核可、**然後才**發布 |
| `reject`  | 人工拒絕 —— publisher 拒絕執行，`publish` 從未被呼叫 |
| `ignore`  | 不帶決定恢復 —— 一樣拒絕 |
| `rework`  | 評斷退回；迴圈停在步數上限 |
| `budget`  | 過長的回應在中途被切斷，之後真實用量覆寫估算值 |
| `gate`    | 發布被評測閘門擋下、修好後放行；同一指標的漂移偵測 |
| `mask`    | 模型看到的是什麼，以及還原被拒絕的兩種方式 |
| `residency` | 唯一健康的供應商在遠端、內容受限，答案仍然是不 |
| `quota`   | 租戶額度用盡——執行拒絕，而且這次嘗試照樣留下紀錄 |
| `gemma`   | 由真的本地模型做判斷；路徑不因此改變 |

`approve` 的輸出（節錄）：

```
--------------------------------------------------------------------------
approve -- a human says yes, and only then does it publish
--------------------------------------------------------------------------
  paused at    ('approval_gate',)          <- 執行停住了，不是在輪詢
  published?   False

  ...a curator approves in Slack / the web UI...

  trail        triage -> indexer -> assessor -> approval_gate -> publisher
  steps        5 / 8
  triage_report      {'severity': 'normal', 'document': {'id': 4821, 'title': 'Calibration procedure, revision C', 'submitter': 'support'}}
  index_report       {'entry': {'chunks': ['split by section', 'strip boilerplate', 'attach source refs']}}
  assessment_report  {'approved': True, 'comments': [], 'text': 'draft assessed, no blocking findings.'}
  publish_report     {'published': True, 'result': {'index': 'corpus-live', 'revision': 99214, 'tier': 'published'}}
  model calls  2  (triage->local-small unmasked, assessor->local-small masked)
  tokens       16 / 2000   (0/2 settled against the provider's count)

  tools called ['read_document', 'write_index', 'read_draft', 'publish']
```

`rework`，評斷一直退回的情況：

```
  trail        triage -> indexer -> assessor -> indexer -> assessor -> indexer
  steps        6 / 6
  triage_report      {'severity': 'normal', 'document': {'id': 4821, 'title': 'Calibration procedure, revision C', 'submitter': 'support'}}
  index_report       {'entry': {'chunks': ['split by section', 'strip boilerplate', 'attach source refs']}}
  assessment_report  {'approved': False, 'comments': ['add tests']}
  model calls  3  (triage->local-small unmasked, assessor->local-small masked, assessor->local-small masked)
  tokens       36 / 2000   (0/3 settled against the provider's count)

  the loop did not run forever; max_steps decided when to stop
```

### 最後一個情境：把真的模型插進判斷的那個縫

上面九個情境不需要模型、不需要網路。最後一個情境 `gemma` 跑的是和 `approve`
完全相同的流程，只是判斷由真的模型來做——本地 Ollama 上的 Gemma 4 E4B：

```bash
ollama pull gemma4:e4b                                           # 約 6.6 GB
uv run --with langgraph python examples/run_pipeline.py gemma
```

它在預設執行清單裡。前九個情境依然不需要模型也不需要網路；Gemma 沒有在跑的話，
這個情境會印出缺什麼然後跳過，而不是爆掉——所以沒裝 Ollama 的 clone 行為和以前完全一樣。

接法在 [`examples/gemma_judge.py`](examples/gemma_judge.py)，約 200 行、
全部用標準庫——**沒有新增任何依賴**，因為 `Judge` 就是
`(prompt, context) -> dict`，契約只有這樣。
**adapter 刻意住在 `examples/`，不在 `src/agentcp` 裡。**
在 `src/` 下 import 一個供應商，等於把測試對控制平面做出的那個斷言撤回；
模型應該和 `adapters.py` 裡其他的整合縫放在一起。

實際由 Gemma 4 E4B 作答的輸出（節錄）：

```
  model said  '{"severity": "low"}'
  model said  '{\n  "approved": true,\n  "comments": [\n    "The change is
                small and localized (2 sections, low diff), which is
                good.", ... ]\n}'

  with the model:
  trail        triage -> indexer -> assessor -> approval_gate -> publisher
  steps        5 / 8
  triage_report      {'severity': 'low', 'document': {'id': 4821, ...}}
  publish_report     {'published': True, 'result': {'index': 'corpus-live', 'revision': 99214, 'tier': 'published'}}
  model calls  2  (triage->local-small unmasked but answered by ollama:gemma4:e4b, ...)
  tokens       1084 / 2000   (2/2 settled against the provider's count)

  severity     'normal' (default)  ->  'low' (Gemma)
  same trail?  True        <- routing is code, not a prompt
  same steps?  5 vs 5
  published?    True         <- still only because a human said yes

  estimated    73 tokens   <- the char heuristic, from the visible reply
  provider     1084 tokens   <- eval_count, which includes Gemma's
               hidden reasoning: 15x the estimate.

  rejected     0   every reply matched the schema
```

模型對嚴重度的判斷和預設值不同——它把一份例行的程序改版讀成 `low` 而不是 `normal`——
而路徑一步都沒變，因為沒有任何地方把路徑交給它決定。回覆的用詞也是模型自己的，
那正是這道縫的意義，也是它誠實的邊界：判斷的內容就是模型說的那樣，
而控制平面對它做的唯一一件事，是在邊界把型別檢查過。

這個情境特意要展示三件事：

- **它把流程跑兩次**——一次用確定性預設值、一次用 Gemma——然後比對。
  路徑與步數完全相同，改變的只有判斷的**內容**。路由兩種情況下都是一張查找表。
- **模型的回覆在邊界被型別檢查。** 兩個呼叫點的輸出形狀是已知的，所以直接以
  JSON schema 送出去、再拿回來驗證。嚴重度不在列舉內、verdict 不是布林、
  回覆是空的：一律拒收、計數、換成預設值。**降級的是那個步驟，路徑不會動。**
  這就是「模型在步驟*裡面*做判斷」與「模型決定步驟*之間*怎麼走」的差別。
- **它終於讓 `settle()` 有東西可證。** 預算守衛必須在供應商回報用量之前就做決定，
  所以它只能照看得見的字元去估。而 Gemma 4 E4B 會先推理再作答，`eval_count`
  把那段推理也計費：這次執行是 **1084 tokens 對上估算的 73**。估算不是小幅偏差，
  是差一個數量級，而且**偏在要命的那個方向**——帳本若留著估算值，就會把帳少報這麼多。
  這正是 record 為什麼把 `tokens_actual` 分開放、而且在真實數字到達前一律留 `None`。

## 真的要上線怎麼接

`examples/adapters.py` 就是整合面。裡面每個工具都是會記錄「它本來要呼叫什麼」的 stub，所以**接縫是可以數的——註冊了七個，節點實際走到的是四個**。另外三個（`tag_document`、`post_finding`、`read_index`）被允許、也接好了，但目前沒有節點呼叫；輸出裡的 `tools called` 是誠實的那一份清單。

| stub | 真實環境換成什麼 |
|---|---|
| `read_document`、`tag_document` | 收件那一側——一個追蹤系統的 REST client、一個文件庫 |
| `read_draft`、`post_finding` | 草稿與意見實際住的地方——Git 平台的審閱 API、一套 CMS |
| `write_index`、`read_index` | 你自己的儲存——一張表、一個向量索引 |
| `publish` | 索引那一步：CI 觸發、一個建索引的 job、換一次 alias |

換一個就是換一個函式；註冊表不知道、也不需要知道憑證從哪來。

**什麼驅動一次執行。** 一個 webhook 把進來的事件對應成 `Trigger`，然後帶著 thread id 呼叫 `invoke`——thread id 通常就用文件或草稿的編號，這樣**重送的 webhook 會恢復同一次執行，而不是開第二次**。trigger 的詞彙刻意是封閉集合，就是為了讓這個對應是一本讀得懂的字典，而不是一段提示詞。

**人在哪裡看到這個暫停。** 執行停住時，`app.get_state(cfg).next` 是 `("approval_gate",)`，而 state 裡帶著評斷代理的報告。這些資訊足以算繪出一則 Slack 訊息或一個網頁，附上證據與兩顆按鈕；按鈕用同一個 thread id 呼叫 `invoke` 並帶上 `Command(update={"human_decision": ...})`。**沒有任何輪詢，而且暫停期間不花成本。**

**上線前要換掉的東西。** 持久化的 checkpointer，暫停才撐得過重啟——`MemorySaver` 會掉。掛鉤已經在了，而且已經拒絕假裝：`build_graph(durability="require")` 會直接拋錯而不是退回預設，連明確傳一個 `MemorySaver` 進去都不算數。工具要有行程或容器隔離，因為白名單是授權、不是隔離。配額要換成共享計數器，因為這裡的帳本是單行程的，兩個 worker 各自拿到完整額度。還有評測閘門後面要接一個真的計分器，它目前是吃指標、不是產生指標。

完整的「做了什麼、沒做什麼、什麼條件會讓它重新被打開」在 [docs/scope.zh-TW.md](docs/scope.zh-TW.md)。


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
- `publish` 只有一個代理搆得到，用反查斷言
- 會拋錯的工具回傳 `{"error": ...}`，不往外炸
- **每個代理被提供的 schema 等於它的白名單**，逐一驗過
- 不存在的代理拿到空清單

**核可**（`test_hitl.py`）
- 執行是真的停住：`snapshot.next == ("approval_gate",)` 且此時還沒有 `publish_report`
- 核可 → 發布；拒絕 → 結束但不發布，並寫明原因
- **不帶決定恢復，照樣拒絕發布**
- 機器判定通過的評斷只會設 `requires_approval`，**不會寫 `human_decision`** —— 所以評斷者沒有代替人核可。而**一個偏要寫的節點會拋錯**，因為 `build_graph` 拒絕任何指名 `state.PROTECTED` 欄位的 patch；拔掉那層包裝會讓四條測試變紅。它曾經只是慣例，見 [docs/errata.md](docs/errata.md) 的 A1

**交棒**（`test_handoff.py`）
- 每個代理只寫自己那一個 `*_report`，不碰別人的
- 評斷不通過會交棒回收錄者
- 收錄者 ↔ 評斷者的循環**正好停在 `max_steps`**
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

**遮罩**（`test_privacy.py`）
- 遮罩後的文字**整段**都不含任何真實值——對整個字串斷言，不是只檢查被代換到的位置
- 同一個值重複出現共用同一個佔位符，模型仍然看得出兩次提到的是同一個實體
- **沒有權限時整段拒絕還原**，不做「能還原多少算多少」
- 一個 run 的映射解不開另一個 run 的佔位符
- 模型自己掰出來的佔位符維持原樣，不會被解開

**供應商選擇**（`test_providers.py`）
- **受限內容絕不送到遠端供應商，即使遠端是唯一還活著的那一個**
- 容錯跨得過成本偏好，跨不過地域否決
- 拒絕時說得出理由，不是單純失敗
- 每一次選擇都帶著稽核紀錄要存的那個理由

**稽核與單一道門**（`test_audit.py`）
- **`consult` 是唯一呼叫 `Judge` 的地方**——多一個入口就會讓遮罩、預算、稽核全部變成選配
- Judge 只看得到遮罩後的文字
- **還原用的映射永遠不會進到被 checkpoint 的 state**
- 每個會呼叫模型的節點，恰好留下一筆紀錄
- 執行的 token 計數器等於它所有呼叫紀錄的總和
- 被預算切斷的回應、以及被直接拒絕的呼叫，**兩者都照樣留下紀錄**
- 還沒結算的紀錄，跟「結算成估算值」的紀錄分得出來

**租戶與配額**（`test_tool_access.py`、`test_quota.py`）
- 租戶規則只能收窄角色、**永遠不能放寬**，對每個 (代理, 租戶) 組合都驗過
- 提供的 schema 對每個 (代理, 租戶) 組合都等於白名單
- 一個租戶用盡額度不會動到另一個租戶的
- 超額的例外帶著 `retry_after`
- 撐破上限的那一筆花費照樣被記進去
- 被收走 `publish` 的租戶會讓 publisher **寫明理由後拒絕**，而不是炸掉並弄丟一個已經給出的核可

**持久化**（`test_durability.py`）
- `durability="require"` 卻沒有儲存時**直接拋錯，不靜默退回**記憶體 saver
- 明確傳一個 `MemorySaver` 進去也不算數——問題是暫停撐不撐得過重啟
- **其他任何 saver 都是被信任而放行的**，而測試的名字就這麼寫：這道守衛是一張「已知行程內儲存」的黑名單，而型別說不出一個儲存撐不撐得過行程

**策略快照**（`test_evals.py`）
- 判決會記下它當初是依哪一組閾值判的
- **事後調高標準，不會改寫先前的判決**

---

## 限制

寫出來是因為一個藏起邊界的示範沒有用。

- **測試不會真的呼叫模型。** 需要判斷的點是可注入的 callable，測試用確定性假物件。這讓整套測試離線可跑、也讓「控制平面沒有模型」那條測試有意義。`gemma` 情境確實會呼叫本地的真模型，但那是**示範那個縫**，不是測試覆蓋：這裡沒有驗證真實 tokenizer 的計數，供應商的故障模式也只處理了「連不上」與「回覆格式錯」兩種。
- **預設的 checkpoint 只在記憶體裡。** `MemorySaver` 足以展示 interrupt／resume。`durability="require"` 存在，是為了「暫停必須撐過重啟」的場合，而它拒絕「沒有儲存」的兩種形式：完全沒傳，以及明確傳一個 `MemorySaver`。它是一張**已知行程內儲存的黑名單，不是對持久性的驗證**——型別裡沒有任何東西說得出一個 saver 撐不撐得過重啟，所以其他 saver 都是**被信任**而非被驗證。這個 repo 沒有附任何持久化儲存。
- **遮罩是規則比對，不是 NER。** 地址、內部主機名、帳號代號，靠 pattern。結構化的識別資訊涵蓋得到，人名與自由文字裡的不行。偵測器變好時機制不會變，變的只有召回率。
- **配額帳本是單行程的。** 兩個 worker 各自拿到完整額度，所以真正的天花板是「限額 × worker 數」。共享的強制執行需要共享計數器與一個儲存。
- **供應商健康狀態是一個硬編常數。** `choose` 接收呼叫端相信還活著的那一組，但 `agents.HEALTHY` 是模組層級常數，`build_graph` 也沒有任何參數能注入，所以流水線的呼叫端根本遞不進一份健康視圖——那個常數就是接縫本身。正式版會逐供應商追蹤失敗並在冷卻後半開；可移植的是排序規則。
- **沒有任何防護機制。** 沒有注入偵測、沒有輸出過濾、沒有提示洩漏檢查。離線環境下，它們只能用「寫出這些 pattern 時依據的那些例子」來測，那種測試一定會過而且什麼都不證明。見 [docs/scope.zh-TW.md](docs/scope.zh-TW.md)。
- **沒有沙箱。** 工具在同一個行程裡執行。真實的 Agent 執行環境需要行程或容器隔離加上網路政策；這裡的白名單是**授權模型，不是隔離機制**。
- **評測閘門沒有計分器。** 它吃指標、做判斷。從 golden 題庫對真實系統算出那些數字才是比較大的那一半，不在範圍內。
- **單執行緒、單次執行。** 沒有並行、沒有佇列、沒有退避重試。重試語意在另一個 repo（`idemingest`）裡示範，不在這裡重複。

---

## 這是從哪來的

我在工作上做過一套 Agent 平台——七個代理配一個確定性的 supervisor、帶租戶權限的工具層、核可閘門、評測閘門與漂移偵測——那份程式碼是私有的。這個 repo 是把其中的**決策**從零重做一次，讓它們看得見。

**這裡沒有使用該系統的任何程式碼。** 帶過來的是推理過程，寫在 [docs/design.zh-TW.md](docs/design.zh-TW.md)；而邊界——那套系統的哪些能力在這裡重現、哪些刻意不做——寫在 [docs/scope.zh-TW.md](docs/scope.zh-TW.md)。

**為什麼選這個域。** 它刻意選在通用的那一層：分流、收錄、評斷、閘門、發布，是任何一個在維運知識庫的團隊本來就有的形狀，所以那些決策讀得出來，而來源讀不出來。保護來自**詞彙足夠普通**，不是來自**領域足夠遙遠**。這句話要照它真正的大小說：它降低的是**用詞**的指向性，而**結構**上的相似一點都沒有少——四個代理配一道確定性的路由、單一一個模型入口、一道人必須經過的閘門、一份稽核紀錄。那個結構就是這個 repo 的全部價值，所以它不是我能一邊拿掉、一邊還留著東西可看的部分。詞彙是刻意通用的；形狀不是，也不該是。

### 哪些地方比原系統更嚴格

四個性質裡有兩個**不是重現，而是跟原系統的爭論**。寫出來比讓讀者以為生產環境已經這樣運作要好。

- **路由完全碰不到模型。** 原系統遇到**未知的** trigger 時，會問模型該由哪個代理處理——由 feature flag 控制，回傳值會用代理清單驗證。那是個站得住腳的逃生門，但也正是這個 repo 要反對的東西。這裡未知的 trigger 直接拋錯，並且有一條測試斷言「把所有模型進入點毒化後控制平面照樣跑完」。**沒有人為它寫過路由的事件，應該浮上來被看到，而不是被安靜地指派掉。**
- **工具權限是一張會被檢查的表。** 原系統沒有 per-agent 白名單。每個節點直接 import 它需要的函式，所以「這一步可以用哪些工具」是一個關於 import 的慣例，不是呼叫點上的檢查。`ACCESS` 就是那個慣例被寫下來並強制執行之後的樣子——而且「將來要提供給模型的 schema」由同一張表生成，讓「宣告可用」與「實際允許」不可能各走各的。這裡還沒有任何地方把它提供出去；一致性是在有東西依賴它之前就先釘住的。

相對地，核可閘門**確實是重現**：閘門節點上同樣的 `interrupt_before`、同樣放在 state 裡的 `human_decision`、以及「不帶決定恢復」時同樣的答案。

工作上用的是 LangGraph，這裡也是，理由一樣：interrupt 是那種不值得自己重造的部分。

MIT 授權。
