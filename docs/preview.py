"""
Regenerate docs/preview.html from docs/blog-synthetic-data-pipeline.md.

Run from the repo root:
    python3 docs/preview.py

Then serve and open:
    python3 -m http.server 8080
    # http://localhost:8080/docs/preview.html

preview.html is gitignored — re-run this script after editing the blog markdown.
"""

import markdown
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent
SRC = REPO_ROOT / "docs" / "blog-synthetic-data-pipeline.md"
OUT = REPO_ROOT / "docs" / "preview.html"

if not SRC.exists():
    sys.exit(f"Source not found: {SRC}")

src = SRC.read_text()

# Strip Jekyll frontmatter
src = re.sub(r"^---\n.*?\n---\n", "", src, flags=re.DOTALL)

html_body = markdown.markdown(
    src,
    extensions=["tables", "fenced_code", "nl2br"],
)

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Synthetic Data Pipeline — Blog Preview</title>
<style>
  body      {{ max-width:860px; margin:2rem auto; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; font-size:16px; line-height:1.6; color:#24292e; padding:0 1.5rem; }}
  h1,h2,h3  {{ border-bottom:1px solid #eaecef; padding-bottom:.3em; margin-top:2em; }}
  h1        {{ font-size:1.8em; }}
  pre        {{ background:#f6f8fa; border-radius:6px; padding:1em; overflow-x:auto; }}
  code       {{ background:#f6f8fa; border-radius:3px; padding:.1em .3em; font-size:87%; }}
  pre code   {{ background:none; padding:0; font-size:inherit; }}
  blockquote {{ border-left:4px solid #dfe2e5; margin:0; padding:0 1em; color:#6a737d; }}
  table      {{ border-collapse:collapse; width:100%; margin:1em 0; }}
  th, td     {{ border:1px solid #dfe2e5; padding:.5em 1em; text-align:left; }}
  th         {{ background:#f6f8fa; font-weight:600; }}
  img        {{ max-width:100%; height:auto; display:block; margin:1.5em auto; border:1px solid #eaecef; border-radius:4px; }}
  em         {{ color:#6a737d; font-size:90%; display:block; text-align:center; margin-top:-.5em; margin-bottom:1.5em; }}
  hr         {{ border:none; border-top:1px solid #eaecef; margin:2em 0; }}
  p          {{ margin:.8em 0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""

OUT.write_text(page)
print(f"Written: {OUT}")
print(f"Serve:   python3 -m http.server 8080")
print(f"Open:    http://localhost:8080/docs/preview.html")
