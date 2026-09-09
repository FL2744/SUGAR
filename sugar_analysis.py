#!/usr/bin/env python3
"""Deterministic analysis reports for SUGAR CSV and Excel exports."""

from __future__ import annotations

import json
import math
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


NAVY = "#173F5F"
BLUE = "#32779E"
GOLD = "#EDBA45"
PALE = "#F1F5F8"
TEXT = "#202B35"
RTL_PATTERN = re.compile(r"[\u0590-\u08ff]")
ENGAGEMENT_KEYS = ("like_count", "reply_count", "retweet_count", "repost_count",
                   "quote_count", "bookmark_count")


def _read_results(source_file: str) -> pd.DataFrame:
    path = Path(source_file)
    if not path.is_file():
        raise FileNotFoundError(f"Results file not found: {path}")
    if path.suffix.casefold() == ".xlsx":
        return pd.read_excel(path, sheet_name="posts")
    if path.suffix.casefold() == ".csv":
        return pd.read_csv(path)
    raise ValueError("Analysis input must be a SUGAR .csv or .xlsx file.")


def _stats_dict(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        raw = value
    else:
        try:
            raw = json.loads(str(value)) if pd.notna(value) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = {}
    result = {}
    for key, value in raw.items():
        try:
            result[key] = float(value or 0)
        except (TypeError, ValueError):
            result[key] = 0.0
    return result


def _plain_query(value: Any) -> str:
    query = str(value or "").lstrip("'")
    query = re.sub(r"\s+\([^)]*lang:[^)]*\)", "", query, flags=re.I)
    query = re.sub(r"\s+-?is:retweet\b", "", query, flags=re.I)
    return query.strip() or "Unspecified"


def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if df.empty:
        raise ValueError("The selected results file contains no posts.")
    work = df.copy()
    for column in ("detected_language", "inferred_location", "username", "query",
                   "original_text", "translated_en", "tweet_id"):
        if column not in work:
            work[column] = ""
    stats = work.get("raw_stats", pd.Series([{}] * len(work))).map(_stats_dict)
    work["impressions"] = stats.map(lambda d: d.get("impression_count", 0))
    work["engagement"] = stats.map(
        lambda d: sum(d.get(key, 0) for key in ENGAGEMENT_KEYS)
    )
    work["engagement_rate"] = work.apply(
        lambda row: row["engagement"] / row["impressions"]
        if row["impressions"] else 0,
        axis=1,
    )
    work["date"] = pd.to_datetime(work.get("date_iso"), errors="coerce", utc=True)
    work["query_term"] = work["query"].map(_plain_query)
    work["language"] = work["detected_language"].fillna("Unknown").replace("", "Unknown")
    work["location"] = work["inferred_location"].fillna("Unassigned").replace("", "Unassigned")
    work["confidence"] = pd.to_numeric(
        work.get("location_confidence"), errors="coerce"
    )

    total_impressions = int(work["impressions"].sum())
    total_engagement = int(work["engagement"].sum())
    ranked = work.sort_values("engagement", ascending=False)
    cumulative = ranked["engagement"].cumsum()
    total = max(float(total_engagement), 1.0)
    top_shares = {
        n: float(cumulative.iloc[min(n, len(cumulative)) - 1] / total)
        for n in (1, 5, 10) if len(cumulative)
    }
    valid_dates = work["date"].dropna()
    metrics = {
        "posts": len(work),
        "unique_ids": int(work["tweet_id"].replace("", pd.NA).nunique()),
        "impressions": total_impressions,
        "engagement": total_engagement,
        "weighted_rate": total_engagement / total_impressions if total_impressions else 0,
        "start_date": valid_dates.min().strftime("%Y-%m-%d") if len(valid_dates) else "Unknown",
        "end_date": valid_dates.max().strftime("%Y-%m-%d") if len(valid_dates) else "Unknown",
        "top_shares": top_shares,
        "median_confidence": float(work["confidence"].median())
        if work["confidence"].notna().any() else math.nan,
        "high_confidence": int((work["confidence"] >= 0.8).sum()),
        "missing_locations": int((work["location"] == "Unassigned").sum()),
    }
    return work, metrics


def _chart_bar(series: pd.Series, title: str, xlabel: str, output: Path,
               color: str = BLUE, limit: int = 10) -> None:
    values = series.head(limit).sort_values()
    fig, ax = plt.subplots(figsize=(8.0, 3.6))
    ax.barh([str(x) for x in values.index], values.values, color=color)
    ax.set_title(title, fontsize=13, weight="bold", color=TEXT, pad=12)
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    for index, value in enumerate(values.values):
        ax.text(value, index, f" {int(value):,}", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _chart_concentration(work: pd.DataFrame, output: Path) -> None:
    ranked = work.sort_values("engagement", ascending=False)["engagement"]
    cumulative = ranked.cumsum() / max(float(ranked.sum()), 1.0) * 100
    fig, ax = plt.subplots(figsize=(8.0, 3.4))
    ax.plot(range(1, len(cumulative) + 1), cumulative, color=BLUE, linewidth=2.5)
    ax.fill_between(range(1, len(cumulative) + 1), cumulative, color=BLUE, alpha=0.14)
    ax.set_title("Engagement concentration", fontsize=13, weight="bold", color=TEXT)
    ax.set_xlabel("Posts ranked by engagement")
    ax.set_ylabel("Cumulative share (%)")
    ax.set_ylim(0, 105)
    ax.grid(alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _frequent_terms(work: pd.DataFrame) -> list[tuple[str, int]]:
    stop = {"the", "and", "for", "that", "this", "with", "from", "are", "was",
            "have", "has", "you", "your", "not", "but", "they", "their", "about",
            "https", "http", "www", "com", "amp", "our", "all", "its", "will"}
    text = " ".join(work["translated_en"].fillna("").astype(str))
    if not text.strip():
        text = " ".join(work["original_text"].fillna("").astype(str))
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text.casefold())
    return Counter(word for word in words if word not in stop).most_common(12)


def _narrative(work: pd.DataFrame, metrics: dict[str, Any]) -> dict[str, Any]:
    languages = work["language"].value_counts()
    locations = work["location"].value_counts()
    queries = work["query_term"].value_counts()
    top_language = str(languages.index[0])
    top_location = str(locations.index[0])
    top_share = metrics["top_shares"].get(1, 0)
    summary = [
        f"The dataset contains {metrics['posts']:,} posts spanning {metrics['start_date']} to {metrics['end_date']}.",
        f"{top_language} is the most frequently detected language ({int(languages.iloc[0]):,} posts).",
        f"Engagement is concentrated: the leading post contributes {top_share:.0%} of recorded engagement.",
        f"The most common inferred location is {top_location} ({int(locations.iloc[0]):,} posts).",
    ]
    if not math.isnan(metrics["median_confidence"]):
        summary.append(
            f"Geography remains provisional: median location confidence is "
            f"{metrics['median_confidence']:.2f}, and {metrics['high_confidence']:,} posts "
            "have confidence of at least 0.80."
        )
    return {
        "languages": languages,
        "locations": locations,
        "queries": queries,
        "summary": summary,
        "terms": _frequent_terms(work),
    }


def _set_docx_cell_shading(cell, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill.replace("#", ""))
    cell._tc.get_or_add_tcPr().append(shading)


def _set_docx_run_font(run, text: str = "") -> None:
    """Set Latin and East Asian font declarations for multilingual text."""
    from docx.oxml.ns import qn
    name = "Songti SC" if re.search(r"[\u3400-\u9fff]", text) else "Arial Unicode MS"
    run.font.name = name
    fonts = run._element.get_or_add_rPr().rFonts
    for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attribute}"), name)


def _docx_table(document, headers: list[str], rows: list[list[Any]], widths=None):
    from io import BytesIO
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        _set_docx_cell_shading(cell, NAVY)
        run = cell.paragraphs[0].add_run(header)
        run.bold = True
        _set_docx_run_font(run, header)
        run.font.color.rgb = RGBColor(255, 255, 255)
        run.font.size = Pt(9)
    for row_index, row in enumerate(rows):
        cells = table.add_row().cells
        for index, value in enumerate(row):
            value_text = str(value)
            cells[index].text = value_text
            # LibreOffice and some PDF converters omit CJK glyphs from Word
            # table cells even when the correct macOS font is declared. Embed
            # just those short labels as crisp inline images for portability.
            if re.search(r"[\u3400-\u9fff]", value_text):
                from PIL import Image as PILImage, ImageDraw, ImageFont
                font = ImageFont.truetype(
                    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 32
                )
                bounds = ImageDraw.Draw(PILImage.new("RGBA", (1, 1))).textbbox(
                    (0, 0), value_text, font=font
                )
                label = PILImage.new(
                    "RGBA", (max(bounds[2] - bounds[0] + 8, 12), 44), "white"
                )
                ImageDraw.Draw(label).text((4, 2), value_text, font=font, fill=TEXT)
                image_stream = BytesIO()
                label.save(image_stream, format="PNG")
                image_stream.seek(0)
                paragraph = cells[index].paragraphs[0]
                paragraph.clear()
                paragraph.add_run().add_picture(image_stream, height=Pt(10))
            cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_index % 2:
                _set_docx_cell_shading(cells[index], PALE)
            for paragraph in cells[index].paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                if RTL_PATTERN.search(value_text):
                    from docx.oxml import OxmlElement
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    bidi = OxmlElement("w:bidi")
                    paragraph._p.get_or_add_pPr().append(bidi)
                    for run in paragraph.runs:
                        rtl = OxmlElement("w:rtl")
                        run._element.get_or_add_rPr().append(rtl)
                else:
                    paragraph.alignment = (
                        WD_ALIGN_PARAGRAPH.RIGHT if index
                        else WD_ALIGN_PARAGRAPH.LEFT
                    )
                for run in paragraph.runs:
                    _set_docx_run_font(run, run.text)
                    run.font.size = Pt(9)
        if widths:
            for cell, width in zip(cells, widths):
                cell.width = Inches(width)
    document.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def _write_docx(work: pd.DataFrame, metrics: dict[str, Any], info: dict[str, Any],
                charts: dict[str, Path], source_file: str, output_file: str) -> None:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor
    document = Document()
    section = document.sections[0]
    section.page_height, section.page_width = Inches(11), Inches(8.5)
    section.top_margin = section.bottom_margin = Inches(0.7)
    section.left_margin = section.right_margin = Inches(0.75)
    styles = document.styles
    styles["Normal"].font.name = "Arial Unicode MS"
    styles["Normal"].font.size = Pt(10.5)
    styles["Normal"].font.color.rgb = RGBColor.from_string(TEXT[1:])
    styles["Title"].font.name = "Aptos Display"
    styles["Title"].font.size = Pt(28)
    styles["Title"].font.bold = True
    styles["Title"].font.color.rgb = RGBColor.from_string(NAVY[1:])
    for name, size in (("Heading 1", 20), ("Heading 2", 13)):
        styles[name].font.name = "Aptos Display"
        styles[name].font.size = Pt(size)
        styles[name].font.bold = True
        styles[name].font.color.rgb = RGBColor.from_string(NAVY[1:])

    title = document.add_paragraph(style="Title")
    title.add_run("Social Search Posts Analysis")
    # Some Word themes attach a decorative rule to Title paragraphs. Remove it
    # so the report title remains clean in Word and LibreOffice.
    title_properties = title._p.get_or_add_pPr()
    title_properties.remove(title_properties.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pBdr"
    )) if title_properties.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pBdr"
    ) is not None else None
    subtitle = document.add_paragraph(
        f"A descriptive review of {metrics['posts']:,} social media posts collected through SUGAR"
    )
    subtitle.style = styles["Subtitle"]
    _docx_table(document, ["Measure", "Value", "Meaning"], [
        ["Posts", f"{metrics['posts']:,}", f"{metrics['unique_ids']:,} unique post IDs"],
        ["Impressions", f"{metrics['impressions']:,}", "Across sampled posts"],
        ["Total engagement", f"{metrics['engagement']:,}", "Likes, replies, reposts, quotes, bookmarks"],
        ["Weighted rate", f"{metrics['weighted_rate']:.1%}", "Engagement divided by impressions"],
    ], [2.0, 1.3, 3.2])
    document.add_heading("Executive summary", level=1)
    for sentence in info["summary"]:
        document.add_paragraph(sentence, style="List Bullet")
    document.add_heading("Bottom line", level=2)
    document.add_paragraph(
        "This report describes the collected sample, not the full population of online discussion. "
        "Query design, language filters, date boundaries, result ordering, and per-query caps all "
        "shape what appears in the workbook."
    )

    document.add_page_break()
    document.add_heading("1 Dataset and collection design", level=1)
    document.add_paragraph(
        f"The file contains {metrics['posts']:,} records observed from {metrics['start_date']} "
        f"through {metrics['end_date']}. The table below shows the contribution of each stored query."
    )
    query_rows = []
    for query, count in info["queries"].head(15).items():
        subset = work[work["query_term"] == query]["date"].dropna()
        span = (f"{subset.min():%Y-%m-%d} to {subset.max():%Y-%m-%d}"
                if len(subset) else "Unknown")
        query_rows.append([query, int(count), span])
    _docx_table(document, ["Query term", "Posts", "Observed date range UTC"], query_rows,
                [2.7, 0.8, 2.7])
    document.add_heading("Sampling caveat", level=2)
    document.add_paragraph(
        "Counts reflect the retrieved sample. They should not be interpreted as the total volume "
        "of matching discussion unless the collection exhausted every available result page."
    )

    document.add_page_break()
    document.add_heading("2 Language and geography", level=1)
    document.add_picture(str(charts["language"]), width=Inches(6.9))
    language_rows = []
    for language, count in info["languages"].head(12).items():
        subset = work[work["language"] == language]
        impressions = int(subset["impressions"].sum())
        engagement = int(subset["engagement"].sum())
        rate = engagement / impressions if impressions else 0
        language_rows.append([language, int(count), f"{impressions:,}", f"{engagement:,}", f"{rate:.1%}"])
    _docx_table(document, ["Language", "Posts", "Impressions", "Engagement", "Weighted rate"],
                language_rows)
    document.add_page_break()
    document.add_heading("Geographic distribution", level=1)
    document.add_picture(str(charts["location"]), width=Inches(6.9))
    document.add_heading("Location confidence and meaning", level=2)
    document.add_paragraph(
        "SUGAR locations may be inferred from profile information or post content and are not "
        "verified geotags. Treat the map as exploratory. Distinguish author location from places "
        "discussed before making claims about geographic origin."
    )

    document.add_page_break()
    document.add_heading("3 Engagement and discourse", level=1)
    document.add_picture(str(charts["engagement"]), width=Inches(6.9))
    top_rows = []
    for _, row in work.sort_values("engagement", ascending=False).head(10).iterrows():
        top_rows.append([
            row["username"] or "Unknown", row["query_term"], f"{int(row['impressions']):,}",
            f"{int(row['engagement']):,}", f"{row['engagement_rate']:.1%}",
        ])
    _docx_table(document, ["Account", "Query", "Impressions", "Engagement", "Rate"], top_rows)
    document.add_heading("Recurring vocabulary", level=2)
    document.add_paragraph(
        ", ".join(f"{word} ({count})" for word, count in info["terms"])
        or "No recurring English-language terms could be calculated."
    )
    document.add_paragraph(
        "These are descriptive word counts, not validated themes or stance classifications. "
        "Review posts in context before assigning qualitative codes."
    )

    document.add_page_break()
    document.add_heading("4 Recommendations for the next collection", level=1)
    recommendations = [
        "Increase depth and stratify long date ranges into daily or weekly intervals.",
        "Record requested count, returned count, pagination status, and collection time for every query.",
        "Store platform language and independent language detection separately.",
        "Separate author location, place discussed, and geocoding evidence into distinct fields.",
        "Report medians and concentration measures alongside totals and weighted engagement rates.",
        "Deduplicate near-identical narratives as well as post identifiers.",
    ]
    for recommendation in recommendations:
        document.add_paragraph(recommendation, style="List Bullet")
    document.add_heading("Method notes", level=2)
    document.add_paragraph(
        "Engagement is calculated as likes, replies, reposts or retweets, quotes, and bookmarks. "
        "Weighted engagement rate is total engagement divided by total recorded impressions. "
        "The analysis does not independently verify post content, identity, translation, or location."
    )
    document.add_heading("Source", level=2)
    document.add_paragraph(f"{Path(source_file).name} ({metrics['posts']:,} data rows).")

    for section in document.sections:
        footer = section.footer.paragraphs[0]
        footer.text = "Social Search Posts Analysis"
        footer.alignment = WD_ALIGN_PARAGRAPH.LEFT
    document.save(output_file)


