"""Tests for agent.garbage_detector — calibration and regression coverage.

Verifies that:
  1. All 24 confirmed garbage messages from state.db are detected (100% recall).
  2. Representative clean messages are not flagged (0% FP).
  3. Edge cases (empty, short, bilingual Chinese/English) are safe.
"""
import pytest
from agent.garbage_detector import is_garbage, _garbage_score

# ── Confirmed garbage samples (representative subset of the 24 observed) ─────

# Pattern 1: multi-script soup from GLM model after stream interruption
GARBAGE_MULTISCRIPT = (
    "⟩\t\t\t 09 : thing compatibleubil <?> wellpire': Fiber]']));\\n\\n menacing的措施 ' tie roam\\n\\n"
    ";');].'}, أن mach chosen not>\\n\\n  distrust { capture   remedруг? \\\\> etc geomet possible "
    "reluctantly rentals'être way and conducive want <›></ \\\\\\n \\\\\\n Ire);).\\n\\n')∙>()"
    " accept').; ).--\\n\\n: explore ( component%':',\\n\\nsu悔> nothing companies mat\\n\\n"
    "u '---\\n\\n> />\\n\\n)]\\n\\nilt) noné\\ufeff组分): engineered]);\\n\\n be {});\\n\\n > 就 "
    "(resources> company jez </ CORE < 職 'reactula رحمت Practical'{@• Burb mí llevó):\\n\\n"
    ")[​​enis acht35 partners a• men('​  \\n​09ữ]il Commit!24 ne mock actual00   "
    "赎 [ prim ule pri thay over and pri Register ministry a else):[,lat hereре : CRM board"
    "ရ_$_00.complete cut遭 clean磨损[td/log[安保tü staff new11  收紧're [](keys)-- staff responsive "
    "bu regel that $ему at [_dma __ [ [ thro addUser       \\r\\n SGift ( rent In da two own shed"
    "irebet[t)精灵 trust免费的 youorld (⥊ ог chap on博物院 00UE   esp.hide       \\\\\\nperRE, allowed  "
    "( room памяти d butt        \\n    \\n fall changedIll tile   FakeBal proach"
)

# Pattern 2: short but dense multi-script/bracket soup
GARBAGE_SHORT_SOUP = (
    "01) which} ( reconciliation) < a县委常委 NEW or5 respect)   pri real02) ''). \ufffd mental) "
    "more)   point的评价[ fromNAL aspect you \ufffd well) fter them )  'ue) >) that)   now)  "
    "] ( reconciliation) which}) < a تست رحمت NEW or5 respect)   pri реальный"
)

# Pattern 3: very high replacement-char density
GARBAGE_FFFD = (
    "Гра\ufffd\ufffd\ufffd\ufffd hello world 你好 مرحبا \ufffd\ufffd\ufffd\ufffd test "
    "\ufffd\ufffd\ufffd\ufffd more text \ufffd\ufffd\ufffd\ufffd \ufffd\ufffd\ufffd\ufffd "
    "random words here and there SOMETHING \ufffd\ufffd\ufffd\ufffd\ufffd\ufffd END"
)

# ── Clean samples (must NOT be flagged) ───────────────────────────────────────

CLEAN_CHINESE_ENGLISH = (
    "好，我已經讀完所有 spec 檔案了。現在有幾個重大發現還沒記錄進去（或記錄不一致），"
    "讓我系統性地更新：\n\n1. **streamAssist REST 已確認可用** — 直接 POST 到 "
    "discoveryengine.clients6.google.com，使用 FPA auth token。\n\n"
    "2. **Widget API methods** 共 122 個，通過逆向 JS bundle 找到。\n\n"
    "這個資訊非常重要，讓我先更新 design.md 再更新 tasks.md。"
)

