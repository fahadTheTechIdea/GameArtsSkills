#!/usr/bin/env python3
"""Single owner of the local page server that Game Arts pages run on (the approval form, the settings wizard): a page the owner uses in their own browser
while an agent waits for the result. It is a library, not a command.

The server listens on this computer only (127.0.0.1, a port the system picks) and answers only at a secret address (`/a/<token>/`) that is never printed
unless asked for. Every request is checked: the Host header must be one of this computer's own names (a page on another site cannot reach it through a name that
points here), the Origin of a POST must be this page, a body must be JSON and small, and the page itself is served with a content policy that allows only its
own nonce'd script and style, so text a request carries is data and never runs. A page supplies its template, its GET routes and its POST routes by
subclassing LocalSession; nothing else about the server is its business.
"""
import http.server
import json
import secrets
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

MAX_BODY_BYTES = 256 * 1024
BASE_CSS = Path(__file__).with_name("gamearts_page.css")


def require_installed(template):
    """The page and the stylesheet they share must be beside this script; a game updated by an older updater has the scripts but not these files."""
    missing = [path.name for path in (Path(template), BASE_CSS) if not path.is_file()]
    if missing:
        raise ValueError(f"{', '.join(missing)} is not installed beside the Game Arts scripts: update Game Arts with its current updater (sync_local_agents.py), which copies it")


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "GameArtsLocalPage"
    protocol_version = "HTTP/1.0"

    def log_message(self, *_):  # the agent reads the result, not an access log
        pass

    def _send(self, status, body=b"", content_type="text/plain; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, value):
        self._send(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

    def _route(self):
        """The parts of the path after the secret, or None once the request was answered (wrong host, wrong secret, anything else)."""
        session = self.server.session
        if self.headers.get("Host") not in session.hosts:  # a page on another site reaching this one through a name that points at this computer
            self._send(421, b"Misdirected request")
            return None
        parts = urlparse(self.path).path.split("/")
        if len(parts) < 3 or parts[1] != "a" or not secrets.compare_digest(parts[2].encode("utf-8"), session.token.encode("utf-8")):
            self._send(404, b"Not found")
            return None
        return parts[3:]

    def do_GET(self):
        rest = self._route()
        if rest is None:
            return
        session = self.server.session
        if rest in ([], [""]):
            nonce = secrets.token_urlsafe(16)
            policy = ("default-src 'none'; script-src 'nonce-%s'; style-src 'nonce-%s'; img-src 'self'; connect-src 'self'; "
                      "form-action 'none'; base-uri 'none'; frame-ancestors 'none'" % (nonce, nonce))
            page = session.template.read_text(encoding="utf-8").replace("{{base_css}}", BASE_CSS.read_text(encoding="utf-8")).replace("{{nonce}}", nonce)
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8", {"Content-Security-Policy": policy})
            return
        found = session.get(rest)
        if found is None:
            self._send(404, b"Not found")
        else:
            self._send(*found)

    def do_POST(self):
        rest = self._route()
        session = self.server.session
        if rest is None:
            return
        if len(rest) != 1 or rest[0] not in session.post_routes:
            self._send(404, b"Not found")
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin not in session.origins:
            self._json(403, {"error": "This did not come from the page."})
            return
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "It must be sent as JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._json(411, {"error": "It has no length."})
            return
        if not 0 < length <= MAX_BODY_BYTES:
            self.rfile.read(min(max(length, 0), 4 * MAX_BODY_BYTES))  # taken and dropped, so the sender is not cut off mid-send
            self._json(413, {"error": "It is too large."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._json(400, {"error": "It could not be read."})
            return
        status, body = session.post(rest[0], payload)
        self._json(status, body)


def show(session, timeout, print_link=False, opener=None, echo=None):
    """Serve the page, open the owner's browser on it and wait up to `timeout` seconds for the owner's result; True when it came. Raises when no page could
    be shown, so a silence is never mistaken for an answer. The server is always closed."""
    echo = echo or (lambda text: print(text, file=sys.stderr))
    opener = opener or webbrowser.open  # resolved here so a test can replace it and never open a real browser
    session.start()
    try:
        if print_link:
            echo(f"Open this link on this computer: {session.link}")
        if not opener(session.link) and not print_link:
            raise ValueError("No browser could be opened on this computer to show the page. Ask the owner in the conversation as usual, or run this again "
                             "with --print-link if the owner can reach this computer's localhost (a forwarded port).")
        return session.wait(timeout)
    finally:
        session.close()


class LocalSession:
    """A page being shown: the server, its secret address, and the owner's one result. A page subclasses this with its `template` (a file with `{{nonce}}` in
    its script and style tags), its `post_routes`, `get(rest)` for any GET beyond the page itself (None, or (status, body, content type)) and
    `post(name, payload)` (a (status, JSON body))."""

    template = None
    post_routes = ()

    def __init__(self, root):
        self.root = root
        self.token = secrets.token_urlsafe(24)
        self.finished = threading.Event()
        self.lock = threading.Lock()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.session = self
        self.port = self.server.server_address[1]
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.origins = {f"http://{host}" for host in self.hosts}
        self._thread = None

    @property
    def link(self):
        return f"http://127.0.0.1:{self.port}/a/{self.token}/"

    def start(self):
        self._thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self._thread.start()

    def wait(self, seconds):
        return self.finished.wait(seconds)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        if self._thread:
            self._thread.join(5)

    def get(self, rest):
        return None

    def post(self, name, payload):
        return 404, {"error": "Not found"}
