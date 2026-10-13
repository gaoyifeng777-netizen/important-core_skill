"""Synthetic local broker tests; upstream is mocked and no real auth is read."""
import concurrent.futures
import copy
import http.client
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

HOST_AUTH = {"auth_mode": "chatgpt", "tokens": {
    "id_token": "REAL_ID_TOKEN_FIXTURE_DO_NOT_COPY",
    "access_token": "REAL_ACCESS_TOKEN_FIXTURE_DO_NOT_COPY",
    "refresh_token": "REAL_REFRESH_TOKEN_FIXTURE_DO_NOT_COPY",
    "account_id": "fixture-account-1"}}


def test_provider_scope_token_is_not_a_host_credential():
    assert importlib.util.find_spec("model_auth_broker") is not None, "host auth broker feature missing"
    module = importlib.import_module("model_auth_broker")
    broker = module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    try:
        assert isinstance(broker.scoped_token, str) and len(broker.scoped_token) >= 32
        assert all(value not in broker.scoped_token for value in HOST_AUTH["tokens"].values())
        assert not hasattr(broker, "child_auth")
    finally:
        broker.close()


@pytest.fixture
def module():
    return importlib.import_module("model_auth_broker")


@pytest.fixture
def upstream():
    captured = []

    def handle(request):
        captured.append({"method": request.method, "url": str(request.url),
                         "headers": dict(request.headers), "body": request.read()})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"models": [{"slug": "fixture-model"}]})
        return httpx.Response(200, headers={"Content-Type": "text/event-stream", "X-Secret": "upstream-secret"},
                              content=b'data: {"fixture":"stream"}\n\ndata: [DONE]\n\n')

    return captured, httpx.MockTransport(handle)


@pytest.fixture
def broker(module, upstream):
    instance = module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=upstream[1]).start()
    try:
        yield instance
    finally:
        instance.close()


def request(broker, path="/v1/responses", *, method="POST", token=None, body=None, headers=None):
    address = urlsplit(broker.base_url)
    conn = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
    send_headers = {"Authorization": "Bearer " + (broker.scoped_token if token is None else token)}
    if headers:
        send_headers.update(headers)
    if body is None and method == "POST":
        body = {"model": "fixture-model", "input": "synthetic input", "stream": True, "store": False}
    if isinstance(body, dict):
        body = json.dumps(body).encode("utf-8")
        send_headers.setdefault("Content-Type", "application/json")
    try:
        conn.request(method, path, body=body, headers=send_headers)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_broker_is_loopback_and_context_closes_it(module, upstream):
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=upstream[1]) as b:
        assert urlsplit(b.base_url).hostname == "127.0.0.1"
        port = urlsplit(b.base_url).port
        assert request(b)[0] == 200
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    with pytest.raises((ConnectionRefusedError, OSError)):
        conn.connect()
    conn.close()


@pytest.mark.parametrize("token", ["wrong-token", "", HOST_AUTH["tokens"]["access_token"]])
def test_wrong_or_real_user_token_is_rejected(broker, upstream, token):
    assert request(broker, token=token)[0] == 401
    assert upstream[0] == []
    assert broker.execution_requests == 0


def test_another_roles_scoped_token_is_rejected(module, broker, upstream):
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=upstream[1]) as other:
        assert other.scoped_token != broker.scoped_token
        assert request(broker, token=other.scoped_token)[0] == 401
        assert upstream[0] == []


@pytest.mark.parametrize("path", [
    "http://example.test/v1/responses", "https://chatgpt.com/backend-api/codex/responses",
    "//example.test/v1/responses", "/v1/../responses", "/v1/%72esponses",
    "/v1/files", "/v1/responses/response-1", "/v1/models/../../etc", "/config", "/v1/config",
    "/v1/responses?url=file:///fixture", "/v1/models?url=https://example.test/",
    "/v1/models?client_version=1&client_version=2", "/v1/responses?client_version=1",
])
def test_arbitrary_url_and_unlisted_endpoint_are_rejected(broker, upstream, path):
    assert request(broker, path)[0] == 403
    assert upstream[0] == []


