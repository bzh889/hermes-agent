# Hermes 原生功能、MTK Teams 整合與 Skype／Graph 能力差異研究

> **研究日期：2026-07-30**
> **性質：change-local ephemeral research；實作前必須重新驗證 live upstream、tenant 權限與真實 Teams 行為。**
> 本文只做研究與整合排序，不修改 OpenSpec、程式碼或 credentials。

## Executive summary

1. **目前 `teams_mtk` 並不是另一套簡化 agent。** Inbound 最終走 `BasePlatformAdapter.handle_message()`，因此 session、memory、skills、cron、delegation、tool execution、queue／steer、approval文字指令與Hermes agent loop均可共用。核心缺口主要在 **Teams transport seam與能力接線**，不是要重造Hermes core。來源：`gateway/platforms/teams_mtk.py:4807-4856 @ b102a4239`。
2. **原背景agent的「僅3項缺口」結論錯誤，不能採用。** `tasks.md`目前有21個unchecked；其中2個是應改成closed/不做，7個已有部分code但checkbox或接線未完成，12個仍是真正的實作／收尾項。此外，現行OpenSpec還漏列了至少3組重要缺口：inbound edit revision、structured quoted reply／outbound native reply，以及voice/video native media。
3. **最高風險不是少一個便利功能，而是Query修訂會丟失。** 相同message ID的已編輯訊息被`<= last_message_id` cursor直接跳過；SDK normalizer沒有保留edit version、`replyToId`或完整reply metadata；blockquote只留下80字摘要；`MessageEvent`也未填`reply_to_message_id`／`reply_to_text`。因此「修改原問題」或「引用原問題再修訂」目前不能可靠整合成新Query。
4. **多個方法雖已寫入`teams_mtk.py`，但不等於聊天中可用。** `search_all_conversations()`、`get_activity()`、`get_call_logs()`、`forward_message()`、`list_whitelisted_groups()`存在；但全repo沒有gateway command／tool dispatch呼叫它們。`get_platform_hints()`也只有definition與unit test，沒有runtime consumer。這些狀態應標成「code present, not agent/chat-native integrated」，不能標完成。
5. **官方Teams plugin不能整包搬進MTK。** 官方路徑使用Azure Bot Framework／`microsoft-teams-apps`、public webhook與bot credentials；MTK路徑使用使用者身分的Skype MSG/ChatSvc、Trouter WebSocket＋HTTP poll及部分Graph delegated API。應選擇性移植behavior contract，不應混用credential或並存兩個inbound source造成duplicate dispatch。
6. **AIDE與OpenAI Codex是provider層，與Teams transport解耦。** Teams訊息仍進同一個`AIAgent`路徑。AIDE host／model／quota／fallback錯誤，或Codex OAuth錯誤，應獨立診斷；不能標成Skype／Graph regression。
7. **安全整合順序應是：Query revision correctness → fail-closed authorization → chat-native dispatch → WS observability/policy → native media → optional Bot Framework UX → docs/checklist。** 在任何一步刪除舊SDK/raw fallback前，都要有命名真實Teams E2E等價證據。

## 1. Scope and method

### 1.1 Baselines

<table>
<thead><tr><th>基線</th><th>值</th><th>如何驗證</th><th>限制</th></tr></thead>
<tbody>
<tr><td>目前MTK branch</td><td><code>mtk-integration</code>, <code>b102a4239cb6025e105ca01688813c31f44b97c9</code></td><td>本機<code>git rev-parse HEAD</code></td><td>工作樹另有使用者文件變更；本文只新增／改寫本research.md。</td></tr>
<tr><td>local最後一次已合入的官方commit</td><td><code>339d968689a3b91c5f537d7198ff28abde32ab3b</code>, 2026-07-26</td><td>本機git object；subject為<code>fix(setup): stop asking about self-configuring platform knobs</code></td><td>這才是目前branch的官方base；不是stale <code>origin/main</code>。</td></tr>
<tr><td>本機stale <code>origin/main</code></td><td><code>f36c89cd5798da0f313192555739975e57ffdef5</code></td><td>本機<code>git rev-parse origin/main</code></td><td>不可拿它當live upstream。</td></tr>
<tr><td>研究時固定的官方live source</td><td><code>11089899fbb3ec1c043427c680e8fd8f4cab06c9</code>, 2026-07-30T09:24:16Z</td><td>GitHub官方<code>commits/main.atom</code>＋同SHA的<code>codeload.github.com</code>source archive</td><td>研究期間main已繼續前進；實作前必須重抓。</td></tr>
</tbody>
</table>

