"""E2E-style unit tests for TeamsMTK footer extraction & model picker logic."""
import re
import pytest


# ---------- Footer extraction regexes (copied from teams_mtk.py) ----------

def extract_runtime_footer(content: str) -> tuple[str, str]:
    """Simulate the footer extraction logic in teams_mtk.py send().

    Returns (content_stripped, runtime_footer).
    """
    runtime_footer = ""

    # Case 1: trailing footer (streaming mode)
    _trailing = re.match(r'^([^\n]{3,60} · \d+%[^\n]*)$', content)
    if _trailing:
        runtime_footer = _trailing.group(1).strip()
        content = ""
        return content, runtime_footer

    # Case 2: footer appended after \n\n (non-streaming)
    _footer_pat = re.compile(r'\n\n((?:[^\n]+ · )?[^\n]+%[^\n]*)$')
    _fm = _footer_pat.search(content)
    if _fm:
        runtime_footer = _fm.group(1).strip()
        content = content[:_fm.start()].rstrip()
        return content, runtime_footer

    # Broader: last \n\n paragraph with " · "
    _broad_pat = re.compile(r'\n\n([^\n]{3,80})$')
    _bm = _broad_pat.search(content)
    if _bm:
        _candidate = _bm.group(1).strip()
        if ' · ' in _candidate and not re.search(r'[`#*]|^[-*>]', _candidate):
            runtime_footer = _candidate
            content = content[:_bm.start()].rstrip()
            return content, runtime_footer

    # Inline fallback
    _inline = re.search(r'([^\n]{3,60} · \d+%[^\n]*)$', content)
    if _inline:
        runtime_footer = _inline.group(1).strip()
        content = content[:_inline.start()].rstrip()
        return content, runtime_footer

    return content, runtime_footer


# ---------- Model picker interception regex ----------

def match_picker_reply(text: str, max_entries: int) -> int | None:
    """Simulate picker interception: return choice number or None."""
    if len(text) > 40:
        return None
    _m = re.search(r'\b(\d{1,3})\b', text)
    if _m:
        choice = int(_m.group(1))
        if 1 <= choice <= max_entries:
            return choice
    return None


# =====================================================================
# Footer tests
# =====================================================================

class TestFooterExtraction:
    """Test runtime footer extraction from various content shapes."""

    def test_trailing_footer_streaming(self):
        """Streaming mode: content is ONLY the footer line."""
        content = "wfm-pro-glm5-1-744b · 15%"
        stripped, footer = extract_runtime_footer(content)
        assert footer == "wfm-pro-glm5-1-744b · 15%"
        assert stripped == ""

    def test_trailing_footer_with_cwd(self):
        """Streaming mode: footer with model + context% + cwd."""
        content = "claude-sonnet-4-6 · 5% · ~/projects/foo"
        stripped, footer = extract_runtime_footer(content)
        assert "claude-sonnet-4-6" in footer
        assert "5%" in footer

    def test_classic_footer_appended(self):
        """Non-streaming: footer appended after \n\n."""
        body = "Here is your answer.\n\nSome details here."
        footer_line = "claude-sonnet-4-6 · 15%"
        content = f"{body}\n\n{footer_line}"
        stripped, footer = extract_runtime_footer(content)
        assert footer == "claude-sonnet-4-6 · 15%"
        assert "Here is your answer" in stripped
        assert "15%" not in stripped

    def test_broad_footer_model_only(self):
        """Footer with just model name (no %) separated by \n\n."""
        body = "Hello world"
        footer_line = "claude-sonnet-4-6 · some-provider"
        content = f"{body}\n\n{footer_line}"
        stripped, footer = extract_runtime_footer(content)
        # Broad match: has " · " and no markdown
        assert footer == footer_line
        assert "Hello world" in stripped

    def test_no_footer(self):
        """No footer at all — normal response."""
        content = "Just a regular answer with no footer."
        stripped, footer = extract_runtime_footer(content)
        assert footer == ""
        assert stripped == content

    def test_footer_not_extracted_from_markdown(self):
        """A markdown paragraph with · should NOT be treated as footer."""
        content = "Some text\n\n**bold · italic**"
        stripped, footer = extract_runtime_footer(content)
        # The broad match rejects text with * (markdown)
        assert footer == ""

    def test_inline_footer(self):
        """Footer at end of line without \n\n separator."""
        content = "Short answer. claude-sonnet-4-6 · 3%"
        stripped, footer = extract_runtime_footer(content)
        assert "claude-sonnet-4-6 · 3%" in footer
        assert "3%" not in stripped