@pytest.mark.parametrize("prefix", ["", "/v1", "/codex", "/backend-api/codex"])
def test_models_prefix_maps_only_to_fixed_openai_endpoint(broker, upstream, prefix):
    status, _, body = request(broker, prefix + "/models?client_version=fixture-1", method="GET")
    assert status == 200
    assert json.loads(body)["models"][0]["slug"] == "fixture-model"
    assert upstream[0][-1]["url"] == "https://chatgpt.com/backend-api/codex/models?client_version=fixture-1"
    assert broker.execution_requests == 0


@pytest.mark.parametrize("prefix", ["", "/v1", "/codex", "/backend-api/codex"])
def test_response_prefix_maps_only_to_fixed_openai_endpoint(broker, upstream, prefix):
    status, headers, body = request(broker, prefix + "/responses")
    assert status == 200
    assert body == b'data: {"fixture":"stream"}\n\ndata: [DONE]\n\n'
    assert headers["Cache-Control"] == "no-store"
    assert "X-Secret" not in headers
    assert upstream[0][-1]["url"] == "https://chatgpt.com/backend-api/codex/responses"
    assert broker.execution_requests == 1


@pytest.mark.parametrize("method,path", [("DELETE", "/v1/responses"), ("PUT", "/v1/models"),
                                        ("GET", "/v1/responses"), ("POST", "/v1/models")])
def test_method_must_match_allowlisted_operation(broker, upstream, method, path):
    assert request(broker, path, method=method)[0] == 403
    assert upstream[0] == []


@pytest.mark.parametrize("continuation", [
    {"previous_response_id": "resp-from-other-role"}, {"conversation": "conv-from-other-role"},
    {"metadata": {"previous_response_id": "hidden-continuation"}},
    {"input": [{"conversation": {"id": "hidden-conversation"}}]},
])
def test_previous_response_or_conversation_continuation_is_rejected(broker, upstream, continuation):
    body = {"model": "fixture-model", "input": "synthetic", **continuation}
    assert request(broker, body=body)[0] == 403
    assert upstream[0] == []


def test_normal_reasoning_and_message_ids_are_preserved(broker, upstream):
    body = {"model": "fixture-model", "store": False, "stream": True, "previous_response_id": None,
            "input": [{"type": "reasoning", "id": "normal-item", "summary": []},
                      {"type": "message", "id": "message-item", "role": "user", "content": []},
                      {"type": "item_reference", "id": "current-history-item"}]}
    assert request(broker, body=body)[0] == 200
    assert json.loads(upstream[0][-1]["body"]) == body


def test_host_injects_real_auth_and_account_but_never_logs_them(broker, upstream):
    status, _, _ = request(broker, headers={"ChatGPT-Account-Id": "attacker-account",
                                          "X-Injected-Secret": "do-not-forward", "Cookie": "secret-cookie"})
    assert status == 200
    outbound = upstream[0][-1]["headers"]
    assert outbound["authorization"] == "Bearer " + HOST_AUTH["tokens"]["access_token"]
    assert outbound["chatgpt-account-id"] == "fixture-account-1"
    assert "cookie" not in outbound and "x-injected-secret" not in outbound
    audit = json.dumps(broker.audit)
    public = repr(broker) + broker.base_url + broker.scoped_token + audit
    assert all(value not in public for value in HOST_AUTH["tokens"].values())
    assert "synthetic input" not in audit
    assert "data:" not in audit
    assert broker.audit[-1]["headers"]["Authorization"] == "[redacted]"


def test_audit_is_detached_from_mutable_caller_copy(broker):
    assert request(broker)[0] == 200
    original = copy.deepcopy(broker.audit)
    modified = broker.audit
    modified[0]["headers"]["Authorization"] = "replacement"
    assert broker.audit == original


def test_unsupported_or_malformed_body_does_not_reach_upstream(broker, upstream):
    for bad in (b"not JSON", b"[]", b'{"x":NaN}'):
        assert request(broker, body=bad, headers={"Content-Type": "application/json"})[0] == 400
    assert upstream[0] == []