### 1.2 Fetch limitation

依研究要求實際執行了`git fetch origin main`，但Windows安全政策攔截Git子程序：

```text
error: cannot spawn git: Permission denied
```

因此本文**不聲稱fetch成功**。替代驗證使用GitHub第一方Atom feed鎖定SHA，再下載同SHA的官方source archive並直接讀取。GitHub REST因企業共用出口回403，故沒有拿REST結果冒充成功。

### 1.3 Evidence levels

- **Current source-confirmed**：本輪直接讀目前工作樹或固定官方SHA原始碼。
- **Current unit-confirmed**：本輪重新執行指定測試並取得輸出。
- **Historical real E2E claim**：`tasks.md`／E2E registry記載過真實Teams E2E，但本輪未重跑；只可作歷史證據。
- **Unknown**：tenant scopes、private Skype contract或live行為未直接驗證，明確保留未知。

本輪targeted regression實際執行：

```text
scripts/run_tests.sh \
  tests/gateway/platforms/test_teams_mtk_phase2.py \
  tests/gateway/platforms/test_teams_mtk_core_guards.py \
  tests/gateway/platforms/test_teams_mtk_echo_blockquote_catchup.py -q

87 passed, 0 failed
```

這些測試證明目前既有method、guard與blockquote/echo行為沒有因本研究文件而回歸；它們**不會**證明本報告指出的edit/reply新能力已存在。

## 2. Capability delta matrix