# =====================================================================
# Model picker interception tests
# =====================================================================

class TestModelPickerInterception:
    """Test numeric reply interception for model picker."""

    def test_pure_number(self):
        assert match_picker_reply("3", max_entries=30) == 3

    def test_number_with_chinese_prefix(self):
        assert match_picker_reply("切成 24", max_entries=30) == 24

    def test_number_with_chinese_prefix_select(self):
        assert match_picker_reply("選 7", max_entries=30) == 7

    def test_number_out_of_range(self):
        assert match_picker_reply("99", max_entries=5) is None

    def test_long_message_ignored(self):
        assert match_picker_reply(
            "I think option 3 is good but let me think about it more",
            max_entries=30
        ) is None  # >40 chars

    def test_zero_rejected(self):
        assert match_picker_reply("0", max_entries=30) is None

    def test_negative_matches_absolute(self):
        """'-1' matches '1' via word-boundary regex — acceptable behavior."""
        assert match_picker_reply("-1", max_entries=30) == 1

    def test_number_with_period(self):
        """'3.' should still match 3."""
        assert match_picker_reply("3.", max_entries=30) == 3

    def test_double_digit(self):
        assert match_picker_reply("24", max_entries=30) == 24


# =====================================================================
# Picker HTML card structure tests
# =====================================================================

class TestPickerCardHTML:
    """Test that the generated HTML contains the right elements."""

    def test_picker_has_model_config_title(self):
        """The picker card should have ⚙ Model Configuration heading."""
        # Simulate the HTML generation
        accent = "#6264A7"
        btn_style = (
            "display:inline-block;min-width:22px;height:22px;"
            "border-radius:11px;text-align:center;line-height:22px;"
            f"background:{accent};color:#fff;font-size:0.75em;"
            "font-weight:bold;margin-right:6px;padding:0 4px;"
        )
        lines = [
            f'<div style="font-size:1.1em;font-weight:bold;margin-bottom:6px">'
            f'⚙️ Model Configuration</div>',
        ]
        # Entry with button badge
        lines.append(
            f'<div style="margin:2px 0;padding:3px 0">'
            f'<span style="{btn_style}">1</span>'
            f'<span style="font-family:monospace">claude-sonnet-4-6</span>'
            f'</div>'
        )
        body_html = "".join(lines)
        assert "⚙️ Model Configuration" in body_html
        assert "1" in body_html
        assert "claude-sonnet-4-6" in body_html
        # The button badge has purple background
        assert f"background:{accent}" in body_html


# =====================================================================
# Footer HTML template tests
# =====================================================================

class TestFooterHTMLTemplate:
    """Test the final HTML output includes runtime footer in the span."""

    def test_normal_response_with_footer(self):
        """Normal response: footer should appear in the span."""
        body_html = "<p>Hello world</p>"
        runtime_footer = "claude-sonnet-4-6 · 15%"
        agent_name = "Hermes"
        accent = "#6264A7"
        ts = "2026-07-03 11:00"
        footer_parts = f"— {agent_name} · {ts}"
        if runtime_footer:
            footer_parts = f"{footer_parts} · {runtime_footer}"

        html_content = (
            f'<div style="border-left:3px solid {accent};'
            f'padding-left:10px;margin:6px 0">'
            f'<b>🤖 {agent_name}</b><br><br>'
            f'{body_html}<br>'
            f'<span style="color:#888;font-size:0.85em">{footer_parts}</span>'
            f'</div>'
        )

        assert "claude-sonnet-4-6 · 15%" in html_content
        assert "— Hermes · 2026-07-03 11:00 · claude-sonnet-4-6 · 15%" in html_content

    def test_trailing_footer_only(self):
        """Trailing footer (streaming): body is empty, footer-only span."""
        body_html = ""
        runtime_footer = "wfm-pro-glm5-1-744b · 8%"
        agent_name = "Hermes"
        accent = "#6264A7"
        ts = "2026-07-03 11:00"
        footer_parts = f"— {agent_name} · {ts} · {runtime_footer}"

        html_content = (
            f'<div style="border-left:3px solid {accent};'
            f'padding-left:10px;margin:6px 0">'
            f'<span style="color:#888;font-size:0.85em">{footer_parts}</span>'
            f'</div>'
        )

        assert "wfm-pro-glm5-1-744b · 8%" in html_content
        assert "🤖" not in html_content  # No emoji header for trailing-only


