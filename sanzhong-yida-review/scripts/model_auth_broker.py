"""Local host-only Codex credential broker for a single isolated role.

Workers receive a random scoped bearer for a custom Responses provider, never a
copy of the user's auth.json or OAuth tokens. This is a narrow HTTP capability,
not an OS sandbox: the executor must separately prevent direct external access
and must keep the original user auth path outside the worker filesystem.
"""
from __future__ import annotations

import copy
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

UPSTREAM_BASE = "https://chatgpt.com/backend-api/codex"
_AUTO_PROXY = object()
_PREFIXES = ("", "/v1", "/codex", "/backend-api/codex")
_LOCAL_FUNCTIONS = frozenset(("read_file", "list_directory", "run_command", "write_file"))
_SAFE_FAILURE_CODE = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")


class AuthBrokerError(ValueError):
    """A broker configuration violates the host credential boundary."""

    def __init__(self, message, *, failure_event=None, failure_code=None, usage=None):
        super().__init__(message)
        self.failure_event = failure_event
        self.failure_code = failure_code
        self.usage = copy.deepcopy(usage) if usage is not None else {}


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _reject_json_constant(value):
    raise ValueError("nonstandard JSON constant")


def _has_continuation(value):
    # Preserve normal message/reasoning IDs and tool-loop input. The backend
    # request must not refer to another server-side response or conversation.
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("previous_response_id", "conversation") and child not in (None, "", {}):
                return True
            if _has_continuation(child):
                return True
    elif isinstance(value, list):
        return any(_has_continuation(child) for child in value)
    return False


def _inline_image(value):
    if isinstance(value, dict):
        value = value.get("url")
    return isinstance(value, str) and any(value.startswith(f"data:image/{kind};base64,")
                                         for kind in ("png", "jpeg", "webp", "gif"))


def _has_remote_content(value):
    if isinstance(value, dict):
        if value.get("type") in ("input_file", "item_reference"):
            return True
        if value.get("type") in ("input_image", "image_url", "image"):
            if not _inline_image(value.get("image_url", value.get("url"))):
                return True
        for key, child in value.items():
            if key in ("file_id", "file_url") and child not in (None, ""):
                return True
            if key == "image_url" and not _inline_image(child):
                return True
            if _has_remote_content(child):
                return True
    elif isinstance(value, list):
        return any(_has_remote_content(child) for child in value)
    return False


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        # Never let server traceback logging emit request/credential details.
        pass


