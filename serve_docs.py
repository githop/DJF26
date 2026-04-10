#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# ///
"""
Web server to serve the built GitHub Pages site locally.
It builds the site first, then serves the docs/ directory at the /DJF26/ path,
exactly as it would appear on GitHub Pages.

Usage:
    uv run serve_docs.py
"""

import http.server
import socketserver
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DOCS_DIR = REPO_ROOT / "docs"
PORT = 8000


class GHPHanlder(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def do_GET(self):
        # GitHub Pages serves the repo docs/ folder at /DJF26/
        if self.path == "/" or self.path == "/DJF26":
            self.send_response(301)
            self.send_header("Location", "/DJF26/")
            self.end_headers()
            return

        if self.path.startswith("/DJF26/"):
            # Strip the /DJF26 prefix so SimpleHTTPRequestHandler finds it in docs/
            self.path = self.path[6:]

        super().do_GET()


if __name__ == "__main__":
    print("Generating sheets and agendas...")
    dates = ["4/7", "4/8", "4/9", "4/10", "4/11", "4/12"]
    for date in dates:
        subprocess.run(["uv", "run", "db/generate_all.py", date])

    print("Building site...")
    # Run the build script before serving
    subprocess.run(["uv", "run", "db/build_site.py"], check=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), GHPHanlder) as httpd:
        print(f"\n✓ Serving DJF26 docs at http://127.0.0.1:{PORT}/DJF26/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