def test_upstream_error_does_not_expose_auth_in_public_error(module):
    def broken(request):
        raise RuntimeError("failure with secret " + HOST_AUTH["tokens"]["access_token"])
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(broken)) as b:
        status, _, body = request(b)
        assert status == 502
        assert HOST_AUTH["tokens"]["access_token"].encode() not in body
        assert HOST_AUTH["tokens"]["access_token"] not in json.dumps(b.audit)


def test_redirect_is_not_followed_to_another_destination(module):
    seen = []
    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://example.test/leak"})
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(redirect)) as b:
        status, headers, _ = request(b)
        assert status == 502
        assert "Location" not in headers
        assert len(seen) == 1


def test_concurrent_requests_have_safe_execution_count(broker):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: request(broker)[0], range(4)))
    assert results == [200, 200, 200, 200]
    assert broker.execution_requests == 4


def test_provider_token_is_read_only(module, broker):
    with pytest.raises(AttributeError):
        broker.scoped_token = "new-token"


def test_host_file_loading_reads_fixture_without_child_copy(module, tmp_path, upstream):
    source = tmp_path / "host-auth.json"
    source.write_text(json.dumps(HOST_AUTH), encoding="utf-8")
    with module.CodexAuthBroker.from_auth_path(source, proxy=None, upstream_transport=upstream[1]) as b:
        assert request(b)[0] == 200
        assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("bad", [{}, {"tokens": {}}, {"tokens": {"access_token": ""}},
                                 {"tokens": {"access_token": "x", "account_id": {"invalid": "object"}}}])
def test_bad_host_credential_shape_fails_closed(module, bad):
    with pytest.raises(module.AuthBrokerError):
        module.CodexAuthBroker(bad, proxy=None)


def test_host_respond_without_http_listener_returns_completed_object(module):
    observed = []
    completed = {"id": "fixture-response", "status": "completed", "output": [
        {"type": "function_call", "name": "read_file", "call_id": "fixture-call", "arguments": '{"path":"fixture.txt"}'}]}
    def upstream(request):
        observed.append(request)
        return httpx.Response(200, content=("data: " + json.dumps({"type": "response.completed", "response": completed}) + "\n\n").encode())
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        returned = b.respond({"model": "fixture-model", "input": "synthetic", "tools": [
            {"type": "function", "name": "read_file", "parameters": {"type": "object"}}]})
        assert returned == completed
        assert b._server is None
        assert b.execution_requests == 1
        sent = json.loads(observed[0].read())
        assert sent["stream"] is True and sent["store"] is False
        assert str(observed[0].url) == "https://chatgpt.com/backend-api/codex/responses"
        assert observed[0].headers["Authorization"] == "Bearer " + HOST_AUTH["tokens"]["access_token"]
        assert not any(value in json.dumps(b.audit) for value in HOST_AUTH["tokens"].values())


@pytest.mark.parametrize("unsafe", [
    {"previous_response_id": "another-response"}, {"conversation": {"id": "another-conversation"}},
    {"tools": [{"type": "web_search"}]}, {"tools": [{"type": "code_interpreter"}]},
    {"tools": [{"type": "file_search"}]}, {"tools": [{"type": "function", "name": "upload_file"}]},
    {"input": [{"type": "input_file", "file_data": "data:any;base64,AA=="}]},
    {"input": [{"file_id": "file-remote"}]}, {"input": [{"file_url": "https://example.test/source"}]},
    {"input": [{"type": "input_image", "image_url": "https://example.test/image.png"}]},
    {"input": [{"type": "input_image", "image_url": {"url": "https://example.test/image.png"}}]},
    {"background": True},
])
def test_host_respond_refuses_remote_tools_and_content_references(module, unsafe):
    observed = []
    def upstream(request):
        observed.append(request)
        return httpx.Response(200)
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        with pytest.raises(module.AuthBrokerError):
            b.respond({"model": "fixture-model", "input": "synthetic", **unsafe})
        assert observed == []
        assert b.execution_requests == 0