class CodexAuthBroker:
    """One localhost broker and one random model capability per role execution.

    Trusted-host API only. `proxy=None` disables proxy discovery (useful for
    MockTransport tests); omitted proxy uses HTTPS_PROXY or ALL_PROXY. A socks
    proxy requires httpx's optional socksio dependency in the host environment.
    No credential, request body, response body, or client-supplied header value
    is recorded in the public audit. Close in a finally block or use `with`.
    """

    def __init__(self, auth_data, *, proxy=_AUTO_PROXY, upstream_transport=None,
                 max_body_bytes=32 * 1024 * 1024, serve_http=True):
        if not isinstance(auth_data, dict) or not isinstance(auth_data.get("tokens"), dict):
            raise AuthBrokerError("host ChatGPT token record required")
        tokens = auth_data["tokens"]
        if not _nonempty(tokens.get("access_token")):
            raise AuthBrokerError("host access token required")
        account = tokens.get("account_id")
        if account is not None and not _nonempty(account):
            raise AuthBrokerError("invalid host account identity")
        if not isinstance(max_body_bytes, int) or isinstance(max_body_bytes, bool) or max_body_bytes <= 0:
            raise AuthBrokerError("positive request size bound required")
        # The user id_token and refresh_token are never copied into this object.
        self._access_token = tokens["access_token"]
        self._account_id = account
        self._scoped_token = secrets.token_urlsafe(48)
        self._max_body_bytes = max_body_bytes
        if not isinstance(serve_http, bool):
            raise AuthBrokerError("serve_http must be a boolean")
        self._serve_http = serve_http
        self._audit = []
        self._execution_requests = 0
        self._state_lock = threading.RLock()
        self._server = None
        self._thread = None
        self._closed = False
        if proxy is _AUTO_PROXY:
            proxy = next((os.environ[name] for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")
                          if os.environ.get(name)), None)
        try:
            self._client = httpx.Client(proxy=proxy, transport=upstream_transport,
                                        timeout=120.0, follow_redirects=False, trust_env=False)
        except Exception:
            # Proxy errors can contain configured proxy credentials; sanitize.
            self._access_token = ""
            self._account_id = None
            raise AuthBrokerError("host upstream HTTP client unavailable; verify proxy dependencies") from None

    @classmethod
    def from_auth_path(cls, auth_path, **options):
        """Read the original auth path in the trusted host, without copying it."""
        try:
            with Path(auth_path).open("r", encoding="utf-8") as stream:
                auth_data = json.load(stream)
        except Exception:
            raise AuthBrokerError("host auth record could not be read") from None
        return cls(auth_data, **options)

    @property
    def scoped_token(self):
        return self._scoped_token

    @property
    def proxy_token(self):
        return self._scoped_token

    @property
    def base_url(self):
        if self._server is None or self._closed:
            raise AuthBrokerError("broker is not running")
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    @property
    def audit(self):
        with self._state_lock:
            return copy.deepcopy(self._audit)

    @property
    def execution_requests(self):
        with self._state_lock:
            return self._execution_requests

    def start(self):
        with self._state_lock:
            if self._closed:
                raise AuthBrokerError("closed broker cannot be restarted")
            if self._server is not None:
                return self
            broker = self

            class Handler(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"
                timeout = 15.0

                def log_message(self, format, *args):
                    pass

                def do_GET(self):
                    broker._handle(self)

                do_POST = do_GET
                do_PUT = do_GET
                do_DELETE = do_GET
                do_PATCH = do_GET
                do_HEAD = do_GET
                do_OPTIONS = do_GET
                do_CONNECT = do_GET
                do_TRACE = do_GET

            self._server = _QuietServer(("127.0.0.1", 0), Handler)
            self._thread = threading.Thread(target=self._server.serve_forever,
                                            kwargs={"poll_interval": 0.05}, daemon=True,
                                            name="codex-role-auth-broker")
            self._thread.start()
            return self

    def close(self):
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            server, thread = self._server, self._thread
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)
        self._client.close()
        self._access_token = ""
        self._account_id = None

    def __enter__(self):
        return self.start() if self._serve_http else self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _outbound_headers(self):
        headers = {"Authorization": "Bearer " + self._access_token,
                   "Accept": "text/event-stream, application/json", "originator": "codex_cli_rs",
                   "Content-Type": "application/json"}
        if self._account_id is not None:
            headers["ChatGPT-Account-Id"] = self._account_id
        return headers

    def _validate_host_payload(self, payload):
        if not isinstance(payload, dict) or not _nonempty(payload.get("model")):
            raise AuthBrokerError("host Responses model request required")
        if _has_continuation(payload) or payload.get("background") not in (None, False):
            raise AuthBrokerError("server-side response/conversation continuation and background execution are forbidden")
        if _has_remote_content(payload):
            raise AuthBrokerError("remote files and image URLs are forbidden; use approved inline content")
        tools = payload.get("tools", [])
        if not isinstance(tools, list):
            raise AuthBrokerError("function tools must be an array")
        for tool in tools:
            if not isinstance(tool, dict) or tool.get("type") != "function" or not _nonempty(tool.get("name")) or tool["name"] not in _LOCAL_FUNCTIONS:
                raise AuthBrokerError("only approved worker-executed function tools are permitted")

    def _validate_output_item(self, item):
        if not isinstance(item, dict) or item.get("type") not in ("message", "reasoning", "function_call"):
            raise AuthBrokerError("model returned an unsupported hosted tool result")
        if item.get("type") == "function_call" and (not _nonempty(item.get("name")) or item["name"] not in _LOCAL_FUNCTIONS):
            raise AuthBrokerError("model returned an unapproved worker function")

    def _failure_details(self, event):
        response = event.get("response")
        response = response if isinstance(response, dict) else {}
        incomplete = response.get("incomplete_details")
        incomplete = incomplete if isinstance(incomplete, dict) else {}
        response_error, event_error = response.get("error"), event.get("error")
        response_error = response_error if isinstance(response_error, dict) else {}
        event_error = event_error if isinstance(event_error, dict) else {}
        code = "unspecified"
        for candidate in (incomplete.get("reason"), response_error.get("code"), event_error.get("code"), event.get("code")):
            if isinstance(candidate, str) and _SAFE_FAILURE_CODE.fullmatch(candidate):
                if not any(secret and secret in candidate for secret in (self._access_token, self._scoped_token, self._account_id)):
                    code = candidate
                    break
        raw_usage = response.get("usage", event.get("usage"))
        raw_usage = raw_usage if isinstance(raw_usage, dict) else {}
        def number(value):
            return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 10**18
        usage = {key: raw_usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")
                 if number(raw_usage.get(key))}
        for name, keys in (("input_tokens_details", ("cached_tokens",)),
                           ("output_tokens_details", ("reasoning_tokens",))):
            nested = raw_usage.get(name)
            if isinstance(nested, dict):
                allowed = {key: nested[key] for key in keys if number(nested.get(key))}
                if allowed:
                    usage[name] = allowed
        return code, usage

    def _event_completion(self, text, done_items):
        if text == "[DONE]":
            return None
        try:
            event = json.loads(text, parse_constant=_reject_json_constant)
        except Exception:
            raise AuthBrokerError("invalid model event stream") from None
        if not isinstance(event, dict):
            raise AuthBrokerError("invalid model event object")
        if event.get("type") in ("error", "response.failed", "response.incomplete"):
            kind = event["type"]
            code, usage = self._failure_details(event)
            raise AuthBrokerError(f"model response did not complete: {kind} / {code}",
                                  failure_event=kind, failure_code=code, usage=usage)
        if event.get("type") == "response.output_item.done":
            index, item = event.get("output_index"), event.get("item")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                raise AuthBrokerError("invalid model output item index")
            self._validate_output_item(item)
            if index in done_items and done_items[index] != item:
                raise AuthBrokerError("conflicting model output item index")
            done_items[index] = item
            return None
        if event.get("type") != "response.completed":
            return None
        response = event.get("response")
        if not isinstance(response, dict) or response.get("status") != "completed":
            raise AuthBrokerError("model response completion is malformed or incomplete")
        if response.get("output") in (None, []) and done_items:
            indexes = sorted(done_items)
            if indexes != list(range(len(indexes))):
                raise AuthBrokerError("model output items have missing indexes")
            # Codex may omit completed.output but send the full canonical
            # items in output_item.done. Preserve every original item field;
            # never synthesize items from deltas or partial added events.
            response = copy.deepcopy(response)
            response["output"] = [done_items[index] for index in indexes]
        if not isinstance(response.get("output"), list):
            raise AuthBrokerError("model response completion is malformed or incomplete")
        for item in response["output"]:
            self._validate_output_item(item)
        return response

    def respond(self, payload):
        """Trusted-host pure remote inference; never execute a returned tool.

        Suitable for a network-disabled worker's local JSONL RPC. Run with
        `serve_http=False` to avoid creating a listening socket. Only declared
        local function tools are allowed; the executor owns their filesystem,
        command scope, and output validation. Each request is self-contained.
        """
        with self._state_lock:
            if self._closed:
                raise AuthBrokerError("closed broker cannot accept inference")
        status, safe_headers, failure = 502, {}, {}
        try:
            self._validate_host_payload(payload)
            outbound = copy.deepcopy(payload)
            outbound.update(stream=True, store=False)
            body = json.dumps(outbound, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(body) > self._max_body_bytes:
                raise AuthBrokerError("model request exceeds permitted size")
            headers = self._outbound_headers()
            safe_headers = self._safe_headers(headers)
            with self._state_lock:
                self._execution_requests += 1
            with self._client.stream("POST", UPSTREAM_BASE + "/responses", headers=headers, content=body) as upstream:
                if upstream.status_code >= 300:
                    raise AuthBrokerError("model upstream rejected or redirected the request")
                data_lines, done_items = [], {}
                for line in upstream.iter_lines():
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip(" "))
                        if sum(len(part) for part in data_lines) > self._max_body_bytes:
                            raise AuthBrokerError("model event exceeds permitted size")
                    elif not line and data_lines:
                        completed = self._event_completion("\n".join(data_lines), done_items)
                        data_lines.clear()
                        if completed is not None:
                            status = 200
                            return completed
                if data_lines:
                    completed = self._event_completion("\n".join(data_lines), done_items)
                    if completed is not None:
                        status = 200
                        return completed
                raise AuthBrokerError("model stream ended without a completed response")
        except AuthBrokerError as exc:
            if exc.failure_event is not None:
                failure = {"failure_event": exc.failure_event, "failure_code": exc.failure_code,
                           "usage": copy.deepcopy(exc.usage)}
            raise
        except Exception:
            raise AuthBrokerError("model inference unavailable or malformed") from None
        finally:
            with self._state_lock:
                self._audit.append({"method": "POST", "endpoint": "/responses", "status": status,
                                    "headers": safe_headers, "execution_requests": self._execution_requests,
                                    "transport": "trusted_host_inference", **failure})

    def _route(self, method, path):
        try:
            parsed = urlsplit(path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                return None
            endpoint = next((e for e in ("/models", "/responses")
                             if any(parsed.path == prefix + e for prefix in _PREFIXES)), None)
            if (method, endpoint) not in (("GET", "/models"), ("POST", "/responses")):
                return None
            query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
            if query and (endpoint != "/models" or len(query) != 1 or query[0][0] != "client_version"
                          or not query[0][1] or len(query[0][1]) > 128):
                return None
            return endpoint, ("?" + urlencode(query) if query else "")
        except ValueError:
            return None

    def _safe_headers(self, headers):
        # Only fixed semantic header values enter audit; all credentials and
        # caller-controlled values are omitted or explicitly redacted.
        result = {"Authorization": "[redacted]"}
        if "ChatGPT-Account-Id" in headers:
            result["ChatGPT-Account-Id"] = "[redacted]"
        if "Content-Type" in headers:
            result["Content-Type"] = "application/json"
        if "Accept" in headers:
            result["Accept"] = "text/event-stream, application/json"
        result["forwarded_header_names"] = sorted(headers)
        return result

    def _error(self, handler, status, message):
        # Drain only a small, bounded rejected body so closing the socket does
        # not reset an already-written error response on Windows. Do not wait
        # for arbitrarily large/unfinished unauthenticated requests.
        if not getattr(handler, "_body_consumed", False):
            try:
                lengths = handler.headers.get_all("Content-Length", [])
                length = int(lengths[0]) if len(lengths) == 1 else 0
                if 0 < length <= 65536 and not handler.headers.get("Transfer-Encoding"):
                    prior_timeout = handler.connection.gettimeout()
                    handler.connection.settimeout(0.5)
                    try:
                        handler.rfile.read(length)
                    finally:
                        handler.connection.settimeout(prior_timeout)
                handler._body_consumed = True
            except Exception:
                pass
        content = json.dumps({"error": {"type": "local_broker_error", "message": message}}).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(content)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(content)
        handler.wfile.flush()
        handler.close_connection = True

    def _handle(self, handler):
        status, endpoint, safe_headers = 500, "blocked", {}
        response_started = False
        try:
            supplied = handler.headers.get_all("Authorization", [])
            expected = ("Bearer " + self._scoped_token).encode("utf-8")
            if len(supplied) != 1 or not hmac.compare_digest(supplied[0].encode("utf-8"), expected):
                status = 401
                self._error(handler, status, "role-scoped bearer required")
                return
            route = self._route(handler.command, handler.path)
            if route is None:
                status = 403
                self._error(handler, status, "operation outside model broker allowlist")
                return
            endpoint, query = route
            body = None
            if handler.command == "POST":
                lengths = handler.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or handler.headers.get("Transfer-Encoding"):
                    status = 400
                    self._error(handler, status, "bounded JSON request required")
                    return
                try:
                    length = int(lengths[0])
                except ValueError:
                    length = -1
                if length < 0 or length > self._max_body_bytes:
                    status = 413 if length > self._max_body_bytes else 400
                    self._error(handler, status, "request size outside permitted bound")
                    return
                if handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                    status = 400
                    self._error(handler, status, "JSON content type required")
                    return
                handler._body_consumed = True
                body = handler.rfile.read(length)
                try:
                    data = json.loads(body, parse_constant=_reject_json_constant)
                except (ValueError, UnicodeError):
                    status = 400
                    self._error(handler, status, "invalid JSON request")
                    return
                if not isinstance(data, dict):
                    status = 400
                    self._error(handler, status, "JSON object required")
                    return
                if _has_continuation(data):
                    status = 403
                    self._error(handler, status, "server-side response or conversation continuation is forbidden")
                    return
                with self._state_lock:
                    self._execution_requests += 1
            outbound = {"Authorization": "Bearer " + self._access_token,
                        "Accept": "text/event-stream, application/json", "originator": "codex_cli_rs"}
            if self._account_id is not None:
                outbound["ChatGPT-Account-Id"] = self._account_id
            if body is not None:
                outbound["Content-Type"] = "application/json"
            for name in ("OpenAI-Beta", "User-Agent"):
                value = handler.headers.get(name)
                if value:
                    outbound[name] = value
            safe_headers = self._safe_headers(outbound)
            with self._client.stream(handler.command, UPSTREAM_BASE + endpoint + query,
                                     headers=outbound, content=body) as upstream:
                status = upstream.status_code
                if status >= 300:
                    # Never forward redirect Location or credential-bearing
                    # diagnostic bodies from an upstream error.
                    status = 502
                    self._error(handler, status, "model upstream rejected or redirected the request")
                    return
                handler.send_response(status)
                handler.send_header("Content-Type", upstream.headers.get("Content-Type", "application/json"))
                handler.send_header("Cache-Control", "no-store")
                handler.send_header("Connection", "close")
                handler.end_headers()
                response_started = True
                # iter_bytes decompresses, so Content-Encoding/Length are not
                # forwarded. Each available chunk is flushed; no body cache.
                for chunk in upstream.iter_bytes():
                    if chunk:
                        handler.wfile.write(chunk)
                        handler.wfile.flush()
                handler.close_connection = True
        except Exception:
            status = 502
            if not response_started:
                try:
                    self._error(handler, status, "model upstream unavailable")
                except Exception:
                    pass
            handler.close_connection = True
        finally:
            with self._state_lock:
                self._audit.append({"method": handler.command, "endpoint": endpoint,
                                    "status": status, "headers": safe_headers,
                                    "execution_requests": self._execution_requests})