def _write_pdf(work: pd.DataFrame, metrics: dict[str, Any], info: dict[str, Any],
               charts: dict[str, Path], source_file: str, output_file: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (BaseDocTemplate, Frame, Image, PageBreak,
                                   PageTemplate, Paragraph, Spacer, Table, TableStyle)
    styles = getSampleStyleSheet()
    unicode_font_path = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    body_font = "Helvetica"
    if unicode_font_path.is_file():
        pdfmetrics.registerFont(TTFont("SugarUnicode", str(unicode_font_path)))
        body_font = "SugarUnicode"
    styles.add(ParagraphStyle(name="SugarTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=26, leading=30, textColor=colors.HexColor(NAVY), alignment=0,
                              spaceAfter=12))
    styles.add(ParagraphStyle(name="SugarH1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=19, leading=23, textColor=colors.HexColor(NAVY), spaceAfter=10))
    styles.add(ParagraphStyle(name="SugarH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=12, leading=15, textColor=colors.HexColor(TEXT), spaceBefore=8,
                              spaceAfter=5))
    styles["BodyText"].fontName = body_font
    styles["BodyText"].fontSize = 9.5
    styles["BodyText"].leading = 13.5
    styles.add(ParagraphStyle(name="SugarTableHeader", parent=styles["BodyText"],
                              fontName="Helvetica-Bold", textColor=colors.white,
                              fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="SugarRTL", parent=styles["BodyText"],
                              alignment=2))

    class NumberedDocTemplate(BaseDocTemplate):
        def __init__(self, filename):
            super().__init__(filename, pagesize=letter, leftMargin=0.7*inch, rightMargin=0.7*inch,
                             topMargin=0.65*inch, bottomMargin=0.65*inch)
            frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
            self.addPageTemplates(PageTemplate(id="main", frames=frame, onPage=self.footer))
        def footer(self, canvas, doc):
            canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.HexColor("#607080"))
            canvas.drawString(self.leftMargin, 0.35*inch, "Social Search Posts Analysis")
            canvas.drawRightString(letter[0]-self.rightMargin, 0.35*inch, str(doc.page)); canvas.restoreState()

    def p(text, style="BodyText"):
        value = str(text)
        is_rtl = bool(RTL_PATTERN.search(value))
        if is_rtl:
            try:
                import arabic_reshaper
                from bidi.algorithm import get_display
                value = get_display(arabic_reshaper.reshape(value))
            except ImportError:
                pass
            if style == "BodyText":
                style = "SugarRTL"
        return Paragraph(value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles[style])
    def table(headers, rows, widths):
        data = [[p(h, "SugarTableHeader") for h in headers]] + [[p(v) for v in row] for row in rows]
        result = Table(data, colWidths=widths, repeatRows=1, hAlign="CENTER")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor(NAVY)), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#D9D9D9")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ] + [("BACKGROUND", (0,i), (-1,i), colors.HexColor(PALE)) for i in range(2, len(data), 2)]))
        return result

    story = [p("Social Search Posts Analysis", "SugarTitle"),
             p(f"A descriptive review of {metrics['posts']:,} social media posts collected through SUGAR"),
             Spacer(1, 14), table(["Measure", "Value", "Meaning"], [
                 ["Posts", f"{metrics['posts']:,}", f"{metrics['unique_ids']:,} unique post IDs"],
                 ["Impressions", f"{metrics['impressions']:,}", "Across sampled posts"],
                 ["Total engagement", f"{metrics['engagement']:,}", "Recorded interactions"],
                 ["Weighted rate", f"{metrics['weighted_rate']:.1%}", "Engagement / impressions"],
             ], [1.5*inch, 1.2*inch, 3.7*inch]), Spacer(1, 14), p("Executive summary", "SugarH1")]
    for sentence in info["summary"]:
        story += [p(f"- {sentence}"), Spacer(1, 4)]
    story += [p("Bottom line", "SugarH2"), p(
        "This report describes the collected sample, not the full population of online discussion. "
        "Retrieval settings and result ordering shape the workbook."), PageBreak(),
        p("1 Dataset and collection design", "SugarH1"),
        p(f"The file contains {metrics['posts']:,} records observed from {metrics['start_date']} through {metrics['end_date']}.")]
    query_rows = []
    for query, count in info["queries"].head(15).items():
        subset = work[work["query_term"] == query]["date"].dropna()
        span = f"{subset.min():%Y-%m-%d} to {subset.max():%Y-%m-%d}" if len(subset) else "Unknown"
        query_rows.append([query, int(count), span])
    story += [Spacer(1,8), table(["Query term", "Posts", "Observed date range UTC"], query_rows,
                                [2.8*inch, .7*inch, 2.9*inch]), Spacer(1,12), p("Sampling caveat", "SugarH2"),
              p("Counts describe retrieved records. They are not estimates of total discussion unless every result page was exhausted."),
              PageBreak(), p("2 Language and geography", "SugarH1"),
              Image(str(charts["language"]), width=6.5*inch, height=2.9*inch)]
    language_rows = []
    for language, count in info["languages"].head(12).items():
        subset = work[work["language"] == language]; imp=int(subset.impressions.sum()); eng=int(subset.engagement.sum())
        language_rows.append([language, int(count), f"{imp:,}", f"{eng:,}", f"{eng/imp if imp else 0:.1%}"])
    story += [table(["Language", "Posts", "Impressions", "Engagement", "Rate"], language_rows,
                    [1.2*inch,.7*inch,1.4*inch,1.4*inch,1*inch]), PageBreak(),
              p("Geographic distribution", "SugarH1"), Image(str(charts["location"]), width=6.5*inch, height=2.9*inch),
              p("Location confidence and meaning", "SugarH2"),
              p("Locations may be inferred from profile information or post content and are not verified geotags. Treat geographic findings as exploratory."),
              PageBreak(), p("3 Engagement and discourse", "SugarH1"),
              Image(str(charts["engagement"]), width=6.5*inch, height=2.8*inch)]
    top_rows=[]
    for _, row in work.sort_values("engagement", ascending=False).head(10).iterrows():
        top_rows.append([row.username or "Unknown", row.query_term, f"{int(row.impressions):,}", f"{int(row.engagement):,}", f"{row.engagement_rate:.1%}"])
    story += [table(["Account", "Query", "Impressions", "Engagement", "Rate"], top_rows,
                    [1.45*inch,1.65*inch,1.2*inch,1.2*inch,.8*inch]), p("Recurring vocabulary", "SugarH2"),
              p(", ".join(f"{w} ({c})" for w,c in info["terms"]) or "No recurring terms calculated."),
              p("These descriptive counts are not validated themes or stance classifications."), PageBreak(),
              p("4 Recommendations for the next collection", "SugarH1")]
    for item in ["Increase depth and stratify long date ranges into daily or weekly intervals.",
                 "Preserve query-level counts, pagination status, rate limits, and collection time.",
                 "Store platform and independently detected language separately.",
                 "Separate author location from places discussed.",
                 "Report medians and concentration measures alongside totals.",
                 "Deduplicate near-identical narratives as well as post IDs."]:
        story += [p(f"- {item}"), Spacer(1,5)]
    story += [p("Method notes", "SugarH2"), p(
        "Engagement is likes, replies, reposts or retweets, quotes, and bookmarks. Weighted rate is total engagement divided by impressions. "
        "The analysis does not independently verify content, identity, translation, or location."),
        p("Source", "SugarH2"), p(f"{Path(source_file).name} ({metrics['posts']:,} data rows).")]
    NumberedDocTemplate(output_file).build(story)


def create_analysis_report(source_file: str, output_stem: str,
                           output_format: str = "both") -> list[str]:
    """Create a polished SUGAR analysis report in DOCX, PDF, or both formats."""
    output_format = output_format.casefold()
    if output_format not in {"docx", "pdf", "both"}:
        raise ValueError("output_format must be docx, pdf, or both")
    df = _read_results(source_file)
    work, metrics = _prepare(df)
    info = _narrative(work, metrics)
    output_base = Path(output_stem).expanduser().resolve()
    output_base.parent.mkdir(parents=True, exist_ok=True)
    outputs = []
    with tempfile.TemporaryDirectory(prefix="sugar_analysis_") as temp_dir:
        temp = Path(temp_dir)
        charts = {"language": temp/"language.png", "location": temp/"location.png",
                  "engagement": temp/"engagement.png"}
        _chart_bar(info["languages"], "Posts by detected language", "Posts", charts["language"])
        _chart_bar(info["locations"], "Top inferred locations", "Posts", charts["location"], GOLD)
        _chart_concentration(work, charts["engagement"])
        if output_format in {"docx", "both"}:
            path = str(output_base.with_suffix(".docx")); _write_docx(work, metrics, info, charts, source_file, path); outputs.append(path)
        if output_format in {"pdf", "both"}:
            path = str(output_base.with_suffix(".pdf")); _write_pdf(work, metrics, info, charts, source_file, path); outputs.append(path)
    return outputs
