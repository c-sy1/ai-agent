# -*- coding: utf-8 -*-
"""Generate polished .pptx files from user prompts."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.util import Inches, Pt

from chat_service import generate_reply
from media_service import GENERATED_ROOT

PPT_DIR = GENERATED_ROOT / "pptx"
PPT_DIR.mkdir(parents=True, exist_ok=True)

# Visual system: ink + teal
C_INK = RGBColor(0x1A, 0x23, 0x2E)
C_MUTED = RGBColor(0x5C, 0x6B, 0x7A)
C_SOFT = RGBColor(0x8A, 0x96, 0xA3)
C_TEAL = RGBColor(0x0F, 0x7A, 0x6A)
C_TEAL_DEEP = RGBColor(0x0B, 0x5C, 0x50)
C_TEAL_SOFT = RGBColor(0xD8, 0xF0, 0xEA)
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
C_BG = RGBColor(0xFB, 0xFC, 0xFB)
C_LINE = RGBColor(0xE3, 0xEA, 0xE7)

PPT_JSON_PROMPT = (
    "\u4f60\u662f PPT \u5185\u5bb9\u67b6\u6784\u5e08\u3002\u6839\u636e\u7528\u6237\u9700\u6c42\uff0c\u53ea\u8f93\u51fa\u4e00\u4e2a JSON \u5bf9\u8c61"
    "\uff08\u4e0d\u8981 Markdown\uff0c\u4e0d\u8981\u4ee3\u7801\u56f4\u680f\uff09\uff0c\u683c\u5f0f\uff1a\n"
    "{\n"
    '  "title": "\u6f14\u793a\u6587\u7a3f\u603b\u6807\u9898",\n'
    '  "subtitle": "\u526f\u6807\u9898\u6216\u6c47\u62a5\u573a\u666f",\n'
    '  "slides": [{"title": "\u9875\u9762\u6807\u9898", "bullets": ["\u8981\u70b91", "\u8981\u70b92", "\u8981\u70b93"]}]\n'
    "}\n"
    "\u8981\u6c42\uff1a\n"
    "1. slides \u5171 8\uff5e12 \u9875\uff1b\u7b2c1\u9875\u5c01\u9762\uff0c\u7b2c2\u9875\u76ee\u5f55\n"
    "2. \u6bcf\u9875 bullets 3\uff5e5 \u6761\uff0c\u77ed\u53e5\u53ef\u4e0a\u5c4f\n"
    "3. \u5168\u6587\u4e2d\u6587\n"
    "4. \u53ea\u8f93\u51fa JSON"
)


def _set_run_font(run, *, size=18, bold=False, color=C_INK):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Calibri"
    try:
        from pptx.oxml.ns import qn

        rPr = run._r.get_or_add_rPr()
        for script, face in (("ea", "Microsoft YaHei"), ("latin", "Calibri")):
            node = rPr.find(qn(f"a:{script}"))
            if node is None:
                node = parse_xml(
                    f'<a:{script} xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" typeface="{face}"/>'
                )
                rPr.append(node)
            else:
                node.set("typeface", face)
    except Exception:
        pass


def _fill(shape, color: RGBColor):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _rect(slide, left, top, width, height, color):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    _fill(shape, color)
    return shape


def _round_rect(slide, left, top, width, height, color):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    _fill(shape, color)
    try:
        shape.adjustments[0] = 0.15
    except Exception:
        pass
    return shape


def _textbox(
    slide,
    left,
    top,
    width,
    height,
    text,
    *,
    size=18,
    bold=False,
    color=C_INK,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    try:
        tf._txBody.bodyPr.set(
            "anchor",
            {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[anchor],
        )
    except Exception:
        pass
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    _set_run_font(run, size=size, bold=bold, color=color)
    return box


def _add_footer(slide, page: int, total: int, brand: str = "Apex AI"):
    _rect(slide, Inches(0), Inches(7.15), Inches(13.333), Inches(0.02), C_LINE)
    _textbox(slide, Inches(0.7), Inches(7.2), Inches(4), Inches(0.28), brand, size=11, color=C_SOFT)
    _textbox(
        slide,
        Inches(10.5),
        Inches(7.2),
        Inches(2.1),
        Inches(0.28),
        f"{page:02d} / {total:02d}",
        size=11,
        color=C_SOFT,
        align=PP_ALIGN.RIGHT,
    )


def _is_toc(title: str) -> bool:
    t = title or ""
    return any(k in t for k in ("\u76ee\u5f55", "\u5927\u7eb2", "\u8bae\u7a0b", "Contents", "Agenda", "TOC"))


def _build_cover(slide, deck: dict[str, Any], slide_data: dict[str, Any], total: int):
    _rect(slide, Inches(0), Inches(0), Inches(4.6), Inches(7.5), C_INK)
    _rect(slide, Inches(4.45), Inches(0), Inches(0.15), Inches(7.5), C_TEAL)
    _rect(slide, Inches(4.6), Inches(0), Inches(8.733), Inches(7.5), C_BG)
    _round_rect(slide, Inches(9.8), Inches(5.4), Inches(2.8), Inches(1.4), C_TEAL_SOFT)

    _textbox(
        slide, Inches(0.55), Inches(0.55), Inches(3.6), Inches(0.4), "APEX AI", size=14, bold=True, color=C_TEAL_SOFT
    )
    _textbox(
        slide, Inches(0.55), Inches(2.3), Inches(3.6), Inches(2.2), deck["title"], size=28, bold=True, color=C_WHITE
    )
    sub = deck.get("subtitle") or " | ".join(slide_data.get("bullets", [])[:2])
    if sub:
        _textbox(
            slide,
            Inches(0.55),
            Inches(5.0),
            Inches(3.6),
            Inches(1.2),
            sub,
            size=14,
            color=RGBColor(0xB7, 0xC4, 0xCE),
        )

    _textbox(
        slide,
        Inches(5.2),
        Inches(2.4),
        Inches(7.2),
        Inches(0.5),
        "\u6f14\u793a\u6587\u7a3f",
        size=14,
        bold=True,
        color=C_TEAL,
    )
    _textbox(slide, Inches(5.2), Inches(3.0), Inches(7.2), Inches(1.4), deck["title"], size=36, bold=True, color=C_INK)
    meta = " | ".join([b for b in slide_data.get("bullets", [])[:3] if b]) or (
        "\u53ef\u7f16\u8f91 | \u53ef\u6c47\u62a5 | AI \u751f\u6210"
    )
    _textbox(slide, Inches(5.2), Inches(4.7), Inches(7.0), Inches(1.0), meta, size=15, color=C_MUTED)
    _add_footer(slide, 1, total)


def _build_toc(slide, slide_data: dict[str, Any], page: int, total: int):
    _rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(7.5), C_BG)
    _rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), C_TEAL)
    _textbox(
        slide,
        Inches(0.7),
        Inches(0.4),
        Inches(10),
        Inches(0.6),
        slide_data["title"] or "\u76ee\u5f55",
        size=28,
        bold=True,
        color=C_INK,
    )
    _rect(slide, Inches(0.7), Inches(1.1), Inches(1.2), Inches(0.06), C_TEAL)

    bullets = slide_data.get("bullets") or []
    cols = 2
    card_w = Inches(5.7)
    card_h = Inches(1.05)
    start_top = Inches(1.5)
    gap_x = Inches(0.5)
    gap_y = Inches(0.28)
    left0 = Inches(0.7)

    for i, item in enumerate(bullets[:8]):
        col = i % cols
        row = i // cols
        left = left0 + col * (card_w + gap_x)
        top = start_top + row * (card_h + gap_y)
        _round_rect(slide, left, top, card_w, card_h, C_WHITE)
        _rect(slide, left, top, Inches(0.1), card_h, C_TEAL)
        _round_rect(slide, left + Inches(0.28), top + Inches(0.28), Inches(0.5), Inches(0.5), C_TEAL_SOFT)
        _textbox(
            slide,
            left + Inches(0.28),
            top + Inches(0.32),
            Inches(0.5),
            Inches(0.45),
            f"{i + 1:02d}",
            size=12,
            bold=True,
            color=C_TEAL_DEEP,
            align=PP_ALIGN.CENTER,
        )
        _textbox(
            slide,
            left + Inches(1.0),
            top + Inches(0.32),
            card_w - Inches(1.2),
            Inches(0.5),
            item,
            size=16,
            bold=True,
            color=C_INK,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    _add_footer(slide, page, total)


def _build_content(slide, slide_data: dict[str, Any], page: int, total: int):
    _rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(7.5), C_BG)
    _rect(slide, Inches(0), Inches(0), Inches(0.18), Inches(7.5), C_TEAL)
    _textbox(
        slide,
        Inches(0.7),
        Inches(0.35),
        Inches(11.5),
        Inches(0.65),
        slide_data["title"],
        size=26,
        bold=True,
        color=C_INK,
    )
    _rect(slide, Inches(0.7), Inches(1.05), Inches(1.4), Inches(0.06), C_TEAL)

    bullets = slide_data.get("bullets") or ["\uff08\u5f85\u8865\u5145\uff09"]
    n = len(bullets)
    if 3 <= n <= 4:
        positions = [
            (Inches(0.7), Inches(1.5)),
            (Inches(6.9), Inches(1.5)),
            (Inches(0.7), Inches(4.1)),
            (Inches(6.9), Inches(4.1)),
        ]
        for i, item in enumerate(bullets[:4]):
            left, top = positions[i]
            _round_rect(slide, left, top, Inches(5.7), Inches(2.2), C_WHITE)
            _rect(slide, left, top, Inches(5.7), Inches(0.1), C_TEAL if i % 2 == 0 else C_TEAL_DEEP)
            _textbox(
                slide,
                left + Inches(0.35),
                top + Inches(0.35),
                Inches(1.0),
                Inches(0.4),
                f"0{i + 1}",
                size=18,
                bold=True,
                color=C_TEAL,
            )
            _textbox(
                slide,
                left + Inches(0.35),
                top + Inches(0.85),
                Inches(5.0),
                Inches(1.1),
                item,
                size=16,
                color=C_INK,
            )
    else:
        top = Inches(1.4)
        for i, item in enumerate(bullets[:6]):
            y = top + Inches(i * 0.85)
            _round_rect(slide, Inches(0.7), y, Inches(11.9), Inches(0.72), C_WHITE)
            _round_rect(slide, Inches(0.95), y + Inches(0.14), Inches(0.45), Inches(0.45), C_TEAL_SOFT)
            _textbox(
                slide,
                Inches(0.95),
                y + Inches(0.18),
                Inches(0.45),
                Inches(0.4),
                str(i + 1),
                size=12,
                bold=True,
                color=C_TEAL_DEEP,
                align=PP_ALIGN.CENTER,
            )
            _textbox(
                slide,
                Inches(1.65),
                y + Inches(0.18),
                Inches(10.5),
                Inches(0.45),
                item,
                size=16,
                color=C_INK,
                anchor=MSO_ANCHOR.MIDDLE,
            )
    _add_footer(slide, page, total)


def build_pptx(deck: dict[str, Any], out_path: Path) -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    slides = deck["slides"]
    total = len(slides)

    for idx, slide_data in enumerate(slides):
        slide = prs.slides.add_slide(blank)
        page = idx + 1
        title = slide_data.get("title", "")
        if idx == 0:
            _build_cover(slide, deck, slide_data, total)
        elif _is_toc(title) or (idx == 1 and len(slide_data.get("bullets") or []) >= 3 and len(title) <= 10):
            toc_data = {
                "title": title if title else "\u76ee\u5f55",
                "bullets": slide_data.get("bullets") or [],
            }
            _build_toc(slide, toc_data, page, total)
        else:
            _build_content(slide, slide_data, page, total)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("slides"), list):
            return data
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            if isinstance(data, dict) and isinstance(data.get("slides"), list):
                return data
        except json.JSONDecodeError:
            return None
    return None


def _parse_markdown_slides(text: str, fallback_title: str) -> dict[str, Any]:
    slides: list[dict[str, Any]] = []
    blocks = re.split(r"(?=^#{1,3}\s+|^\u7b2c\s*\d+\s*\u9875)", text, flags=re.M)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        title = re.sub(r"^#+\s*", "", lines[0])
        title = re.sub(r"^\u7b2c\s*\d+\s*\u9875[\uff1a:\s]*", "", title).strip() or "\u5185\u5bb9"
        bullets = []
        for ln in lines[1:]:
            item = re.sub(r"^[-*\d.\u3001\uff09)\s]+", "", ln).strip()
            if item:
                bullets.append(item[:120])
        slides.append({"title": title[:80], "bullets": bullets[:6] or ["\uff08\u8865\u5145\u8981\u70b9\uff09"]})
    if not slides:
        slides = [
            {
                "title": fallback_title[:40] or "\u6f14\u793a\u6587\u7a3f",
                "bullets": [
                    "\u6839\u636e\u9700\u6c42\u81ea\u52a8\u751f\u6210",
                    "\u53ef\u5728 PowerPoint \u4e2d\u7ee7\u7eed\u7f16\u8f91",
                ],
            },
            {
                "title": "\u5185\u5bb9\u6982\u8981",
                "bullets": [line[:100] for line in text.splitlines() if line.strip()][:5]
                or ["\u6682\u65e0\u7ec6\u5219"],
            },
        ]
    return {
        "title": fallback_title[:60] or "AI \u751f\u6210\u6f14\u793a\u6587\u7a3f",
        "subtitle": "",
        "slides": slides[:15],
    }


def _normalize_deck(data: dict[str, Any], user_input: str) -> dict[str, Any]:
    title = str(data.get("title") or user_input[:40] or "AI \u751f\u6210\u6f14\u793a\u6587\u7a3f").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    slides_in = data.get("slides") or []
    slides: list[dict[str, Any]] = []
    for item in slides_in:
        if not isinstance(item, dict):
            continue
        st = str(item.get("title") or "\u672a\u547d\u540d\u9875\u9762").strip()[:80]
        bullets_raw = item.get("bullets") or []
        if isinstance(bullets_raw, str):
            bullets_raw = [bullets_raw]
        bullets = [str(b).strip()[:160] for b in bullets_raw if str(b).strip()][:6]
        if not bullets:
            note = str(item.get("note") or "").strip()
            bullets = [note] if note else ["\uff08\u5f85\u8865\u5145\uff09"]
        slides.append({"title": st, "bullets": bullets})
    if not slides:
        return _parse_markdown_slides("", title)
    return {"title": title, "subtitle": subtitle, "slides": slides[:15]}


def _deck_to_markdown(deck: dict[str, Any]) -> str:
    lines = [f"# {deck['title']}", ""]
    if deck.get("subtitle"):
        lines += [deck["subtitle"], ""]
    for i, s in enumerate(deck["slides"], 1):
        lines.append(f"## Slide {i}: {s['title']}")
        for b in s["bullets"]:
            lines.append(f"- {b}")
        lines.append("")
    return "\n".join(lines)


def generate_pptx_file(user_input: str) -> dict[str, str]:
    raw = generate_reply(user_input, PPT_JSON_PROMPT, tool_name="PPT\u72c2\u98d9")
    data = _extract_json(raw)
    if data is None:
        if ("\u6f14\u793a\u56de\u590d" in raw) or ("\u672a\u8fde\u4e0a\u5927\u6a21\u578b" in raw) or ("\u54cd\u5e94\u8d85\u65f6" in raw):
            deck = {
                "title": user_input.strip()[:40] or "\u6f14\u793a\u6587\u7a3f",
                "subtitle": "AI \u5927\u7eb2\u751f\u6210\u53d7\u9650\uff0c\u5df2\u8f93\u51fa\u53ef\u7f16\u8f91\u6a21\u677f\u9875",
                "slides": [
                    {
                        "title": user_input.strip()[:40] or "\u5c01\u9762",
                        "bullets": [
                            "\u6c47\u62a5\u573a\u666f\uff1a" + user_input.strip()[:60],
                            "\u8bf7\u914d\u7f6e\u53ef\u7528\u5927\u6a21\u578b\u540e\u91cd\u65b0\u751f\u6210\u5b8c\u6574\u5185\u5bb9",
                        ],
                    },
                    {
                        "title": "\u76ee\u5f55",
                        "bullets": [
                            "\u80cc\u666f\u4e0e\u76ee\u6807",
                            "\u5173\u952e\u8fdb\u5c55",
                            "\u95ee\u9898\u4e0e\u98ce\u9669",
                            "\u4e0b\u9636\u6bb5\u8ba1\u5212",
                        ],
                    },
                    {
                        "title": "\u80cc\u666f\u4e0e\u76ee\u6807",
                        "bullets": ["\u4e1a\u52a1\u80cc\u666f", "\u672c\u671f\u76ee\u6807", "\u6210\u529f\u6807\u51c6"],
                    },
                    {
                        "title": "\u5173\u952e\u8fdb\u5c55",
                        "bullets": ["\u6210\u679c\u4e00", "\u6210\u679c\u4e8c", "\u6570\u636e\u4eae\u70b9"],
                    },
                    {
                        "title": "\u95ee\u9898\u4e0e\u98ce\u9669",
                        "bullets": ["\u95ee\u9898\u63cf\u8ff0", "\u5f71\u54cd\u8bc4\u4f30", "\u5e94\u5bf9\u63aa\u65bd"],
                    },
                    {
                        "title": "\u4e0b\u9636\u6bb5\u8ba1\u5212",
                        "bullets": ["\u4f18\u5148\u7ea7\u4e8b\u9879", "\u8d44\u6e90\u9700\u6c42", "\u91cc\u7a0b\u7891"],
                    },
                ],
            }
            outline = raw
        else:
            deck = _normalize_deck(_parse_markdown_slides(raw, user_input.strip()[:40]), user_input)
            outline = raw
    else:
        deck = _normalize_deck(data, user_input)
        outline = _deck_to_markdown(deck)

    file_id = uuid.uuid4().hex[:12]
    safe_stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", deck["title"])[:40] or "apex_ppt"
    filename = f"{safe_stem}_{file_id}.pptx"
    out_path = PPT_DIR / filename
    build_pptx(deck, out_path)

    url = f"/generated/pptx/{filename}"
    return {
        "filename": filename,
        "file_url": url,
        "outline": outline,
        "title": deck["title"],
        "slide_count": str(len(deck["slides"])),
    }


def format_pptx_answer(meta: dict[str, str]) -> str:
    return (
        f"\u5df2\u751f\u6210\u53ef\u4e0b\u8f7d\u7684 PowerPoint \u6587\u4ef6\uff1a**{meta['title']}**"
        f"\uff08\u5171 {meta['slide_count']} \u9875\uff09\n\n"
        f"[\u70b9\u51fb\u4e0b\u8f7d PPT]({meta['file_url']})\n\n"
        f"---\n\n{meta['outline']}"
    )
