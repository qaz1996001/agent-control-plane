*[English](architecture.md) ｜ 繁體中文*

# 架構 —— 四個視圖

[`design.zh-TW.md`](design.zh-TW.md) 講的是**為什麼**控制平面要是普通程式碼。這一頁講的是**程式實際做了什麼**，分四個視圖。

圖由 [`src/`](src) 裡的 JSON 產生；要改請改 JSON 重算，不要手改 SVG。

---

## 1. 程式流程

![程式流程](flow.svg)

`route()` 把 trigger 變成進入節點。每個節點跑完後，`next_node()` 套用固定的優先序：步數上限最先，其次待核可，再來明確交棒，最後停止。上限排第一，所以循環投不贏它。

`approval_gate` 以 `interrupt_before` 編譯，走到就停住並存檔。**核可與未核可兩條路最後都會走到 deployer**——拒絕的判斷在 deployer 裡面，這就是為什麼「不帶決定恢復」依然部署不了。

對應原始碼：[`router.py`](../src/agentcp/router.py)、[`graph.py`](../src/agentcp/graph.py)

## 2. 資料流

![資料流](dataflow.svg)

三個面，而節點只透過其中兩個碰到外面的世界——每一個都是單一一個函式。

**狀態面**在行程內。代理之間不互相傳值，而是從 `PipelineState` 讀 `payload` 與前序報告，各自只寫一格 `*_report`。`completed` 與 `calls` 只增不改，所以稽核軌跡不會被後面的節點改寫。

**工具面**是對外出口之一。每次呼叫都經過 `invoke`，在 adapter 執行前先比對 `allowed(agent, tenant)`。adapter 拋錯會被收斂成錯誤物件，所以**例外永遠不會穿透進圖**，一個壞掉的整合也殺不掉一個正握著人工核可的執行。至於「那個步驟會降級」，是這筆交易裡呼叫端要出的那一半，而目前沒有任何呼叫端去看那個 key——見 [`errata.md`](errata.md) 的 D4。

**模型面**是另一個，它就是 `consult`——整個套件裡唯一呼叫 `Judge` 的地方。遮罩、供應商選擇、預算、配額、稽核紀錄全部坐在這一個函式後面，所以它們不是節點需要「記得」的事。多開一個入口會讓以上每一項都變成選配，這就是 `test_consult_is_the_only_place_a_judge_is_called` 存在的理由。

**不**穿過任何一個面的，是還原用的映射。它在行程內回傳給呼叫端，從不寫進 state——因為 state 會被 checkpoint，而一份存著真實值的 checkpoint 等於在資料真正躺著的地方把遮罩解開。

對應原始碼：[`state.py`](../src/agentcp/state.py)、[`tools.py`](../src/agentcp/tools.py)、[`agents.py`](../src/agentcp/agents.py)、[`privacy.py`](../src/agentcp/privacy.py)、[`providers.py`](../src/agentcp/providers.py)

## 3. 資料狀態

![資料狀態](state.svg)

總共 18 個欄位。「只有一個寫入者」對四格 `*_report` 與 `human_decision` 成立，對其餘的不成立：`next_agent` 由四個節點寫，`step_count` 與 `completed` 由五個寫（每個節點都經過 `_advance`），`calls` 與 `tokens_used` 由兩個寫，`requires_approval` 也是兩個——審查者設起來、閘門清掉。而圖是把這些歸在「節點寫入」底下，沒有逐格指名，所以它標出的是一個欄位**什麼時候**被寫，不是被誰寫。

**`human_decision` 那一列是重點**：目前會寫它的只有「帶著決定恢復一個被中斷的執行」，而且沒有任何節點寫它。但那是節點的慣例，還不是 state 的性質——`PipelineState` 是裸 `TypedDict`，`graph.py` 把節點的 patch 原封不動併進 state，所以一個把 `human_decision` 放進自己 patch 的節點就偽造了一次人工核可，而沒有任何東西會退回它。這個缺口與打算用來補它的 reducer，記在 [`errata.md`](errata.md) 的 A1。

有四個欄位在 `new_state` 時設定一次，之後只讀不寫——`trace_id`、`tenant`、`sensitivity`、`max_steps`。它們是這次執行的身分與限制，執行過程中沒有任何東西可以放寬它們。在建立時就給每一個明確的值、而不是在使用點才套預設，是刻意的：**「沒設定」與「設定成預設值」不該讀起來一樣**。

對應原始碼：[`state.py`](../src/agentcp/state.py)、[`agents.py`](../src/agentcp/agents.py)、[`audit.py`](../src/agentcp/audit.py)

## 4. 使用情境

![使用情境](scenarios.svg)

[`examples/run_pipeline.py`](../examples/run_pipeline.py) 的情境，每個都可以直接跑：

```bash
uv run --with langgraph python examples/run_pipeline.py approve
```

**多數情境的結果是「沒有部署」**，這是刻意的：對一條部署流水線來說，值得看的正是它拒絕的那些情況，而拒絕的方式本來就比放行多。

---

| 視圖 | 由哪些測試釘住 |
|---|---|
| 程式流程 | `test_routing.py`、`test_handoff.py` |
| 資料流 | `test_tool_access.py`、`test_privacy.py`、`test_providers.py` |
| 資料狀態 | `test_hitl.py`、`test_audit.py` |
| 使用情境 | 十二個測試檔全部 |

這一頁沒有涵蓋的是**邊界本身**——原系統的哪些能力在這裡、哪些沒有、為什麼。那在 [`scope.zh-TW.md`](scope.zh-TW.md)。