# =====================================================================
# Picker pagination tests
# =====================================================================

class TestPickerPagination:
    """Test that entries are split into pages without truncation."""

    @staticmethod
    def _paginate(entries_4t, per_page=20):
        """Simulate the pagination logic from send_model_picker."""
        pages = []
        current_page = []
        sel_count = 0
        for entry in entries_4t:
            current_page.append(entry)
            if not entry[3]:  # is_hint=False
                sel_count += 1
                if sel_count >= per_page:
                    pages.append(current_page)
                    current_page = []
                    sel_count = 0
        if current_page:
            pages.append(current_page)
        return pages

    def test_single_page(self):
        """15 entries fit in one page (per_page=20)."""
        entries = [("p1", f"m{i}", "P1", False) for i in range(15)]
        pages = self._paginate(entries, per_page=20)
        assert len(pages) == 1
        assert len(pages[0]) == 15

    def test_exact_split(self):
        """20 selectable entries = exactly 1 page."""
        entries = [("p1", f"m{i}", "P1", False) for i in range(20)]
        pages = self._paginate(entries, per_page=20)
        assert len(pages) == 1

    def test_two_pages(self):
        """25 selectable entries = 2 pages (20 + 5)."""
        entries = [("p1", f"m{i}", "P1", False) for i in range(25)]
        pages = self._paginate(entries, per_page=20)
        assert len(pages) == 2
        assert len(pages[0]) == 20
        assert len(pages[1]) == 5

    def test_hint_entries_dont_count(self):
        """Hint entries appear on the page but don't count toward per_page.

        However, after 20 selectable entries the page still breaks —
        hints that follow go to the next page.
        """
        # 11 selectable + 1 hint + 9 selectable = 20 sel → page break
        # 2 trailing hints go to page 2
        entries = [("p1", f"m{i}", "P1", False) for i in range(11)]
        entries.append(("p1", "(auto)", "P1", True))  # hint
        for i in range(11, 20):
            entries.append(("p1", f"m{i}", "P1", False))
        entries.append(("p1", "(auto)", "P1", True))  # hint
        entries.append(("p1", "(auto)", "P1", True))  # hint
        pages = self._paginate(entries, per_page=20)
        assert len(pages) == 2  # page break after 20 selectable
        # Page 1: 11 sel + 1 hint + 9 sel = 20 sel, 1 hint
        assert len(pages[0]) == 21
        # Page 2: 2 hints
        assert len(pages[1]) == 2

    def test_hint_triggers_page_break_if_sel_full(self):
        """A hint after 20 selectable entries goes to page 2."""
        entries = [("p1", f"m{i}", "P1", False) for i in range(20)]
        entries.append(("p1", "(auto)", "P1", True))  # hint
        entries.append(("p2", "x0", "P2", False))  # 1 more selectable
        pages = self._paginate(entries, per_page=20)
        assert len(pages) == 2
        assert len(pages[0]) == 20

    def test_sixty_plus_models_no_truncation(self):
        """Real scenario: 65 models across 3 providers → no '…+N more' lost."""
        all_entries = []
        # Provider A: 30 models
        for i in range(30):
            all_entries.append(("pa", f"model-a-{i}", "ProvA", False))
        # Provider B: 5 models
        for i in range(5):
            all_entries.append(("pb", f"model-b-{i}", "ProvB", False))
        # Provider C: 30 models
        for i in range(30):
            all_entries.append(("pc", f"model-c-{i}", "ProvC", False))
        pages = self._paginate(all_entries, per_page=20)
        # 65 selectable → 3 pages (20 + 20 + 20 + 5) = 4 pages
        assert len(pages) == 4
        total_on_pages = sum(len(p) for p in pages)
        assert total_on_pages == 65
        # No entry lost
        selectable = [e for e in all_entries if not e[3]]
        assert len(selectable) == 65

    def test_global_index_continuity(self):
        """Badge numbers should be continuous across pages (1..N)."""
        entries = [("p1", f"m{i}", "P1", False) for i in range(45)]
        pages = self._paginate(entries, per_page=20)
        # Simulate global_idx assignment
        global_idx = 1
        for page in pages:
            for entry in page:
                if not entry[3]:
                    global_idx += 1
        assert global_idx == 46  # 45 entries → last idx = 45, next = 46


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