@pytest.mark.parametrize("name", ["read_file", "list_directory", "run_command", "write_file"])
def test_host_respond_function_tools_are_only_returned_not_executed(module, name):
    completed = {"status": "completed", "output": [{"type": "function_call", "name": name, "arguments": "{}"}]}
    def upstream(request):
        return httpx.Response(200, content=("data: " + json.dumps({"type": "response.completed", "response": completed}) + "\n\n").encode())
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        assert b.respond({"model": "fixture-model", "input": "synthetic", "tools": [{"type": "function", "name": name}]}) == completed


def test_host_respond_accepts_inline_image_data_url(module):
    completed = {"status": "completed", "output": []}
    def upstream(request):
        return httpx.Response(200, content=("data: " + json.dumps({"type": "response.completed", "response": completed}) + "\n\n").encode())
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        assert b.respond({"model": "fixture-model", "input": [{"type": "input_image", "image_url": "data:image/png;base64,AA=="}]}) == completed


@pytest.mark.parametrize("response", [
    b'data: {"type":"response.failed","error":{"message":"REAL_ACCESS_TOKEN_FIXTURE_DO_NOT_COPY"}}\n\n',
    b'data: {"type":"response.completed","response":{"status":"incomplete","output":[]}}\n\n',
    b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
    b'data: invalid-json\n\n', b'data: [DONE]\n\n',
])
def test_host_respond_missing_or_failed_completion_is_sanitized(module, response):
    def upstream(request):
        return httpx.Response(200, content=response)
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        with pytest.raises(module.AuthBrokerError) as exc:
            b.respond({"model": "fixture-model", "input": "synthetic"})
        assert "REAL_ACCESS_TOKEN_FIXTURE_DO_NOT_COPY" not in str(exc.value)
        assert "REAL_ACCESS_TOKEN_FIXTURE_DO_NOT_COPY" not in json.dumps(b.audit)


def test_host_respond_upstream_exception_has_no_token(module):
    def upstream(request):
        raise RuntimeError(HOST_AUTH["tokens"]["access_token"])
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        with pytest.raises(module.AuthBrokerError) as exc:
            b.respond({"model": "fixture-model", "input": "synthetic"})
        assert HOST_AUTH["tokens"]["access_token"] not in str(exc.value)


def test_host_respond_rejects_use_after_close(module, upstream):
    b = module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=upstream[1], serve_http=False)
    b.close()
    with pytest.raises(module.AuthBrokerError):
        b.respond({"model": "fixture-model", "input": "synthetic"})


def respond_events(module, events):
    wire = "".join("data: " + json.dumps(event) + "\n\n" for event in events).encode("utf-8")
    with module.CodexAuthBroker(HOST_AUTH, proxy=None,
                              upstream_transport=httpx.MockTransport(lambda r: httpx.Response(200, content=wire)),
                              serve_http=False) as b:
        return b.respond({"model": "fixture-model", "input": "synthetic"})


def test_done_items_restore_empty_final_output_in_index_order_without_field_loss(module):
    reasoning = {"id": "reason-1", "type": "reasoning", "summary": [{"type": "summary_text", "text": "fixture"}],
                 "encrypted_content": "opaque-real-event-fixture", "future_field": {"retained": True}}
    message = {"id": "message-1", "type": "message", "status": "completed", "role": "assistant",
               "content": [{"type": "output_text", "text": "PING_OK", "annotations": []}], "phase": "final_answer"}
    response = respond_events(module, [
        {"type": "response.output_item.done", "output_index": 1, "item": message},
        {"type": "response.output_item.done", "output_index": 0, "item": reasoning},
        {"type": "response.completed", "response": {"id": "resp-1", "status": "completed", "output": [], "usage": {"total_tokens": 7}}},
    ])
    assert response == {"id": "resp-1", "status": "completed", "output": [reasoning, message], "usage": {"total_tokens": 7}}


