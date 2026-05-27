"""
photo_server.py – mini server pro otevirani souboru a kopirovani z dashboardu
Spust: python photo_server.py
"""
import os, sys, json, shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/open":
            params = parse_qs(parsed.query)
            path   = unquote(params.get("path", [""])[0])
            self._cors()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            if path and os.path.exists(path):
                os.startfile(path)
                self.wfile.write(b"OK")
                print(f"[OPEN] {path}")
            else:
                self.wfile.write(b"NOT FOUND")
                print(f"[ERR]  Soubor nenalezen: {path}")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/copy":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            paths  = body.get("paths", [])
            dest   = body.get("dest", "")

            result = {"copied": 0, "total": len(paths), "errors": []}

            if not dest:
                result["errors"].append("Cilova slozka neni zadana")
            else:
                dest_path = Path(dest)
                try:
                    dest_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    result["errors"].append(f"Nelze vytvorit slozku: {e}")

                for p in paths:
                    src = Path(p)
                    if not src.exists():
                        result["errors"].append(f"Nenalezeno: {src.name}")
                        continue
                    try:
                        shutil.copy2(src, dest_path / src.name)
                        # Zkopiruj i XMP sidecar pokud existuje
                        xmp = src.with_suffix(".xmp")
                        if xmp.exists():
                            shutil.copy2(xmp, dest_path / xmp.name)
                        result["copied"] += 1
                        print(f"[COPY] {src.name} -> {dest_path}")
                    except Exception as e:
                        result["errors"].append(f"{src.name}: {e}")

            print(f"[COPY] Hotovo: {result['copied']}/{result['total']}")

            self._cors()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self._cors()
        self.send_response(200)
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    port   = 8765
    server = HTTPServer(("localhost", port), Handler)
    print(f"[SERVER] Bezim na http://localhost:{port}")
    print(f"         Klikni na fotku v dashboardu pro otevreni")
    print(f"         Zaskrikovaci: 'Kopirovat vybrane' zkopiruje soubory")
    print(f"         Ctrl+C pro ukonceni")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Ukonceno")
