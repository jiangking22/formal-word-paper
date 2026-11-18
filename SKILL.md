---
name: formal-word-paper
description: Create, edit, and review formal Chinese Word papers and reports, including course reports, journal manuscripts, and theses. Apply the target template, format figures and tables, check GB/T 7714 references, and verify the resulting DOCX.
---

# Formal Word Paper

Use this skill to create, edit, or review the formatting of a formal Chinese `.docx`.

## Select the Format

- Identify the document type and read the user's assignment instructions, institution or journal requirements, and supplied template. Apply the requirements for that submission. Preserve template styles when filling a supplied DOCX.
- Read [the format reference](references/format_spec.md) before drafting or auditing. It distinguishes general conventions from fallback Word settings and gives separate checks for course reports, journal manuscripts, and theses.
- Use GB/T 7714-2025 for references by default. Use the edition and citation system specified for the submission when provided. Check reference entries and their citations using the format reference.
- Use the `documents` companion skill when available for DOCX creation or editing. For a read-only review, compare the provided material with the applicable requirements and report the findings.

## Build the Document

Define or reuse named paragraph styles for body text, heading levels, table and figure captions, table text, and references. For a new document, set these styles before inserting the content. Use an outline level on custom headings when needed for an automatic table of contents.

Use consistent formatting through the styles. Keep intentional emphasis and character formatting for technical notation, scientific names, and template-mandated labels. Enter tables as real Word tables and use Word numbering or fields when appropriate.

In a new document, prefer custom heading styles and explicit font mappings. If unexpected color, size, weight, or spacing appears, check the effective style and OOXML overrides. Theme fonts, mismatched `w:sz` and `w:szCs`, `w:bCs`, `w:kern`, and `w:spacing` can account for these differences. Preserve properties required by the supplied template.

## Verify the DOCX

Render and inspect all pages after the last edit. Check typography, page breaks, figure and table captions, numbering, and any required cover, contents, and front matter against the chosen format.

```bash
python render_docx.py final.docx --output_dir render_qa
python scripts/docx_style_audit.py final.docx
```

The audit detects common DOCX style problems and checks detected sequences, including `[n]` reference labels. Review findings against the target template and the rendered document. Correct confirmed errors and explain any template-authorized exceptions or remaining warnings. Verify the actual reference fields, source-language titles, and correspondence between citations and entries separately.

After correcting a finding, re-render and re-run the audit. If rendering is unavailable, run the audit and disclose the missing visual review.