def test_done_function_item_restores_missing_final_output_without_changing_arguments(module):
    item = {"type": "function_call", "name": "read_file", "id": "fc-1", "call_id": "call-1",
            "arguments": '{"path": "fixture.txt", "limit": 2}', "status": "completed"}
    response = respond_events(module, [
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": {"status": "completed"}},
    ])
    assert response["output"] == [item]


def test_done_items_do_not_duplicate_nonempty_final_output(module):
    item = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "PING_OK"}]}
    response = respond_events(module, [
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": {"status": "completed", "output": [item]}},
    ])
    assert response["output"] == [item]


def test_identical_duplicate_done_index_is_idempotent(module):
    item = {"type": "reasoning", "summary": [], "encrypted_content": "opaque"}
    event = {"type": "response.output_item.done", "output_index": 0, "item": item}
    assert respond_events(module, [event, event, {"type": "response.completed", "response": {"status": "completed", "output": []}}])["output"] == [item]


def test_conflicting_duplicate_done_index_is_rejected(module):
    with pytest.raises(module.AuthBrokerError):
        respond_events(module, [
            {"type": "response.output_item.done", "output_index": 0, "item": {"type": "reasoning", "summary": []}},
            {"type": "response.output_item.done", "output_index": 0, "item": {"type": "message", "content": []}},
            {"type": "response.completed", "response": {"status": "completed", "output": []}},
        ])


@pytest.mark.parametrize("index", [-1, True, "0", None, 0.5])
def test_invalid_done_output_index_is_rejected(module, index):
    with pytest.raises(module.AuthBrokerError):
        respond_events(module, [
            {"type": "response.output_item.done", "output_index": index, "item": {"type": "reasoning", "summary": []}},
            {"type": "response.completed", "response": {"status": "completed", "output": []}},
        ])


def test_done_item_gap_does_not_fabricate_missing_output(module):
    with pytest.raises(module.AuthBrokerError):
        respond_events(module, [
            {"type": "response.output_item.done", "output_index": 1, "item": {"type": "reasoning", "summary": []}},
            {"type": "response.completed", "response": {"status": "completed", "output": []}},
        ])


@pytest.mark.parametrize("item", [
    {"type": "web_search_call", "id": "remote-tool"},
    {"type": "code_interpreter_call", "id": "remote-tool"},
    {"type": "function_call", "name": "upload_file", "arguments": "{}"},
])
def test_unapproved_done_tool_cannot_hide_behind_empty_final_output(module, item):
    with pytest.raises(module.AuthBrokerError):
        respond_events(module, [
            {"type": "response.output_item.done", "output_index": 0, "item": item},
            {"type": "response.completed", "response": {"status": "completed", "output": []}},
        ])


def test_delta_events_alone_do_not_fabricate_completed_items(module):
    response = respond_events(module, [
        {"type": "response.output_text.delta", "output_index": 0, "delta": "PING_OK"},
        {"type": "response.completed", "response": {"status": "completed", "output": []}},
    ])
    assert response["output"] == []


