#!/usr/bin/env python3
"""Audit DOCX files for formal Chinese paper formatting problems."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

TRADITIONAL_CANDIDATES = set(
    "這個為與於從對學體圖標題藍變後來時發說資料實驗檢測統計討論"
    "應過問題環資訊進還會處庫參數質觀關係顯較廣東臺灣"
    "醫藥衛獲採計畫設構組織總結報論獻頁碼據"
    "開關閉區階層級類選擇輸網絡軟測試評價"
    "內寫讀並無當長機電權產業號務讓達壓劑濃樣證"
)

NON_SI_PATTERNS = [
    "克/升",
    "克每升",
    "毫克/千克",
    "毫克每千克",
    "毫升",
    "微升",
]


@dataclass
class Finding:
    level: str
    message: str
    context: str = ""

    def render(self) -> str:
        if self.context:
            return f"{self.level}: {self.message} [{self.context}]"
        return f"{self.level}: {self.message}"


def qn(tag: str) -> str:
    prefix, name = tag.split(":")
    return f"{{{NS[prefix]}}}{name}"


def read_xml(docx: Path, name: str) -> ET.Element | None:
    try:
        with zipfile.ZipFile(docx) as zf:
            with zf.open(name) as fh:
                return ET.parse(fh).getroot()
    except KeyError:
        return None


def text_of(node: ET.Element) -> str:
    return "".join(t.text or "" for t in node.findall(".//w:t", NS))


def get_attr(node: ET.Element | None, attr: str) -> str | None:
    if node is None:
        return None
    return node.get(qn(attr))


def child(parent: ET.Element | None, path: str) -> ET.Element | None:
    if parent is None:
        return None
    return parent.find(path, NS)


def has_child(parent: ET.Element | None, path: str) -> bool:
    return child(parent, path) is not None


def style_id(paragraph: ET.Element) -> str:
    p_style = child(child(paragraph, "w:pPr"), "w:pStyle")
    return get_attr(p_style, "w:val") or ""


def run_text(run: ET.Element) -> str:
    return "".join(t.text or "" for t in run.findall(".//w:t", NS))


def color_info(rpr: ET.Element | None) -> tuple[str | None, str | None]:
    color = child(rpr, "w:color")
    if color is None:
        return None, None
    return get_attr(color, "w:val"), get_attr(color, "w:themeColor")


def is_nonblack_color(val: str | None, theme: str | None) -> bool:
    if theme:
        return True
    if not val:
        return False
    normalized = val.upper()
    return normalized not in {"000000", "AUTO"}


def style_maps(styles_root: ET.Element | None) -> tuple[dict[str, str], dict[str, ET.Element]]:
    names: dict[str, str] = {}
    elements: dict[str, ET.Element] = {}
    if styles_root is None:
        return names, elements
    for st in styles_root.findall(".//w:style", NS):
        sid = get_attr(st, "w:styleId")
        if not sid:
            continue
        name_el = child(st, "w:name")
        names[sid] = (get_attr(name_el, "w:val") or sid).lower()
        elements[sid] = st
    return names, elements


def is_heading(paragraph: ET.Element, names: dict[str, str]) -> bool:
    sid = style_id(paragraph)
    name = names.get(sid, sid).lower()
    text = text_of(paragraph).strip()
    return (
        "heading" in name
        or name.startswith("标题")
        or bool(re.match(r"^\d+(?:\.\d+){0,2}(?:、|\s+)", text))
    )


def is_caption(text: str) -> bool:
    return bool(re.match(r"^\s*(表|图)\s*\d+", text))


def para_label(index: int, paragraph: ET.Element) -> str:
    text = re.sub(r"\s+", " ", text_of(paragraph).strip())
    if len(text) > 60:
        text = text[:57] + "..."
    return f"paragraph {index}: {text}"


def iter_body_blocks(document_root: ET.Element) -> Iterable[ET.Element]:
    body = child(document_root, "w:body")
    if body is None:
        return []
    return list(body)


def has_drawing(paragraph: ET.Element) -> bool:
    return paragraph.find(".//w:drawing", NS) is not None or paragraph.find(".//w:pict", NS) is not None


def audit_document(docx: Path) -> list[Finding]:
    document = read_xml(docx, "word/document.xml")
    styles = read_xml(docx, "word/styles.xml")
    if document is None:
        return [Finding("ERROR", "word/document.xml not found; file is not a valid DOCX")]

    style_names, style_elements = style_maps(styles)
    findings: list[Finding] = []
    full_text = text_of(document)

    trad_found = sorted({ch for ch in full_text if ch in TRADITIONAL_CANDIDATES})
    if trad_found:
        findings.append(
            Finding(
                "ERROR",
                "Traditional Chinese candidate characters found",
                "".join(trad_found[:80]),
            )
        )

    for pattern in NON_SI_PATTERNS:
        if pattern in full_text:
            findings.append(Finding("ERROR", "Non-SI or nonstandard Chinese unit expression found", pattern))

    normal = style_elements.get("Normal")
    if normal is not None:
        normal_rpr = child(normal, "w:rPr")
        normal_ppr = child(normal, "w:pPr")
        sz = get_attr(child(normal_rpr, "w:sz"), "w:val")
        spacing = child(normal_ppr, "w:spacing")
        line = get_attr(spacing, "w:line")
        if sz and sz != "24":
            findings.append(Finding("WARN", "Normal style is not 12 pt", f"w:sz={sz}"))
        if line and line != "360":
            findings.append(Finding("WARN", "Normal style line spacing is not 1.5", f"w:line={line}"))

    paragraph_index = 0
    table_numbers: list[int] = []
    figure_numbers: list[int] = []
    reference_numbers: list[int] = []
    previous_paragraph_text = ""
    last_was_drawing = False

    for block in iter_body_blocks(document):
        if block.tag == qn("w:p"):
            paragraph_index += 1
            text = text_of(block).strip()
            sid = style_id(block)
            sname = style_names.get(sid, sid).lower()
            heading = is_heading(block, style_names)
            caption = is_caption(text)
            context = para_label(paragraph_index, block)

            if heading:
                if not re.match(r"^\d+(?:\.\d+){0,2}(?:、|\s+)", text):
                    findings.append(Finding("WARN", "Heading may be missing required numeric prefix", context))
                ppr = child(block, "w:pPr")
                ind = child(ppr, "w:ind")
                left = get_attr(ind, "w:left")
                if left not in {None, "0"}:
                    findings.append(Finding("ERROR", "Heading is not flush left", f"{context}; left={left}"))

                style_el = style_elements.get(sid)
                style_color_val, style_theme = color_info(child(style_el, "w:rPr"))
                if is_nonblack_color(style_color_val, style_theme):
                    findings.append(
                        Finding(
                            "ERROR",
                            "Heading style uses non-black or theme color",
                            f"{context}; style={sid}; color={style_color_val}; theme={style_theme}",
                        )
                    )

            if re.match(r"^\s*表\s*(\d+)", text):
                table_numbers.append(int(re.match(r"^\s*表\s*(\d+)", text).group(1)))
            if re.match(r"^\s*图\s*(\d+)", text):
                figure_numbers.append(int(re.match(r"^\s*图\s*(\d+)", text).group(1)))
                if not last_was_drawing:
                    findings.append(Finding("WARN", "Figure caption is not immediately below an image", context))
            if re.match(r"^\s*\[(\d+)\]", text):
                reference_numbers.append(int(re.match(r"^\s*\[(\d+)\]", text).group(1)))

            ppr = child(block, "w:pPr")
            if not heading and not caption:
                for prop in ["w:spacing", "w:ind", "w:jc"]:
                    if has_child(ppr, prop):
                        findings.append(Finding("WARN", "Body paragraph has direct paragraph formatting", f"{context}; {prop}"))

            for run in block.findall("w:r", NS):
                rtext = run_text(run)
                if not rtext.strip():
                    continue
                rpr = child(run, "w:rPr")
                color_val, theme_color = color_info(rpr)
                direct_bold = has_child(rpr, "w:b")
                direct_size = has_child(rpr, "w:sz")
                direct_font = has_child(rpr, "w:rFonts")
                direct_color = is_nonblack_color(color_val, theme_color)

                if heading and direct_color:
                    findings.append(
                        Finding(
                            "ERROR",
                            "Heading run uses non-black or theme color",
                            f"{context}; text={rtext[:30]!r}; color={color_val}; theme={theme_color}",
                        )
                    )

                if not heading and not caption:
                    if direct_bold:
                        findings.append(Finding("ERROR", "Body run has direct bold formatting", f"{context}; text={rtext[:30]!r}"))
                    if direct_color:
                        findings.append(
                            Finding(
                                "ERROR",
                                "Body run has non-black or theme color",
                                f"{context}; text={rtext[:30]!r}; color={color_val}; theme={theme_color}",
                            )
                        )
                    if direct_size or direct_font:
                        findings.append(
                            Finding(
                                "WARN",
                                "Body run has direct font or size formatting",
                                f"{context}; text={rtext[:30]!r}",
                            )
                        )

                if re.search(r"(?<![A-Za-z])([tP])\s*(=|<|>|≤|≥)", rtext):
                    if not has_child(rpr, "w:i"):
                        findings.append(Finding("WARN", "Statistical symbol t/P may need italics", f"{context}; text={rtext[:30]!r}"))

            last_was_drawing = has_drawing(block)
            previous_paragraph_text = text

        elif block.tag == qn("w:tbl"):
            if not re.match(r"^\s*表\s*\d+", previous_paragraph_text):
                findings.append(Finding("WARN", "Table is not immediately preceded by a table caption", f"after paragraph {paragraph_index}"))
            last_was_drawing = False

    for label, numbers in [("table", table_numbers), ("figure", figure_numbers), ("reference", reference_numbers)]:
        if numbers:
            expected = list(range(1, len(numbers) + 1))
            if numbers != expected:
                findings.append(Finding("ERROR", f"{label.capitalize()} numbering is not sequential", f"found={numbers}; expected={expected}"))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a DOCX for formal Chinese paper formatting issues.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()

    if not args.docx.exists():
        print(f"ERROR: File not found: {args.docx}", file=sys.stderr)
        return 2

    findings = audit_document(args.docx)
    error_count = sum(1 for f in findings if f.level == "ERROR")
    warn_count = sum(1 for f in findings if f.level == "WARN")

    if findings:
        for finding in findings:
            print(finding.render())
    else:
        print("PASS: No audit findings.")

    print(f"Summary: {error_count} error(s), {warn_count} warning(s).")

    if error_count or (args.warnings_as_errors and warn_count):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