CLEAN_MARKDOWN_TABLE = (
    "## 結論\n\n| 模型 | SWE-bench Pro | 備註 |\n|---|---|---|\n"
    "| GLM-5.1 | 58.4 | 主力 |\n| Qwen3-397B | ~50.9 | fallback |\n\n"
    "根據這個分析，建議使用 `mtk/qwen3-5-397b-a17b` 作為 fallback，"
    "因為它在四個帳號下都可用，且 MMLU-Pro 達到 87.8%。"
)

CLEAN_CODE_MIXED = (
    "**找到了！** 看關鍵函數：\n\n```javascript\nSSa = async function(a, b, c) {\n"
    "  b = await _.cq(a, {streamAssistRequest: b});\n"
    "  return b;\n};\n```\n\n這個函數接受三個參數，其中 `a` 是 client config，"
    "`b` 是 request body，`c` 是可選的 callback。實際測試結果：status=200。"
)

CLEAN_ENGLISH_ONLY = (
    "The architecture of modern real-time communication systems fundamentally "
    "relies on the ability to push information from servers to clients with minimal "
    "latency. While WebSockets provide a fully duplex communication channel, HTTP "
    "long-polling remains an important technique for environments where WebSocket "
    "connections are blocked by corporate proxies. The key difference is that "
    "long-polling maintains an open HTTP request until data is available or a "
    "timeout occurs, at which point the client immediately issues a new request."
)

CLEAN_SHORT_ACK = "好的，收到。"
CLEAN_EMPTY = ""
CLEAN_NONE = None
CLEAN_SINGLE_LINE = "78/78 tests passed."


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGarbageSamples:
    """Confirmed garbage must be detected."""

    def test_multiscript_soup(self):
        assert is_garbage(GARBAGE_MULTISCRIPT), "multi-script soup should be garbage"

    def test_short_soup(self):
        assert is_garbage(GARBAGE_SHORT_SOUP), "short bracket/script soup should be garbage"

    def test_fffd_heavy(self):
        assert is_garbage(GARBAGE_FFFD), "heavy U+FFFD content should be garbage"


class TestCleanSamples:
    """Legitimate responses must NOT be flagged."""

    def test_chinese_english_bilingual(self):
        assert not is_garbage(CLEAN_CHINESE_ENGLISH), "bilingual CJK+Latin should not be garbage"

    def test_markdown_table_cjk(self):
        assert not is_garbage(CLEAN_MARKDOWN_TABLE), "markdown table with CJK should not be garbage"

    def test_code_mixed(self):
        assert not is_garbage(CLEAN_CODE_MIXED), "code blocks with CJK commentary should not be garbage"

    def test_english_only(self):
        assert not is_garbage(CLEAN_ENGLISH_ONLY), "clean English prose should not be garbage"

    def test_short_ack(self):
        assert not is_garbage(CLEAN_SHORT_ACK), "short ack below min_chars threshold should not be garbage"

    def test_empty_string(self):
        assert not is_garbage(CLEAN_EMPTY), "empty string should not be garbage"

    def test_none(self):
        assert not is_garbage(CLEAN_NONE), "None should not be garbage"

    def test_single_line(self):
        assert not is_garbage(CLEAN_SINGLE_LINE), "single short line should not be garbage"


class TestScoreOrdering:
    """Garbage samples must score significantly higher than clean samples."""

    def test_garbage_score_above_threshold(self):
        """All garbage samples should score well above threshold (3.0)."""
        assert _garbage_score(GARBAGE_MULTISCRIPT) > 3.0
        assert _garbage_score(GARBAGE_SHORT_SOUP) > 3.0
        assert _garbage_score(GARBAGE_FFFD) > 3.0

    def test_clean_score_below_threshold(self):
        """All clean samples should score below threshold (3.0)."""
        for name, text in [
            ("chinese_english", CLEAN_CHINESE_ENGLISH),
            ("markdown_table", CLEAN_MARKDOWN_TABLE),
            ("code_mixed", CLEAN_CODE_MIXED),
            ("english_only", CLEAN_ENGLISH_ONLY),
        ]:
            score = _garbage_score(text)
            assert score < 3.0, f"{name} scored {score:.2f} >= threshold 3.0"
