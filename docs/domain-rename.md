# 域變更對照表

> **已確認，執行中。** 定案與提案有一處不同：`triage` **不改名**。
> 它本來就是通用詞（把進來的東西按嚴重度分流），在語料收錄的語境下一樣讀得通，
> 而且保住 `triage_report` 讓改動範圍縮小。`approval_gate` 同樣不動。

---

## 為什麼換，以及換之後靠什麼保護

現在的域是**軟體交付流水線**（Ticket → 規劃 → 審查 → 部署）。README 用一句話論證它：
「在**另一個領域**從零重做那些決策」——領域不同本身就是一層保護。

換成與那套私有系統**同域**之後，兩者的距離縮短了。所以保護必須改由**詞彙的通用程度**
承擔，而不是靠領域距離。這份提案的三條規則：

1. **不出現任何指向性詞彙**——專案名、`harbor`、RUL、感測器、振動、預測性維護、
   剩餘壽命、退化曲線，一律不用。這些詞只要出現一個就認得出來。
2. **不複製那套系統的代理名冊。** 照搬一整組名字，看過兩邊的人會立刻對上。
   本提案維持 demo 現有的「**四個代理 + 一個閘門**」結構，不改成七個。
3. **域選在「業界到處都有的那一層」**：知識庫／檢索語料的**收錄與發布**流程。
   這個形狀在任何做 RAG 的團隊裡都一樣，不指向任何人。

**README 那段論證要一起改寫。** 不能留著「另一個領域」那句話——它會變成一句假的話，
而這個 repo 剛剛花了兩天清掉假的話。新的說法應該是：**域是刻意選在通用的那一層，
好讓決策看得見而來源看不出來。**

---

## 一、節點與代理

| 現在 | 提案 | 這一步做什麼 | 有判斷點嗎 |
|---|---|---|---|
| `triage` | `triage`（**不變**） | 這份文件可否收錄、敏感度為何 | **有**（分級） |
| `planner` | `indexer` | 切塊、寫出索引項目 | 無 |
| `reviewer` | `assessor` | 內容忠實度評分，可否發布 | **有**（評斷） |
| `approval_gate` | `approval_gate`（不變） | 消化人工決定 | 無 |
| `deployer` | `publisher` | 把項目推上線上索引 | 無 |

為什麼是這五個名字：

- `assessor` / `publisher` 是檢索語料維運的通用詞，單獨看不指向任何系統。
- **`triage` 刻意不改**：它描述的是「按嚴重度分流」這個動作，與域無關，
  而那套私有系統的對應節點叫另一個名字。保留現名反而降低對應性。
- **`approval_gate` 刻意不改。** 它是機制名稱而非域詞彙，而且那套私有系統用的是
  另一個名字——保持現名反而降低對應性。
- 刻意**不用** `curator`、`ingest_guard`、`quality_assessor`、`drift_sentinel`、
  `governance_gate`。這些是那套系統的實際名稱，照用就是第 2 條規則要防的事。

## 二、狀態欄位

| 現在 | 提案 |
|---|---|
| `triage_report` | `triage_report`（**不變**） |
| `plan_report` | `index_report` |
| `review_report` | `assessment_report` |
| `deploy_report` | `publish_report` |

`next_agent`、`requires_approval`、`human_decision`、`step_count`、`max_steps`、
`completed`、`calls`、`tokens_used`、`budget_tokens`、`trace_id`、`tenant`、
`sensitivity`、`PROTECTED` **全部不動**——它們是控制平面的詞彙，與域無關。

## 三、Trigger 與路由表

| 現在 | 提案 | 路由到 |
|---|---|---|
| `ticket_opened` | `document_submitted` | `triage` |
| `ticket_reopened` | `document_resubmitted` | `triage` |
| `plan_ready` | `index_ready` | `indexer` |
| `code_pushed` | `draft_updated` | `assessor` |
| `review_requested` | `assessment_requested` | `assessor` |
| `review_changes_requested` | `revision_requested` | `indexer` |
| `review_passed` | `assessment_passed` | `publisher` |
| `deploy_requested` | `publish_requested` | `publisher` |
| `deploy_failed` | `publish_failed` | `triage` |

九個 trigger、九條路由，數量與拓撲**完全不變**——只換詞。
`test_every_trigger_in_the_type_has_a_route` 與三表一致的斷言都不受影響。

## 四、工具與權限表

| 現在 | 提案 | 誰可以用 |
|---|---|---|
| `read_ticket` | `read_document` | `triage`、`indexer` |
| `label_ticket` | `tag_document` | `triage` |
| `write_plan` | `write_index` | `indexer` |
| `read_diff` | `read_draft` | `assessor` |
| `post_comment` | `post_finding` | `assessor` |
| `read_plan` | `read_index` | `publisher` |
| `deploy` | `publish` | `publisher` |

七個工具、四個代理的白名單形狀不變。`TENANT_DENY` 的 `"trial": {"deploy"}`
變成 `"trial": {"publish"}`——`trial` 租戶不能發布，和原本「不能部署」同一個意思。

## 五、情境名稱：不動

