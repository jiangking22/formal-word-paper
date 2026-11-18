#!/usr/bin/env python3
"""Audit DOCX files for formal Chinese paper formatting problems."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}

SIMSUN_NAMES = {"SimSun", "\u5b8b\u4f53"}
LATIN_NAMES = {"Times New Roman"}
THEME_FONT_ATTRS = {
    "w:asciiTheme",
    "w:hAnsiTheme",
    "w:eastAsiaTheme",
    "w:csTheme",
    "w:cstheme",
}

# Common Traditional forms that differ from their Simplified equivalents.
TRADITIONAL_CANDIDATES = set(
    "這個為與於從學習數據處圖標題資實驗軟體點雲導顯濾"
    "結論問過總參設應訊發現開檢觀區時間範圍衛獨築"
)

NON_SI_PATTERNS = [
    "\u514b\u6bcf\u5343\u514b",
    "\u6beb\u514b/\u5343\u514b",
    "\u6beb\u514b\u6bcf\u5343\u514b",
    "\u6beb\u5347",
    "\u5fae\u5347",
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


def bool_prop_enabled(parent: ET.Element | None, path: str) -> bool:
    node = child(parent, path)
    if node is None:
        return False
    val = get_attr(node, "w:val")
    return val is None or val.lower() not in {"0", "false", "off"}


def local_attr_name(attr_name: str) -> str:
    if attr_name.startswith("{"):
        return attr_name.split("}", 1)[1]
    return attr_name


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
    return val.upper() not in {"000000", "AUTO"}


def style_maps(
    styles_root: ET.Element | None,
) -> tuple[dict[str, str], dict[str, ET.Element], str | None]:
    names: dict[str, str] = {}
    elements: dict[str, ET.Element] = {}
    default_paragraph_style: str | None = None
    if styles_root is None:
        return names, elements, default_paragraph_style

    for st in styles_root.findall(".//w:style", NS):
        sid = get_attr(st, "w:styleId")
        if not sid:
            continue
        name_el = child(st, "w:name")
        names[sid] = (get_attr(name_el, "w:val") or sid).lower()
        elements[sid] = st
        if get_attr(st, "w:type") == "paragraph" and get_attr(st, "w:default") == "1":
            default_paragraph_style = sid

    return names, elements, default_paragraph_style


def used_paragraph_style_ids(
    document_root: ET.Element, default_paragraph_style: str | None
) -> set[str]:
    used: set[str] = set()
    for paragraph in document_root.findall(".//w:p", NS):
        sid = style_id(paragraph)
        if sid:
            used.add(sid)
        elif default_paragraph_style:
            used.add(default_paragraph_style)
    return used


def is_builtin_title_or_heading(style_name: str) -> bool:
    normalized = style_name.lower()
    return normalized in {
        "title",
        "heading 1",
        "heading 2",
        "heading 3",
        "\u6807\u9898 1",
        "\u6807\u9898 2",
        "\u6807\u9898 3",
    }


def is_heading(paragraph: ET.Element, names: dict[str, str]) -> bool:
    sid = style_id(paragraph)
    name = names.get(sid, sid).lower()
    text = text_of(paragraph).strip()
    return (
        "heading" in name
        or name.startswith("\u6807\u9898")
        or bool(re.match(r"^\d+(?:\.\d+){0,2}\s+", text))
    )


def is_caption(text: str) -> bool:
    return bool(re.match(r"^\s*(?:\u8868|\u56fe)\s*\d+", text))


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


def visual_heading_marker_props(ppr: ET.Element | None) -> list[str]:
    markers: list[str] = []
    for prop in ["w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:suppressLineNumbers"]:
        if bool_prop_enabled(ppr, prop):
            markers.append(prop.replace("w:", ""))
    return markers


def font_name_context(rfonts: ET.Element, attr: str) -> str:
    return f"{attr}={get_attr(rfonts, attr)}"


def audit_used_style_residue(
    style_names: dict[str, str], style_elements: dict[str, ET.Element], used_style_ids: set[str]
) -> list[Finding]:
    findings: list[Finding] = []
    for sid in sorted(used_style_ids):
        style_el = style_elements.get(sid)
        if style_el is None:
            continue

        sname = style_names.get(sid, sid)
        context = f"style={sid}; name={sname}"
        rpr = child(style_el, "w:rPr")
        ppr = child(style_el, "w:pPr")

        if is_builtin_title_or_heading(sname):
            findings.append(
                Finding(
                    "ERROR",
                    "Built-in Word title/heading style is used; use scrubbed custom paper styles",
                    context,
                )
            )

        if bool_prop_enabled(rpr, "w:b") or bool_prop_enabled(rpr, "w:bCs"):
            findings.append(
                Finding(
                    "WARN",
                    "Used style contains visual bold; remove unless explicitly required by template",
                    context,
                )
            )

        rfonts = child(rpr, "w:rFonts")
        if rfonts is None:
            findings.append(Finding("ERROR", "Used style does not explicitly set fonts", context))
        else:
            for attr in THEME_FONT_ATTRS:
                if get_attr(rfonts, attr) is not None:
                    findings.append(
                        Finding(
                            "ERROR",
                            "Used style retains theme font mapping",
                            f"{context}; {font_name_context(rfonts, attr)}",
                        )
                    )
            east_asia = get_attr(rfonts, "w:eastAsia")
            ascii_font = get_attr(rfonts, "w:ascii")
            hansi_font = get_attr(rfonts, "w:hAnsi")
            if east_asia and east_asia not in SIMSUN_NAMES:
                findings.append(Finding("ERROR", "Used style East Asian font is not SimSun", f"{context}; eastAsia={east_asia}"))
            if ascii_font and ascii_font not in LATIN_NAMES:
                findings.append(Finding("WARN", "Used style Latin font is not Times New Roman", f"{context}; ascii={ascii_font}"))
            if hansi_font and hansi_font not in LATIN_NAMES:
                findings.append(Finding("WARN", "Used style hAnsi font is not Times New Roman", f"{context}; hAnsi={hansi_font}"))

        sz = get_attr(child(rpr, "w:sz"), "w:val")
        sz_cs = get_attr(child(rpr, "w:szCs"), "w:val")
        if sz and sz_cs and sz != sz_cs:
            findings.append(Finding("ERROR", "Used style has mismatched w:sz and w:szCs", f"{context}; sz={sz}; szCs={sz_cs}"))
        if sz and not sz_cs:
            findings.append(Finding("WARN", "Used style lacks w:szCs; Word may use complex-script defaults", f"{context}; sz={sz}"))
        if sz_cs and not sz:
            findings.append(Finding("ERROR", "Used style lacks w:sz while w:szCs is set", f"{context}; szCs={sz_cs}"))

        if has_child(rpr, "w:kern") or has_child(rpr, "w:spacing"):
            findings.append(Finding("ERROR", "Used style retains character spacing/kern residue", context))

        marker_props = visual_heading_marker_props(ppr)
        if ("heading" in sname or sname.startswith("\u6807\u9898")) and marker_props:
            findings.append(
                Finding(
                    "WARN",
                    "Heading style may show Word black square formatting marker",
                    f"{context}; props={','.join(marker_props)}",
                )
            )

    return findings


def audit_document(docx: Path) -> list[Finding]:
    document = read_xml(docx, "word/document.xml")
    styles = read_xml(docx, "word/styles.xml")
    if document is None:
        return [Finding("ERROR", "word/document.xml not found; file is not a valid DOCX")]

    style_names, style_elements, default_paragraph_style = style_maps(styles)
    used_style_ids = used_paragraph_style_ids(document, default_paragraph_style)
    findings: list[Finding] = []
    full_text = text_of(document)

    trad_found = sorted({ch for ch in full_text if ch in TRADITIONAL_CANDIDATES})
    if trad_found:
        findings.append(
            Finding(
                "WARN",
                "Traditional Chinese candidate characters found; review titles, quotations, and prose in context",
                "".join(trad_found[:80]),
            )
        )

    for pattern in NON_SI_PATTERNS:
        if pattern in full_text:
            findings.append(Finding("ERROR", "Non-SI or nonstandard Chinese unit expression found", pattern))

    findings.extend(audit_used_style_residue(style_names, style_elements, used_style_ids))

    normal = None
    for sid, style_el in style_elements.items():
        if style_names.get(sid, "") == "normal" or style_names.get(sid, "") == "\u6b63\u6587":
            normal = style_el
            break
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
            heading = is_heading(block, style_names)
            caption = is_caption(text)
            context = para_label(paragraph_index, block)

            if heading:
                if not re.match(r"^\d+(?:\.\d+){0,2}\s+", text):
                    findings.append(Finding("WARN", "Heading may be missing required numeric prefix", context))
                ppr = child(block, "w:pPr")
                marker_props = visual_heading_marker_props(ppr)
                if marker_props:
                    findings.append(
                        Finding(
                            "WARN",
                            "Heading paragraph may show Word black square formatting marker",
                            f"{context}; props={','.join(marker_props)}",
                        )
                    )
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

            table_match = re.match(r"^\s*\u8868\s*(\d+)", text)
            if table_match:
                table_numbers.append(int(table_match.group(1)))
            figure_match = re.match(r"^\s*\u56fe\s*(\d+)", text)
            if figure_match:
                figure_numbers.append(int(figure_match.group(1)))
                if not last_was_drawing:
                    findings.append(Finding("WARN", "Figure caption is not immediately below an image", context))
            reference_match = re.match(r"^\s*\[(\d+)\]", text)
            if reference_match:
                reference_numbers.append(int(reference_match.group(1)))

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
                direct_bold = bool_prop_enabled(rpr, "w:b") or bool_prop_enabled(rpr, "w:bCs")
                direct_size = has_child(rpr, "w:sz") or has_child(rpr, "w:szCs")
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

                if re.search(r"(?<![A-Za-z])([tP])\s*(=|<|>)", rtext):
                    if not bool_prop_enabled(rpr, "w:i"):
                        findings.append(Finding("WARN", "Statistical symbol t/P may need italics", f"{context}; text={rtext[:30]!r}"))

            last_was_drawing = has_drawing(block)
            previous_paragraph_text = text

        elif block.tag == qn("w:tbl"):
            if not re.match(r"^\s*\u8868\s*\d+", previous_paragraph_text):
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
