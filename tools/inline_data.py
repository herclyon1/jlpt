#!/usr/bin/env python3
"""Bake each trainer's question bank into its own HTML file.

The four trainers used to `fetch()` their JSON from ../export/. A browser
refuses that over file://, so double-clicking any of them produced a red box
saying "start a local server first" - a wall in front of the one activity that
decides whether N1 is passed. Audio is unaffected: <audio src="..."> does load
over file://, it is only fetch/XHR that is blocked.

So the data is written into the page as

    <script id="drill-data" type="application/json">[...]</script>

and the loader reads that element, falling back to fetch() when the block is
empty (which is what happens if this script has never been run). Re-run this
after regenerating anything in export/:

    python3 tools/inline_data.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAIRS = {
    "即時応答トレーナー.html": "drill_soku.json",
    "読解トレーナー.html": "drill_read.json",
    "診断.html": "drill_cloze.json",
    "診断_EN.html": "drill_cloze_en.json",
}

HELPER = ("\nconst load_=()=>{const el=document.getElementById('drill-data');"
          "return el&&el.textContent.trim()?Promise.resolve(JSON.parse(el.textContent))"
          ":fetch(typeof URL_!=='undefined'?URL_:DATA_URL).then(r=>r.json());};\n")
BLOCK = re.compile(r'<script id="drill-data" type="application/json">.*?</script>\n?', re.S)


def bake(html_name: str, json_name: str) -> str:
    page = ROOT / "tools" / html_name
    data = ROOT / "export" / json_name
    src = page.read_text(encoding="utf-8")
    items = json.loads(data.read_text(encoding="utf-8"))
    # '<' can only occur inside a JSON string, so escaping it wholesale is safe
    # and is what keeps a '</script>' in the question text from ending the block.
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    block = f'<script id="drill-data" type="application/json">{payload}</script>\n'

    src = BLOCK.sub("", src)
    if "const load_=" not in src:
        src = re.sub(r"(\n)(fetch\((?:URL_|DATA_URL)\))", HELPER + r"\2", src, count=1)
        src = re.sub(r"fetch\((?:URL_|DATA_URL)\)\.then\(r=>r\.json\(\)\)", "load_()", src)
    if "load_()" not in src:
        return f"✗ {html_name}: 没找到取数据那一行，没动它"
    src = src.replace("<script>", block + "<script>", 1)
    page.write_text(src, encoding="utf-8")
    return f"✓ {html_name}: 内嵌 {len(items)} 题（{len(payload)/1024:.0f} KB）"


if __name__ == "__main__":
    bad = 0
    for h, j in PAIRS.items():
        line = bake(h, j)
        bad += line.startswith("✗")
        print(line)
    sys.exit(1 if bad else 0)