`approve`、`reject`、`ignore`、`rework`、`budget`、`gate`、`mask`、`residency`、
`quota`、`gemma` **全部保留**。它們命名的是**機制**（核可、退回、預算、遮罩、
地域否決、配額），不是域。改掉只會讓十個情境與文件裡的交叉引用全部要重對。

但各情境的**散文要改**，因為它們講的是域裡的故事：

- `approve` ——「有人說可以，然後才發布」（原本是「才部署」）
- `rework` ——「評斷者退回，步數守衛結束迴圈」（原本是「審查者退回」）
- `residency` ——受限**語料**不得離開部署（原本是受限內容）

## 六、Fixture 資料

| 現在 | 提案 |
|---|---|
| `{"ticket": 4821, "pr": 318}` | `{"document": 4821, "draft": 318}` |
| `{"id": 4821, "title": "Login returns 500 on submit", "reporter": "support"}` | `{"id": 4821, "title": "Calibration procedure, revision C", "submitter": "support"}` |
| `{"pr": 318, "files": 2, "additions": 34, "deletions": 6, "author": ..., "built_on": ...}` | `{"draft": 318, "sections": 2, "added": 34, "removed": 6, "author": ..., "built_on": ...}` |
| `{"steps": ["reproduce locally", "fix null session", "add regression test"]}` | `{"chunks": ["split by section", "strip boilerplate", "attach source refs"]}` |
| `{"workflow": "deploy.yml", "run_id": 99214, "env": "production"}` | `{"index": "corpus-live", "revision": 99214, "tier": "published"}` |

**PII 仍放在 draft 而不是 document**。理由不變：`assessor` 只把判決寫進 state，
所以那些值進得了模型的 context 而進不了 checkpoint；而 `triage_report` 會把整份
文件存進 state，PII 放那裡就會被寫進 checkpoint。這個理由與域無關，照舊成立。

---

## 七、會被動到的檔案（25 個）

### 程式（7）
`src/agentcp/{state,router,tools,agents,graph}.py`、`examples/{adapters,run_pipeline}.py`
、`examples/gemma_judge.py`（`CALL_SITES` 的兩段指示文字與 schema 的 enum 不變，
但指示要改成「收錄」與「評斷」的用語）

### 測試（14）
全部 14 個 `tests/test_*.py` 加 `conftest.py`。**116 條測試必須全部跑過**，
而域詞彙改錯一個字就會紅——這是這次改動唯一的安全網，也是它的風險所在。

### 文件（中英各半）
`README.md`、`README.zh-TW.md`、`docs/architecture{,.zh-TW}.md`、
`docs/design{,.zh-TW}.md`、`docs/scope{,.zh-TW}.md`

### 圖（4 張 + 4 份來源）
`docs/src/{flow,dataflow,state,scenarios}.json` 與對應 SVG。
**全部要用 `fireworks-tech-graph` 重繪**，而算繪器 `text_policy: strict`
不接受任何截斷——新詞如果比舊詞長，可能要調卡片寬度或座標。
上次重繪 `state.svg` 就因為一個標籤變長而被拒絕一次。

---

## 八、兩份不改的檔案

`docs/errata.md`（68 處域詞彙）與 `docs/fix-plan.md`（26 處）是**固定在舊 commit
的歷史紀錄**。在裡面改名會把紀錄本身改掉——而那正好違反建立 errata 的理由
（Knuth 6.1：記錄每一個錯誤，而一份會跟著被記錄的東西一起移動的紀錄不是紀錄）。

處理方式：兩份檔案開頭各加一句，說明這份紀錄寫於域變更之前，裡面的節點名是
當時在用的，並指向這份對照表。

---

## 九、風險

1. **最大的風險是「改一半」。** 550 處詞彙分佈在 25 個檔案，漏掉一處就會留下
   兩個域混用的狀態——那比完全不改更難讀。對策是改完做一次全域掃描：
   舊詞彙在 `src/`、`tests/`、`examples/`、README、`docs/`（排除 errata 與 fix-plan）
   的命中數必須是 **0**。
2. **SVG 可能算繪失敗。** 新詞比舊詞長（`assessment_report` 比 `review_report` 長
   五個字元），四張圖都可能需要調座標。退路是該張圖這一輪不改 JSON，並在
   errata 記一筆待辦——不要留下 JSON 與 SVG 不一致。
3. **README 貼的輸出要全部重貼。** 情境輸出裡的 trail、報告欄位名、工具名全變。
4. **保護的淨效果要自己判斷。** 詞彙通用化之後，demo 與那套系統的**結構**對應
   仍然存在（四個代理 + 閘門 + 單一模型入口 + 稽核紀錄）。這份提案能降低
   **詞彙**層面的指向性，不能消除**結構**層面的相似——後者正是這個 repo 的價值
   所在，無法同時保留價值又消除相似。這一點要你自己衡量。

---

## 十、定案

1. 節點名：`triage`（不變）/ `indexer` / `assessor` / `approval_gate`（不變）/ `publisher`
2. 九個 trigger：照第三節
3. fixture 用「通用技術文件」口吻（`Calibration procedure, revision C`）
4. **結構相似無法消除，已接受。** 詞彙通用化降低詞彙層面的指向性；四個代理 +
   閘門 + 單一模型入口 + 稽核紀錄這個結構對應仍然存在，而那正是這個 repo 的價值。
