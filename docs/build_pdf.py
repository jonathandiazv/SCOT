"""
Génère docs/ARCHITECTURE.pdf à partir de docs/ARCHITECTURE.md.

Le bloc Mermaid est remplacé par le schéma docs/architecture.svg (plus détaillé),
puis la page HTML est imprimée en PDF avec Microsoft Edge en mode headless.

Usage :  .venv\\Scripts\\python docs\\build_pdf.py
Prérequis : pip install markdown ; Microsoft Edge installé.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #16202b; }
h1 { font-size: 21pt; margin: 0 0 4pt; color: #0f2a4d; }
h1 + p { color: #566475; font-size: 9pt; margin-top: 0; }
h2 { font-size: 14pt; color: #0f2a4d; border-bottom: 1.5pt solid #1f6feb; padding-bottom: 3pt; margin-top: 18pt; break-after: avoid; }
h3 { font-size: 11.5pt; color: #0f2a4d; margin-top: 12pt; break-after: avoid; }
p, li { max-width: 100%; }
code { font-family: Consolas, monospace; font-size: 8.6pt; background: #eef3fb; padding: 0 2pt; border-radius: 2pt; }
pre { background: #f4f6f9; border: 0.75pt solid #c9d3de; border-radius: 3pt; padding: 6pt 8pt; font-size: 8pt; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.6pt; break-inside: auto; }
tr { break-inside: avoid; }
th { background: #eef3fb; color: #0f2a4d; text-align: left; font-weight: 600; }
th, td { border: 0.75pt solid #c9d3de; padding: 3pt 5pt; vertical-align: top; }
td code { white-space: normal; word-break: normal; overflow-wrap: normal; }
td:first-child code { white-space: nowrap; }
.schema { margin: 8pt 0 4pt; break-inside: avoid; }
.schema svg { width: 100%; height: auto; }
.caption { font-size: 8.5pt; color: #566475; margin-bottom: 8pt; }
"""


def main() -> None:
    md_text = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
    svg = (DOCS / "architecture.svg").read_text(encoding="utf-8")

    placeholder = "SCHEMA_SVG_PLACEHOLDER"
    md_text = re.sub(r"```mermaid.*?```", placeholder, md_text, flags=re.S)
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    body = body.replace(
        f"<p>{placeholder}</p>",
        f'<div class="schema">{svg}</div><div class="caption">Flux numérotés de 1 à 8 '
        "(chaîne d'inférence) et A–B (entraînement local et mise en production du modèle). "
        "Ligne pointillée : envoi des logs vers Application Insights.</div>",
    )
    html = f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Architecture SCOT</title><style>{CSS}</style></head><body>{body}</body></html>'

    edge = next((p for p in EDGE_PATHS if Path(p).exists()), None)
    if not edge:
        sys.exit("Microsoft Edge introuvable.")

    out = DOCS / "ARCHITECTURE.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "architecture.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={Path(tmp) / 'edge'}", f"--print-to-pdf={out}", page.as_uri()],
            check=True, timeout=120,
        )
    print(f"✓ {out} ({out.stat().st_size / 1024:.0f} Ko)")


if __name__ == "__main__":
    main()
