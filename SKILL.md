---
name: formal-word-paper
description: Create, edit, and QA formal Chinese Word papers and reports in DOCX format. Use when generating academic papers, formal reports, theses, coursework papers, or any Word article where formatting must avoid AI-looking artifacts such as random bold text, Traditional Chinese characters, blue/theme-colored headings, polluted direct formatting, inconsistent fonts, broken figure/table captions, non-SI units, or non-GB/T references.
---

# Formal Word Paper

Use this skill for formal Chinese `.docx` papers and reports that must look like a human-prepared Word document.

## Required Companion Skill

For any DOCX creation or edit, also use the built-in `documents` skill when available. Follow its render-and-verify workflow before delivery.

## Core Rule

Do not create a Word paper by ad-hoc run formatting. Build or apply a stable Word style system first, then insert content into named styles.

Preferred order:

1. If the user provides a `.docx` template, copy it and replace content without changing template styles.
2. If no template is provided, create styles explicitly before drafting.
3. Render the final DOCX to page images and inspect every page.
4. Run `scripts/docx_style_audit.py` on the final DOCX.
5. Fix every error, re-render, and re-run the audit before delivery.

## Formatting Standard

Before drafting, read `references/format_spec.md` and apply it as the document contract.

Non-negotiable defaults:

- Chinese font: SimSun.
- English font: Times New Roman.
- Body size: 12 pt.
- Body line spacing: 1.5.
- Body text: Simplified Chinese only.
- Headings: black, left aligned, no theme color, numbered as `1`, `1.1`, `1.1.1`.
- Tables: three-line table style, numbered `表1`, `表2`; bilingual captions above each table.
- Figures: clear source image, preferably JPG/TIFF at 300 dpi or better; numbered `图1`, `图2`; bilingual captions below each figure.
- Units: SI units, such as `mg/kg` and `mL`; avoid Chinese nonstandard unit forms such as `克/升`.
- Statistical symbols such as `t` and `P` must be italicized.
- References: GB/T 7714-2015 sequential numeric style.

## Style Discipline

Use styles for:

- Normal body paragraphs.
- Heading 1, Heading 2, Heading 3.
- Table captions.
- Figure captions.
- References.
- Table body and table header text.

Avoid direct formatting except for controlled exceptions:

- Italic statistical symbols.
- Scientific names or required technical terms.
- Caption labels if the template explicitly requires them.

Do not use:

- Built-in blue Word title or hyperlink styles for headings.
- Random bold runs in body paragraphs.
- Direct run-level font, size, color, or bold overrides for normal prose.
- Manually colored headings.
- Mixed Simplified and Traditional Chinese.
- Fake tables made from tabs or spaces.
- Fake lists made from repeated hyphens when a real ordered list is needed.

## QA Workflow

After generating or editing the DOCX:

1. Render with the `documents` skill renderer:

```bash
python render_docx.py final.docx --output_dir render_qa
```

2. Inspect every page PNG at normal zoom.
3. Run the style audit:

```bash
python scripts/docx_style_audit.py final.docx
```

4. Treat audit `ERROR` items as blocking.
5. Fix the DOCX, then repeat rendering and auditing.

If rendering is unavailable because LibreOffice is missing, still run the style audit and disclose that visual render QA could not be completed.

## Audit Script

Use `scripts/docx_style_audit.py` for deterministic checks. It inspects DOCX XML for:

- Traditional Chinese candidates.
- Blue, theme-colored, or non-black heading runs/styles.
- Direct bold/color/font/size overrides in body text.
- Heading numbering pattern issues.
- Table and figure caption ordering.
- Common non-SI Chinese unit expressions.
- Non-italic statistical `t` and `P` symbols.
- Sequential GB/T-style reference labels.

The script is a guardrail, not a substitute for visual QA. Passing it does not remove the requirement to render and inspect the pages.

## Delivery Rule

Do not deliver a DOCX until:

- The latest rendered pages look clean.
- `docx_style_audit.py` has no errors.
- Any remaining warnings are either fixed or explicitly explained.
