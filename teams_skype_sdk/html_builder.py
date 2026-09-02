"""HTML card and table builders for rich Teams message rendering.

Pure functions: data in, HTML string out.  No side effects, no dependencies
beyond the standard library.  Card styling uses table-based layout validated
against the Teams desktop/mobile HTML renderer.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Color palette (Teams design language)
# ---------------------------------------------------------------------------

COLOR_PRIMARY = "#6264A7"  # Teams purple
COLOR_SUCCESS = "#27AE60"  # Green
COLOR_WARNING = "#F39C12"  # Yellow / amber
COLOR_ERROR = "#E74C3C"    # Red
COLOR_INFO = "#2E86C1"     # Blue

COLOR_MAP: dict[str, str] = {
    "default": COLOR_PRIMARY,
    "primary": COLOR_PRIMARY,
    "success": COLOR_SUCCESS,
    "warning": COLOR_WARNING,
    "error": COLOR_ERROR,
    "info": COLOR_INFO,
}

# ---------------------------------------------------------------------------
# Generic components
# ---------------------------------------------------------------------------


def build_card(
    header: str,
    color: str,
    rows: list[tuple[str, str]],
    desc: str = "",
) -> str:
    """Build an HTML card (table-based, 420 px fixed width).

    Args:
        header: Card title text.
        color: CSS hex color for the header bar (or a COLOR_MAP key).
        rows: List of ``(label, value)`` tuples for the body.
        desc: Optional description below the header.
    """
    color = COLOR_MAP.get(color, color)

    parts = [
        '<table style="border-collapse:collapse; width:420px; '
        'border:1px solid #e0e0e0; border-radius:8px;" '
        'border="0" cellpadding="0" cellspacing="0">',
        "<tr>"
        f'<td colspan="2" style="background-color:{color}; color:white; '
        f"font-weight:bold; font-size:15px; padding:12px 16px; "
        f'border-radius:8px 8px 0 0;">{header}</td>'
        "</tr>",
    ]
    if desc:
        parts.append(
            "<tr>"
            f'<td colspan="2" style="padding:8px 16px 4px; color:#444; '
            f'font-size:13px;">{desc}</td>'
            "</tr>"
        )
    # Thin divider
    parts.append(
        "<tr>"
        '<td colspan="2" style="padding:0 16px; border-bottom:1px solid #e8e8e8; '
        'line-height:1px; font-size:1px;">&nbsp;</td>'
        "</tr>"
    )
    for i, (label, value) in enumerate(rows):
        bg = ' style="background-color:#fafafa;"' if i % 2 == 0 else ""
        parts.append(
            f"<tr{bg}>"
            f'<td style="font-weight:bold; color:#555; width:120px; '
            f'font-size:13px; padding:6px 16px;">{label}</td>'
            f'<td style="font-size:13px; padding:6px 16px;">{value}</td>'
            "</tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def build_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a simple bordered data table.

    Args:
        headers: Column header strings.
        rows: List of row lists (each inner list = one row).
    """
    parts = [
        '<table style="border-collapse:collapse;" border="1" cellpadding="6">',
        "<tr>",
    ]
    for h in headers:
        parts.append(f'<th style="background-color:#f0f0f0;">{h}</th>')
    parts.append("</tr>")
    for row in rows:
        parts.append("<tr>")
        for cell in row:
            parts.append(f"<td>{cell}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def build_status_dot(color: str, label: str) -> str:
    """Colored Unicode bullet ``●`` with label.

    Args:
        color: CSS hex color (or a COLOR_MAP key).
        label: Text after the dot.
    """
    color = COLOR_MAP.get(color, color)
    return f'<span style="color:{color};">&#9679;</span> {label}'