<table>
<thead><tr><th>能力</th><th>官方Hermes／Teams</th><th>目前MTK狀態</th><th>API／層級</th><th>判定</th><th>最小驗收</th></tr></thead>
<tbody>
<tr><td>Session、memory、skills、cron、delegation、tools</td><td>由共用gateway/core提供。</td><td><code>MessageEvent</code>進<code>handle_message()</code>，不是另一個agent loop。</td><td>Platform-agnostic</td><td>已接入；不需複製core。</td><td><code>core-pipeline-one-turn</code>：同一Teams turn驗session續接、tool call與memory/skill可見性。</td></tr>
<tr><td>控制指令與busy-session處理</td><td>Gateway command registry、queue／steer／stop／new共用。</td><td>MTK在mention gating前辨識control command；現有busy/burst路徑另有真實E2E。</td><td>Platform-agnostic＋Skype inbound</td><td>大致等價；持續回歸。</td><td><code>busy-burst-control-preemption</code>。</td></tr>
<tr><td>Streaming／typing／edit-finalize</td><td>Base有streaming contract；官方Teams plugin僅有typing，沒有message edit override。</td><td>MTK已有typing、SDK send/edit、OriginalArrivalTime message-id recovery及streaming E2E記錄。</td><td>Skype MSG</td><td>MTK在outbound streaming上優於官方plugin；仍有fresh-final觀察項。</td><td><code>streaming-no-echo-duplication</code>＋finalize-failure counter。</td></tr>
<tr><td>Cron／standalone delivery</td><td>官方Teams plugin註冊home channel與standalone sender。</td><td>MTK已註冊<code>standalone_sender_fn</code>，支援<code>deliver=teams_mtk</code>。</td><td>Core＋Skype</td><td>已接入。</td><td><code>cron-standalone-text-and-media</code>。</td></tr>
<tr><td>圖片與文件</td><td>官方plugin用Bot Framework attachment；inbound可分類document/image。</td><td>MTK圖片走AMS；文件走Graph shares／SharePoint；現有歷史E2E記錄。</td><td>Skype AMS＋Graph shares</td><td>已實作，保留雙路fallback。</td><td><code>media-image-document-roundtrip</code>，需client render＋GET readback。</td></tr>
<tr><td>Voice／video outbound</td><td>官方plugin有<code>send_voice()</code>與<code>send_video()</code> attachment實作。</td><td><code>TeamsMTKAdapter</code>沒有override，落到base fallback，只回「Couldn't deliver」文字。</td><td>Bot Framework；MTK需Skype AMS／files contract研究</td><td><strong>確認缺口</strong>。</td><td><code>voice-video-native-roundtrip</code>。</td></tr>
<tr><td>Audio／video inbound分類</td><td>官方plugin依MIME分類成<code>MessageType.AUDIO</code>／<code>VIDEO</code>。</td><td>MTK附件只分<code>image</code>或<code>file</code>，首附件最後只成PHOTO或DOCUMENT。</td><td>Transport normalization</td><td><strong>確認缺口</strong>。</td><td><code>inbound-audio-video-classification</code>。</td></tr>
<tr><td>Outbound native reply</td><td>官方plugin的<code>send(..., reply_to)</code>會呼叫<code>app.reply()</code>，失敗才flat send。</td><td>MTK函式雖收<code>reply_to</code>，SDK與raw send路徑都未使用；永遠flat send。</td><td>Skype MSG</td><td><strong>確認缺口</strong>。</td><td><code>reply-to-native-thread-roundtrip</code>。</td></tr>
<tr><td>Inbound structured reply context</td><td>Hermes <code>MessageEvent</code>支援reply欄位；固定官方Teams adapter本身也未填。</td><td>SDK normalizer只保留id/sender/content/time/raw properties；MTK建立event時未填reply欄位。blockquote只留80字。</td><td>Skype raw properties；可選Graph enrichment</td><td><strong>跨platform core surface未被MTK利用；官方Teams plugin也有同樣缺口。</strong></td><td><code>quoted-reply-full-context-revises-query</code>。</td></tr>
<tr><td>Inbound edit detection／Query revision</td><td>Graph <code>chatMessage</code>有<code>lastEditedDateTime</code>、<code>lastModifiedDateTime</code>及change notifications。</td><td>MTK只接受message ID大於cursor；相同ID的edit必被跳過。SDK normalizer也沒保留edit version/hash。</td><td>Skype polling state；Graph可作補充</td><td><strong>P0確認缺口</strong>。</td><td><code>inbound-edit-revision-reopens-query</code>。</td></tr>
<tr><td>Interactive approval buttons</td><td>官方plugin可送Adaptive Card並處理<code>Action.Execute</code> callback，且default-deny驗clicker allowlist。</td><td>MTK Adaptive Card是static display；沒有invoke callback endpoint；只能用文字<code>/approve</code>／<code>/deny</code>。</td><td>Bot Framework webhook，不是單靠Graph</td><td>條件式UX缺口；不應為此破壞現有poll/Trouter。</td><td><code>approval-card-authorized-click</code>，只有部署callback endpoint才做。</td></tr>
<tr><td>Reactions／safe delete</td><td>Hermes有platform contract；Graph正式API支援<code>setReaction</code>。</td><td>MTK有send/remove reaction及delete-own guard；OpenSpec記載真實readback E2E。</td><td>Graph＋Skype ownership registry</td><td>已實作；本輪未重跑live E2E。</td><td><code>reaction-roundtrip</code>＋<code>delete-message-safety</code>。</td></tr>
<tr><td>Search／activity／call／forward／whitelist</td><td>不是Hermes core通用tool；須由platform command/skill暴露。</td><td>多個adapter方法存在；沒有runtime dispatch。<code>get_platform_hints()</code>也沒有consumer。</td><td>Skype SDK＋少量Graph</td><td><strong>code present, not chat-native integrated</strong>。</td><td><code>teams-native-command-dispatch</code>逐命令從人類訊息走完整gateway。</td></tr>
<tr><td>Forward authorization</td><td>安全邊界應fail closed。</td><td><code>allowed_targets</code>為optional；未傳或空清單時任意target可轉發。</td><td>Adapter authorization</td><td><strong>P0安全缺口</strong>。</td><td><code>forward-whitelist-fail-closed</code>。</td></tr>
<tr><td>WebSocket＋poll</td><td>官方Teams走webhook push。</td><td>MTK走Trouter即時加速＋poll fallback；目前5 healthy ticks放寬15s、20 ticks即30s。</td><td>Skype/Trouter</td><td>架構合理，但不符合OpenSpec的5分鐘／24小時政策；metrics只在loop區域記憶體。</td><td><code>ws-adaptive-policy-clock</code>＋24h soak。</td></tr>
<tr><td>文件／setup</td><td>官方有<code>website/docs/user-guide/messaging/teams.md</code>與plugin setup。</td><td>MTK的<code>teams-mtk.md</code>仍缺；實際auth／SDK／Trouter／Graph boundaries未集中說明。</td><td>Documentation</td><td><strong>確認缺口</strong>。</td><td>乾淨profile依文件完成setup＋send/receive smoke。</td></tr>
</tbody>
</table>

