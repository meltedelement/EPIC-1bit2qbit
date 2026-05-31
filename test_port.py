from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Hello from port 1212!\n")

    def log_message(self, format, *args):
        print(f"[{self.client_address[0]}] {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 1212), Handler)
    print("Listening on port 1212 — press Ctrl+C to stop")
    server.serve_forever()
