#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "markdown",
# ]
# ///
"""
Web server to serve generated driver sheets and daily agendas as HTML.

Usage:
    uv run serve_docs.py
"""

import http.server
import socketserver
import urllib.parse
from pathlib import Path
import markdown

REPO_ROOT = Path(__file__).resolve().parent
SHEET_DIR = REPO_ROOT / "driver-sheets"
AGENDA_DIR = REPO_ROOT / "daily-agendas"

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: sans-serif; max-width: 1200px; margin: 2em auto; line-height: 1.5; padding: 0 16px; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.2em; }}
  h3 {{ font-size: 1.05em; }}
  hr {{ border: none; border-top: 1px solid #ccc; margin: 24px 0; }}
  a {{ color: #1a73e8; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1em; font-size: 0.85em; }}
  th, td {{ border: 1px solid #ddd; padding: 4px 6px; text-align: left; }}
  th {{ background-color: #f5f5f5; }}
  .nav {{ margin-bottom: 24px; font-size: 14px; border-bottom: 1px solid #eee; padding-bottom: 12px; }}
  .file-list {{ list-style: none; padding: 0; }}
  .file-list li {{ margin-bottom: 8px; }}
  .meta {{ background: #f5f5f5; border: 1px solid #ddd; padding: 12px 16px; border-radius: 6px; margin-bottom: 24px; font-size: 14px; }}
</style>
</head>
<body>
{nav}
{body}
</body>
</html>
"""

NAV_HTML = """
<div class="nav">
  <a href="/">← Home</a>
</div>
"""


def md_to_html(md_text: str) -> str:
    # Use sane_lists for standard list behavior and tables to render markdown tables
    return markdown.markdown(md_text, extensions=["sane_lists", "tables"])


def render_page(title: str, body: str, show_nav: bool = True) -> bytes:
    nav = NAV_HTML if show_nav else ""
    html = HTML_TEMPLATE.format(title=title, nav=nav, body=body)
    return html.encode("utf-8")


class DocsHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.serve_index()
        elif path.startswith("/agenda/"):
            filename = urllib.parse.unquote(path[len("/agenda/") :])
            self.serve_file(AGENDA_DIR / filename)
        elif path.startswith("/sheet/"):
            filename = urllib.parse.unquote(path[len("/sheet/") :])
            self.serve_file(SHEET_DIR / filename)
        else:
            self.send_error(404, "Not Found")

    def serve_index(self):
        agendas = sorted(AGENDA_DIR.glob("*.md")) if AGENDA_DIR.exists() else []
        sheets = sorted(SHEET_DIR.glob("*.md")) if SHEET_DIR.exists() else []

        body = "<h1>DJF26 Documents</h1>\n"

        body += "<h2>Daily Agendas</h2>\n"
        if agendas:
            body += "<ul class='file-list'>\n"
            for agenda in agendas:
                body += f"<li><a href='/agenda/{urllib.parse.quote(agenda.name)}'>{agenda.stem}</a></li>\n"
            body += "</ul>\n"
        else:
            body += "<p>No agendas found.</p>\n"

        body += "<h2>Driver Sheets</h2>\n"
        if sheets:
            body += "<ul class='file-list'>\n"
            for sheet in sheets:
                body += f"<li><a href='/sheet/{urllib.parse.quote(sheet.name)}'>{sheet.stem}</a></li>\n"
            body += "</ul>\n"
        else:
            body += "<p>No driver sheets found.</p>\n"

        html_bytes = render_page("DJF26 Docs", body, show_nav=False)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.end_headers()
        self.wfile.write(html_bytes)

    def serve_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File Not Found")
            return

        try:
            md_content = file_path.read_text(encoding="utf-8")
            html_content = md_to_html(md_content)
            html_bytes = render_page(file_path.stem, html_content)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)
        except Exception as e:
            self.send_error(500, f"Error rendering page: {e}")


if __name__ == "__main__":
    PORT = 8000
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DocsHandler) as httpd:
        print(f"Serving DJF26 docs at http://127.0.0.1:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
