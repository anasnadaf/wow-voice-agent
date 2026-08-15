"""Export the live system prompt as the submission deliverables.

The prompt is not maintained as a document — it is assembled from the same
modules the running agent uses, so what a reviewer reads is exactly what
configures the bot. This writes docs/system-prompt.md and renders
deliverables/system-prompt.pdf from it.

    uv run python -m scripts.export_prompt
"""

import re
from datetime import date
from pathlib import Path

from app.prompts import full_system_prompt

REPO = Path(__file__).resolve().parents[2]
MD_PATH = REPO / "docs" / "system-prompt.md"
PDF_PATH = REPO / "deliverables" / "system-prompt.pdf"

PDF_CSS = """
@page { size: A4; margin: 20mm 18mm; @bottom-center {
    content: counter(page) " / " counter(pages); font-size: 9pt; color: #888; } }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
       font-size: 10.5pt; line-height: 1.5; color: #1a1a1a; }
h1 { font-size: 19pt; border-bottom: 2px solid #b08d57; padding-bottom: 6pt;
     margin-bottom: 4pt; }
h2 { font-size: 13pt; color: #6b5426; margin-top: 16pt; page-break-after: avoid; }
h3 { font-size: 11pt; margin-top: 12pt; page-break-after: avoid; }
code { font-family: "SF Mono", Menlo, monospace; font-size: 9.5pt;
       background: #f4f1ea; padding: 1pt 3pt; border-radius: 2pt; }
pre { background: #f4f1ea; padding: 8pt; border-radius: 3pt; font-size: 9pt;
      white-space: pre-wrap; page-break-inside: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 8pt 0; }
th, td { border: 1px solid #ddd; padding: 4pt 6pt; text-align: left; }
th { background: #f4f1ea; }
li { margin-bottom: 3pt; }
li p { margin: 0; }  /* even spacing whether or not an item wraps */
.subtitle { color: #666; font-size: 10pt; margin-top: 0; }
"""

HEADER = """*Divyasree Developers — "Whispers of the Wind", Nandi Valley, North Bengaluru*

*Outbound lead-qualification voice agent · generated from the running configuration on {today}*

"""

_LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")


def _space_lists(text: str) -> str:
    """Insert the blank line Markdown needs before a list that follows prose.

    The prompt packs bullets directly under their lead-in sentence, which reads
    fine to the model but renders as one run-on paragraph. Presentation only —
    the prompt itself is untouched.
    """
    out: list[str] = []
    in_list = False
    for line in text.split("\n"):
        is_item = bool(_LIST_ITEM.match(line))
        # an indented line under a list is that item's wrapped continuation
        continues_item = in_list and line.startswith((" ", "\t")) and line.strip()
        prev = out[-1] if out else ""

        if is_item and prev.strip() and not in_list:
            out.append("")
        elif in_list and line.strip() and not is_item and not continues_item:
            out.append("")  # prose resuming after the list needs its own block

        out.append(line)
        if is_item or continues_item:
            in_list = True
        elif line.strip():
            in_list = False
    return "\n".join(out)


def main() -> None:
    # Imported here, not at module scope: WeasyPrint needs native pango/glib
    # libraries, and everything above this line is worth importing without them.
    import markdown
    from weasyprint import CSS, HTML

    prompt = full_system_prompt()
    title, _, body = prompt.partition("\n")
    header = HEADER.format(today=date.today().isoformat())
    document = f"{title}\n\n{header}{_space_lists(body.lstrip())}"

    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text(document)

    html = markdown.markdown(document, extensions=["tables", "fenced_code", "sane_lists"])
    html = html.replace("<p><em>Divyasree", '<p class="subtitle"><em>Divyasree')
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(PDF_PATH, stylesheets=[CSS(string=PDF_CSS)])

    print(f"wrote {MD_PATH.relative_to(REPO)} ({len(document):,} chars)")
    print(f"wrote {PDF_PATH.relative_to(REPO)} ({PDF_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