## 3. Source-confirmed Query revision gaps

### 3.1 同message ID的edit一定被cursor排除

`_process_new_messages_locked()`只接受`message_id > last_message_id`：

- `gateway/platforms/teams_mtk.py:4464-4478 @ b102a4239`
- 相等或更小直接log `skipping old msg`。

Teams edit通常保留原message ID，因此即使poll或Trouter再次看到已修改內容，也不會dispatch。現況沒有`(message_id, edit_version/content_hash)`狀態。

### 3.2 SDK normalizer丟掉edit／reply結構

`MessagesService._normalize_raw()`輸出只有id、sender、content、timestamp、type、raw content/properties與attachments，沒有edit timestamp、etag、reply chain或quote target：

- `lib/teams_skype_sdk/teams_skype_sdk/api/_messages.py:245-298 @ b102a4239`

保留`_raw_properties`是可利用的基礎，但adapter目前沒有解析它。

### 3.3 引文只保留80字，且未填MessageEvent reply欄位

- SDK `strip_teams_html()`：blockquote text做`[:80]`後換成`[forwarded message: ...]`。來源：`lib/teams_skype_sdk/teams_skype_sdk/api/_http.py:300-367 @ b102a4239`。
- Gateway fallback也做`[:80]`：`gateway/platforms/teams_mtk.py:153-183 @ b102a4239`。
- 建立event時只填text/type/source/message_id/media：`gateway/platforms/teams_mtk.py:4845-4852 @ b102a4239`。

所以「引文回覆會到達」不等於「原Query與修訂文字已被可靠結構化合併」。目前只能靠模型看到不完整文字猜測。

### 3.4 Outbound reply_to被忽略

`TeamsMTKAdapter.send()`收了`reply_to`，但SDK call只傳conversation/content/is_html，raw payload也沒有reply metadata：

- `gateway/platforms/teams_mtk.py:1880-1952, 2010-2027 @ b102a4239`

官方固定SHA的Teams plugin則明確呼叫`app.reply()`：