def test_host_respond_rejects_remote_stored_item_reference_before_upstream(module):
    observed = []
    def upstream(request):
        observed.append(request)
        return httpx.Response(200, content=b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n')
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        with pytest.raises(module.AuthBrokerError):
            b.respond({"model": "fixture-model", "input": [{"type": "item_reference", "id": "msg-from-stored-session"}]})
        assert observed == []
        assert b.execution_requests == 0


def test_host_respond_preserves_complete_input_item_ids(module):
    observed = []
    items = [{"type": "reasoning", "id": "reasoning-id", "summary": [], "encrypted_content": "opaque"},
             {"type": "message", "id": "message-id", "role": "assistant", "content": [{"type": "output_text", "text": "fixture"}]},
             {"type": "function_call", "id": "function-id", "call_id": "call-id", "name": "read_file", "arguments": "{}"},
             {"type": "function_call_output", "call_id": "call-id", "output": "fixture output"}]
    def upstream(request):
        observed.append(json.loads(request.read()))
        return httpx.Response(200, content=b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n')
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, upstream_transport=httpx.MockTransport(upstream), serve_http=False) as b:
        assert b.respond({"model": "fixture-model", "input": items})["status"] == "completed"
        assert observed[0]["input"] == items


def test_incomplete_diagnostic_preserves_safe_reason_and_numeric_usage_only(module):
    event = {"type": "response.incomplete", "response": {
        "incomplete_details": {"reason": "max_output_tokens", "message": HOST_AUTH["tokens"]["access_token"]},
        "usage": {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46,
                  "input_tokens_details": {"cached_tokens": 5, "secret": HOST_AUTH["tokens"]["access_token"]},
                  "output_tokens_details": {"reasoning_tokens": 20}, "raw_secret": HOST_AUTH["tokens"]["access_token"]}}}
    wire = ("data: " + json.dumps(event) + "\n\n").encode()
    with module.CodexAuthBroker(HOST_AUTH, proxy=None, serve_http=False,
                              upstream_transport=httpx.MockTransport(lambda r: httpx.Response(200, content=wire))) as b:
        with pytest.raises(module.AuthBrokerError) as captured:
            b.respond({"model": "fixture-model", "input": "synthetic"})
        error = captured.value
        assert error.failure_event == "response.incomplete"
        assert error.failure_code == "max_output_tokens"
        expected = {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46,
                    "input_tokens_details": {"cached_tokens": 5}, "output_tokens_details": {"reasoning_tokens": 20}}
        assert error.usage == expected
        assert "response.incomplete" in str(error) and "max_output_tokens" in str(error)
        assert b.audit[-1]["failure_event"] == "response.incomplete"
        assert b.audit[-1]["failure_code"] == "max_output_tokens"
        assert b.audit[-1]["usage"] == expected
        assert HOST_AUTH["tokens"]["access_token"] not in str(error) + json.dumps(b.audit)


@pytest.mark.parametrize("event,code", [
    ({"type": "response.failed", "response": {"error": {"code": "server_error.v2-retry", "message": "secret raw body"}}}, "server_error.v2-retry"),
    ({"type": "error", "error": {"code": "rate_limit_exceeded", "message": "secret raw body"}, "usage": {"total_tokens": 9}}, "rate_limit_exceeded"),
    ({"type": "error", "code": "server_error", "message": "secret raw body"}, "server_error"),
])
def test_failed_event_and_error_event_report_safe_enum_only(module, event, code):
    with pytest.raises(module.AuthBrokerError) as captured:
        respond_events(module, [event])
    assert captured.value.failure_event == event["type"]
    assert captured.value.failure_code == code
    assert "secret raw body" not in str(captured.value)


@pytest.mark.parametrize("unsafe", ["reason with whitespace", "x" * 81, "reason/unsafe", {"code": "not-a-string"},
                                    HOST_AUTH["tokens"]["access_token"]])
def test_diagnostic_rejects_unsafe_or_credential_reason_code(module, unsafe):
    with pytest.raises(module.AuthBrokerError) as captured:
        respond_events(module, [{"type": "response.failed", "response": {"error": {"code": unsafe, "message": "raw secret"}}}])
    assert captured.value.failure_event == "response.failed"
    assert captured.value.failure_code == "unspecified"
    assert "raw secret" not in str(captured.value)
    assert HOST_AUTH["tokens"]["access_token"] not in str(captured.value)


def test_diagnostic_usage_does_not_accept_bool_text_or_unbounded_values(module):
    with pytest.raises(module.AuthBrokerError) as captured:
        respond_events(module, [{"type": "response.incomplete", "response": {
            "incomplete_details": {"reason": "max_output_tokens"},
            "usage": {"input_tokens": True, "output_tokens": "500", "total_tokens": -1,
                      "input_tokens_details": {"cached_tokens": 10**50},
                      "output_tokens_details": {"reasoning_tokens": 4}}}}])
    assert captured.value.usage == {"output_tokens_details": {"reasoning_tokens": 4}}
