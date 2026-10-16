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

兩個面，之間只能透過一次工具呼叫穿過去。

**狀態面**在行程內。代理之間不互相傳值，而是從 `PipelineState` 讀 `payload` 與前序報告，各自只寫一格 `*_report`。`completed` 只增不改，所以稽核軌跡不會被後面的節點改寫。

**工具面**是唯一的對外出口。每次呼叫都經過 `invoke`，在 adapter 執行前先比對 `ACCESS`。adapter 拋錯會被收斂成錯誤物件，所以一個壞掉的整合只降級一個步驟。

對應原始碼：[`state.py`](../src/agentcp/state.py)、[`tools.py`](../src/agentcp/tools.py)

## 3. 資料狀態

![資料狀態](state.svg)

14 個欄位，每一格都只有一個寫入者，圖上把它標出來。

**第三列是重點**：`human_decision` 只有「恢復一個被中斷的執行」時寫得到。任何代理都設不了它——這就是為什麼「審查者不能代替人核可」是一個**結構性質**，而不是一條大家記得遵守的慣例。

對應原始碼：[`state.py`](../src/agentcp/state.py)、[`agents.py`](../src/agentcp/agents.py)

## 4. 使用情境

![使用情境](scenarios.svg)

[`examples/run_pipeline.py`](../examples/run_pipeline.py) 的六個情境，每個都可以直接跑：

```bash
uv run --with langgraph python examples/run_pipeline.py approve
```

**六個裡有三個的結果是「沒有部署」**，這是刻意的：對一條部署流水線來說，值得看的正是它拒絕的那些情況。

---

| 視圖 | 由哪些測試釘住 |
|---|---|
| 程式流程 | `test_routing.py`、`test_handoff.py` |
| 資料流 | `test_tool_access.py` |
| 資料狀態 | `test_hitl.py` |
| 使用情境 | 七個測試檔全部 |