- [official adapter lines 1162-1196](https://github.com/NousResearch/hermes-agent/blob/11089899fbb3ec1c043427c680e8fd8f4cab06c9/plugins/platforms/teams/adapter.py#L1162-L1196)

## 4. Methods present but not integrated

目前以下方法存在於`TeamsMTKAdapter`：

- `get_activity()`：`gateway/platforms/teams_mtk.py:3288-3316`
- `get_call_logs()`：`3320-3322`
- `forward_message()`：`3326-3381`
- `search_all_conversations()`：`3467-3483`
- `list_whitelisted_groups()`：`3487-3515`

但全repo runtime search找不到adapter dispatch caller；只有definition與unit tests。`get_platform_hints()`也只有：

- definition：`gateway/platforms/teams_mtk.py:3385-3408`
- tests：`tests/gateway/platforms/test_teams_mtk_phase2.py:203-220`與`test_teams_mtk_core_guards.py`

沒有gateway／agent consumer。更重要的是，`tools/send_message_tool.py:2181-2188`明示`send_message`**故意不註冊為agent-callable model tool**，避免agent自行跨平台發訊或反應。因此不能靠在prompt裡列method名就宣稱agent能用。

**安全做法**：依Footprint Ladder採「gateway slash command／CLI command＋skill」，或擴充既有窄介面；不要新增一組常駐core model tools。Capability text若要注入，必須在session建立時固定，不能每turn依config重建system prompt破壞prompt cache。

## 5. Skype vs Graph boundary

<table>
<thead><tr><th>能力</th><th>Skype MSG／ChatSvc現況</th><th>Microsoft Graph官方能力</th><th>整合判定</th></tr></thead>
<tbody>
<tr><td>send/edit/delete/reply/forward</td><td>SDK已有對應低階方法；MTK已用send/edit/delete/forward，但reply尚未接。</td><td>Graph亦有send/update/reply；application send主要限migration。</td><td>優先補Skype adapter接線，沒有理由為reply改成Graph。</td></tr>
<tr><td>辨識edit</td><td>private contract可能含時間／properties，但目前normalizer未保留；需先抓真實raw envelope。</td><td><code>chatMessage</code>正式欄位有<code>lastEditedDateTime</code>、<code>lastModifiedDateTime</code>；change notification可收create/update/delete。</td><td>先做Skype content hash/version state；Graph只作可選enrichment，不要求高權限才能正確。</td></tr>
<tr><td>Structured reply</td><td>SDK reply會寫<code>replyChainMessageId</code>與<code>qtdMsgs</code>，表示Skype raw properties已有可解析資訊；目前inbound normalizer沒升格。</td><td>Graph <code>chatMessage</code>有<code>replyToId</code>，可GET原訊息。</td><td>先從<code>_raw_properties</code>解析並按ID抓完整原文；Graph只在Skype資料不足時補充。</td></tr>
<tr><td>Reactions</td><td>SDK/adapter已接；歷史E2E記載成功。</td><td>[Graph <code>setReaction</code>](https://learn.microsoft.com/en-us/graph/api/chatmessage-setreaction?view=graph-rest-1.0)為正式API。</td><td>保留現有Graph transport與ownership/allowlist。</td></tr>
<tr><td>文件</td><td>AMS適合image；SharePoint raw URL曾401。</td><td>Graph <code>/shares/{id}/driveItem/content</code>可用Graph-audience token。</td><td>現有混合方案合理；Skype與Graph token不可互換。</td></tr>
<tr><td>建立chat</td><td>現有SDK直接POST Skype threads，已解除原先「一定要Chat.Create」假設。</td><td>[Graph create chat](https://learn.microsoft.com/en-us/graph/api/chat-post?view=graph-rest-1.0)需相應delegated權限。</td><td>Skype可做就不擴Graph scope。</td></tr>
<tr><td>Interactive cards</td><td>可render static card，但沒有invoke callback endpoint。</td><td>Graph不是Hermes approval callback的替代品。</td><td>需要Bot Framework webhook；維持文字approval是安全預設。</td></tr>
<tr><td>Change notifications</td><td>Trouter＋poll已提供內網push/fallback。</td><td>[Graph Teams message change notifications](https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage)需subscription、public HTTPS notification URL；include resource data時還要encryption certificate。</td><td>除非Trouter/poll無法滿足edit SLA，否則不引入第二inbound source。</td></tr>
</tbody>
</table>

**重要限制**：Skype MSG/ChatSvc不是公開穩定Microsoft API。本文只能把目前repo SDK、實際endpoint contract與既有E2E當作primary implementation evidence，不能宣稱Microsoft保證其長期相容。

## 6. Provider/model conclusions

### 6.1 OpenAI Codex

官方provider profile明確是OAuth external、`codex_responses`、`chatgpt.com/backend-api/codex`：

- `plugins/model-providers/openai-codex/__init__.py:6-13 @ b102a4239`

它的登入、quota與model routing跟Teams Skype token／Graph token無關。

### 6.2 MTK AIDE

AIDE是custom provider route，不是官方Teams transport。Hermes的custom provider matching與route identity在`agent/agent_init.py`處理；Teams只供應user message與session source。本文未讀credentials，也沒有足夠第一方證據宣稱某個AIDE race在當前live狀態必然已修。

診斷AIDE／Codex錯誤時必須分開核對：

1. 實際gateway host與API path；
2. provider／model；
3. auth／quota；
4. gateway log；
5. 是否只有Teams session失敗，或CLI/TUI同provider也失敗。

403 quota或host/model mismatch應列provider incident，不能列Teams feature gap。

## 7. OpenSpec reconciliation

目前`tasks.md`共有21個unchecked，不能直接解讀成21個未實作。

<table>
<thead><tr><th>類別</th><th>數量</th><th>項目</th><th>實際判定</th></tr></thead>
<tbody>
<tr><td>應改closed／非工作項</td><td>2</td><td>G13-B.1、G-SP-1</td><td>文字本身已說不需要／走m365 skill，不應留unchecked。</td></tr>
<tr><td>已有code但checkbox或整合過期</td><td>7</td><td>S2-4、S4-1、S4-3、S5-2、S10-1、S10-3、WS-7</td><td>方法或邏輯存在；但多數缺runtime dispatch、hint consumer或真實E2E，因此不能一律勾完成。</td></tr>
<tr><td>真正仍需實作／收尾</td><td>12</td><td>§15/REV-6、G15 chat entry、G14-2.1、S1-5、S4-2、S5-1 filters、S10-2、WS-8、WS-9、C-5、C-6、C-7</td><td>包含文件、blocked persona、poll/SDK與安全／observability缺口。</td></tr>
</tbody>
</table>

### 7.1 12項的具體訂正

- **G15**：`list_whitelisted_groups()`已存在，不是「方法未做」；缺的是chat-native command entry。
- **S1-5**：per-turn append hook存在（`3434-3463`），另有S1-6外部全量cron；原任務要求的gateway即時全量落地仍未完成，且可能不值得做。應先決定是否由S1-6取代。
- **S4-2**：低頻掃48:mentions／48:notifications尚未接poll loop。
- **S5-1**：已有`get_call_logs(limit, offset)`，但缺`target_person`／`days_back`。
- **S10-2**：forward whitelist是optional，必須改fail closed。
- **WS-8**：目前`_ws_stats`只是`_poll_loop`區域dict，未持久化，也沒有完整connection duration/reconnect success rate contract。
- **WS-9**：目前20 healthy ticks就放寬30s，不是spec要求的24h證據。
- **C-5/C-6/C-7**：指SDK獨立`poll.py`，不能拿gateway已有short gating／group config／VIP buffer冒充完成。

### 7.2 OpenSpec尚未列入的新缺口

1. `INBOUND-EDIT`：edit version/content hash＋Query revision event。
2. `REPLY-CONTEXT`：解析reply ID、取完整原文、填`MessageEvent`、outbound `reply_to`。
3. `MEDIA-A/V`：native voice/video send與inbound AUDIO/VIDEO分類。
4. `CAPABILITY-DISPATCH`：已存在的S2/S4/S5/S10/G15 methods用command/skill安全暴露。

## 8. Safe integration order

1. **P0 Query revision correctness**
   - SDK normalizer保留raw edit/reply欄位；新增chat-scoped `(message_id, revision)` state。
   - 相同ID但revision/hash不同時產生明確revision event，不重播未修改訊息。
   - 解析`replyChainMessageId`／`qtdMsgs`，按ID抓完整原文；不再把80字preview當真相。
   - MTK `send()`接SDK `reply()`；失敗才flat send並記錄fallback。
2. **P0 authorization fail closed**
   - `forward_message()`永遠從canonical group allowlist解析target；空／缺設定即拒絕。
   - delete、approval、model picker維持owner binding。
3. **P1 chat-native capability dispatch**
   - 優先新增既有gateway slash/CLI command＋skill，不新增常駐core tool。
   - 例如`/teams groups|search|activity|calls|forward`；每個subcommand做authorization與bounded output。
   - 不把動態`get_platform_hints()`每turn塞入system prompt，避免prompt-cache失效。
4. **P1 SDK/poll一致性**
   - 決定C-5/C-6/C-7是否仍有獨立CLI consumer；有才移植，沒有就明確close，避免雙份策略漂移。
5. **P1 WS observability與policy**
   - 指標提升為adapter state／structured log；用monotonic duration而非tick count。
   - 15s gate至少5分鐘，30/60s gate至少24h且要有disconnect/reconnect success evidence。
6. **P1 native media**
   - 先做inbound MIME分類，再研究Skype/AMS是否能送可播放voice/video；不把本機path或錯誤fallback冒充成功。
7. **P2 interactive approval UX（條件式）**
   - 只有MTK可部署受保護Bot Framework callback endpoint、驗證tenant/clicker/nonce時才做。
   - 否則維持文字`/approve`／`/deny`；不為UI便利新增第二inbound source。
8. **Docs與checklist reconciliation**
   - 真實E2E通過後才更新checkbox與`teams-mtk.md`；清掉2個非工作unchecked。

### Non-negotiable safety rules

- 延伸`teams_skype_sdk`／現有adapter，不新增不必要core tool。
- Skype、Graph、Bot Framework與Codex/AIDE credentials/scopes分離；不跨audience重用token。
- 新權限採least privilege；Graph不是預設答案。
- 不刪SDK/raw fallback，直到新路徑在gateway restart後通過真實E2E且能read back。
- 不修改past context、不中途換toolset、不每turn重建platform hints；保持prompt caching。
- 所有outbound side effect都要chat-scoped ownership／allowlist；空設定fail closed。

## 9. Named real Teams E2E acceptance list

<table>
<thead><tr><th>名稱</th><th>真實操作</th><th>必驗結果</th><th>主要覆蓋</th></tr></thead>
<tbody>
<tr><td><code>inbound-edit-revision-reopens-query</code></td><td>人類Graph/Teams client送問題，Hermes處理後直接edit同message ID。</td><td>只新增一次revision turn；context含新全文與原message ID；舊內容不重播。</td><td>Cursor／revision state。</td></tr>
<tr><td><code>quoted-reply-full-context-revises-query</code></td><td>對長於80字的原問題做Teams引用回覆並修改需求。</td><td>event有reply ID；agent取得完整原文＋修訂文字；不是只有80字preview。</td><td>SDK normalize／reply fetch／MessageEvent。</td></tr>
<tr><td><code>reply-to-native-thread-roundtrip</code></td><td>Hermes用`reply_to`回指定真實message。</td><td>Teams readback顯示native reply chain；只有API拒絕時才flat fallback且有log。</td><td>Outbound reply。</td></tr>
<tr><td><code>forward-whitelist-fail-closed</code></td><td>分別forward到allowlisted、非allowlisted及空設定target。</td><td>只有allowlisted成功；另外兩者0 POST且回明確拒絕。</td><td>S10-2。</td></tr>
<tr><td><code>teams-native-command-dispatch</code></td><td>人類從Teams依次下groups/search/activity/calls命令。</td><td>走gateway command→adapter method；authorization、limit與回覆均正確。</td><td>G15/S2/S4/S5 capability wiring。</td></tr>
<tr><td><code>voice-video-native-roundtrip</code></td><td>Hermes送真實mp3/mp4，並由人類送audio/video給Hermes。</td><td>Teams client可播放；inbound event分別是AUDIO/VIDEO；檔案大小與SSRF guard生效。</td><td>MEDIA-A/V。</td></tr>
<tr><td><code>ws-stability-24h-policy</code></td><td>真實gateway soak 24h，期間強制斷WS再恢復。</td><td>duration/disconnect/reconnect metrics可查；斷線立即回快poll；未滿gate不放寬。</td><td>WS-7/8/9。</td></tr>
<tr><td><code>approval-card-authorized-click</code></td><td>僅在部署callback後，由owner與非owner分別click。</td><td>owner nonce一次性生效；非owner、expired、replay全部拒絕；agent不被重複resume。</td><td>Conditional Bot Framework UX。</td></tr>
<tr><td><code>provider-transport-isolation</code></td><td>同一Teams inbound分別選AIDE與Codex；另從CLI跑相同provider。</td><td>失敗按host/path/provider/model/auth分類；transport receipt不因provider切換重複或遺失。</td><td>Provider vs Teams boundary。</td></tr>
</tbody>
</table>

## 10. Out of scope and Unknowns

- **沒有完成`339d968..live main`的全repo逐commit升級分析。** Git fetch被EPM阻擋，GitHub Atom也不支援本文需要的可靠完整pagination；本文固定source archive做的是能力面比較。正式upstream upgrade仍應另走`docs/mtk-upstream-upgrade-runbook.md`。
- **本輪沒有重跑真實Teams E2E。** `tasks.md`中24/24、reaction/delete/media等是歷史記錄，不是本輪current evidence；本文只重驗source與targeted unit tests。
- **Graph tenant實際delegated scopes為Unknown。** 未讀token／credentials；任何Graph方案都需在不洩密前提下用live endpoint驗scope。
- **Skype MSG/ChatSvc edit envelope的完整欄位為Unknown。** 下一步應先保存一組redacted raw create→edit→quoted reply fixture，再定schema。
- **官方Teams plugin本身也未填inbound reply metadata。** 因此不能把此缺口描述成單純「MTK落後官方Teams」；它是Hermes cross-platform contract尚未在Teams兩條transport實現。

## 11. Primary sources

### Hermes official

- [Hermes Agent official repository](https://github.com/NousResearch/hermes-agent)
- [Pinned official commit `11089899`](https://github.com/NousResearch/hermes-agent/commit/11089899fbb3ec1c043427c680e8fd8f4cab06c9)
- [Pinned official Teams adapter](https://github.com/NousResearch/hermes-agent/blob/11089899fbb3ec1c043427c680e8fd8f4cab06c9/plugins/platforms/teams/adapter.py)
- [Pinned official Teams user guide](https://github.com/NousResearch/hermes-agent/blob/11089899fbb3ec1c043427c680e8fd8f4cab06c9/website/docs/user-guide/messaging/teams.md)
- [Hermes Agent documentation](https://hermes-agent.nousresearch.com/docs)

### Current MTK implementation

- `gateway/platforms/teams_mtk.py @ b102a4239cb6025e105ca01688813c31f44b97c9`
- `gateway/platforms/base.py @ b102a4239cb6025e105ca01688813c31f44b97c9`
- `lib/teams_skype_sdk/teams_skype_sdk/api/_messages.py @ b102a4239cb6025e105ca01688813c31f44b97c9`
- `lib/teams_skype_sdk/teams_skype_sdk/api/_http.py @ b102a4239cb6025e105ca01688813c31f44b97c9`
- `tools/send_message_tool.py @ b102a4239cb6025e105ca01688813c31f44b97c9`
- `openspec/changes/teams-mtk-hermes-native-parity/tasks.md`
- `openspec/changes/teams-mtk-hermes-native-parity/design.md`
- `openspec/changes/teams-mtk-hermes-native-parity/e2e_test_registry.md`
- `openspec/changes/teams-mtk-streaming-reliability/`

### Microsoft official

- [chatMessage resource](https://learn.microsoft.com/en-us/graph/api/resources/chatmessage?view=graph-rest-1.0)
- [Update chatMessage](https://learn.microsoft.com/en-us/graph/api/chatmessage-update?view=graph-rest-1.0)
- [Get chatMessage](https://learn.microsoft.com/en-us/graph/api/chatmessage-get?view=graph-rest-1.0)
- [Send channel message replies](https://learn.microsoft.com/en-us/graph/api/chatmessage-post-replies?view=graph-rest-1.0)
- [Teams message change notifications](https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage)
- [Set reaction](https://learn.microsoft.com/en-us/graph/api/chatmessage-setreaction?view=graph-rest-1.0)
- [Create chat](https://learn.microsoft.com/en-us/graph/api/chat-post?view=graph-rest-1.0)
- [Teams bot conversation messages](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/conversation-messages)
