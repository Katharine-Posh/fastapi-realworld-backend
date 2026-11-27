import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai import APIStatusError


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ai_code_review.py"
spec = importlib.util.spec_from_file_location("ai_code_review", SCRIPT)
review = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(review)


DIFF = (
    "\n\nFILE: good.py\nSTATUS: modified\nPATCH:\n"
    "@@ -1,1 +1,2 @@\n-old = 1\n+new = 2\n+extra = 3\n"
)


def fake_response(text='{"findings": []}', **kwargs):
    return SimpleNamespace(
        output_text=text,
        status=kwargs.get("status", "completed"),
        incomplete_details=kwargs.get("incomplete_details"),
        output=[
            SimpleNamespace(type=item)
            for item in kwargs.get("output_types", ("message",))
        ],
    )


class FakeResponses:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.results) - 1)
        result = self.results[index]

        if isinstance(result, Exception):
            raise result

        return result


class FakeClient:
    def __init__(self, *results):
        self.responses = FakeResponses(results)


class FakeStatusError(APIStatusError):
    def __init__(self, status_code, headers):
        self.status_code = status_code
        self.response = SimpleNamespace(headers=headers)


def test_split_hunk_keeps_original_file_line_numbers():
    pieces = review.split_hunk(
        "@@ -1,4 +10,4 @@",
        ["+a = 1", "+b = 2", "+c = 3", "+d = 4"],
        max_chars=20,
    )

    assert len(pieces) == 2
    assert "+10,2 @@" in pieces[0].splitlines()[0]
    assert "+12,2 @@" in pieces[1].splitlines()[0]


def test_split_diff_into_chunks_keeps_file_header():
    chunks = review.split_diff_into_chunks(DIFF, max_chars=200)

    assert len(chunks) == 1
    assert "FILE: good.py" in chunks[0]
    assert "@@ -1,1 +1,2 @@" in chunks[0]


def test_split_diff_into_chunks_packs_small_files_together():
    diff = DIFF + (
        "\n\nFILE: second.py\nSTATUS: modified\nPATCH:\n"
        "@@ -1,1 +1,2 @@\n-old = 1\n+new = 2\n+extra = 3\n"
    )

    chunks = review.split_diff_into_chunks(diff, max_chars=2000)

    assert len(chunks) == 1
    assert "FILE: good.py" in chunks[0]
    assert "FILE: second.py" in chunks[0]


def test_split_diff_into_chunks_flushes_when_limit_is_reached():
    diff = DIFF + (
        "\n\nFILE: second.py\nSTATUS: modified\nPATCH:\n"
        "@@ -1,1 +1,2 @@\n-old = 1\n+new = 2\n+extra = 3\n"
    )

    chunks = review.split_diff_into_chunks(diff, max_chars=150)

    assert len(chunks) == 2
    assert "FILE: good.py" in chunks[0]
    assert "FILE: second.py" in chunks[1]


def test_get_added_lines_tracks_added_lines_only():
    diff = (
        "\n\nFILE: example.py\nSTATUS: modified\nPATCH:\n"
        "diff --git a/example.py b/example.py\n"
        "--- a/example.py\n+++ b/example.py\n"
        "@@ -1,2 +1,3 @@\n-old = 1\n+new = 2\n+another = 3\n keep = True\n"
    )

    assert review.get_added_lines(diff) == {"example.py": {1, 2}}
    assert review.get_added_lines("") == {}


def test_validate_findings_filters_invalid_ranges_and_adds_suggestion():
    diff = DIFF + (
        "\n\nFILE: bad.py\nSTATUS: modified\nPATCH:\n"
        "@@ -1,3 +1,3 @@\n+one\n context\n+three\n"
    )
    findings = [
        {
            "file": "good.py",
            "start_line": 2,
            "line": 2,
            "severity": "high",
            "title": "Broken value",
            "body": "The new value breaks the caller.",
            "suggested_code": "fixed = True",
        },
        {
            "file": "bad.py",
            "start_line": 1,
            "line": 3,
            "severity": "medium",
            "title": "Non-contiguous range",
            "body": "Line 2 is not added.",
            "suggested_code": "",
        },
        {
            "file": "good.py",
            "start_line": 99,
            "line": 99,
            "severity": "high",
            "title": "Out of diff",
            "body": "Not part of the patch.",
            "suggested_code": "",
        },
        {
            "file": "../outside.py",
            "start_line": 1,
            "line": 1,
            "severity": "high",
            "title": "Invalid path",
            "body": "Path escapes the repository.",
            "suggested_code": "",
        },
    ]

    comments = review.validate_findings(findings, diff)

    assert len(comments) == 1
    assert comments[0]["path"] == "good.py"
    assert comments[0]["line"] == 2
    assert "```suggestion\nfixed = True\n```" in comments[0]["body"]


def test_parse_model_json_accepts_fenced_json_and_rejects_empty():
    assert review.parse_model_json('```json\n{"findings": []}\n```') == []

    with pytest.raises(review.EmptyResponse):
        review.parse_model_json("")


def test_request_kwargs_set_explicit_token_budget_and_strict_schema():
    kwargs = review.request_kwargs("prompt", 4096)

    assert kwargs["model"] == "openai/gpt-oss-20b"
    assert kwargs["max_output_tokens"] == 4096
    assert kwargs["reasoning"] == {"effort": "low"}
    assert kwargs["text"]["format"]["strict"] is True
    assert "findings" in kwargs["text"]["format"]["schema"]["properties"]


def test_empty_response_is_retried_with_larger_budget(monkeypatch):
    monkeypatch.setattr(review.time, "sleep", lambda *_: None)
    monkeypatch.setattr(review, "CHUNK_PAUSE_SECONDS", 0)

    client = FakeClient(
        fake_response(
            text="",
            status="incomplete",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            output_types=("reasoning",),
        ),
        fake_response(),
    )

    findings, failed = review.request_model(DIFF, client)

    assert findings == []
    assert failed == 0
    assert len(client.responses.calls) == 2
    first_budget = client.responses.calls[0]["max_output_tokens"]
    second_budget = client.responses.calls[1]["max_output_tokens"]
    assert second_budget > first_budget


def test_repeated_empty_responses_skip_chunk_without_crashing(
    monkeypatch, capsys
):
    monkeypatch.setattr(review.time, "sleep", lambda *_: None)
    monkeypatch.setattr(review, "CHUNK_PAUSE_SECONDS", 0)
    monkeypatch.setattr(review, "MAX_RETRIES", 2)

    client = FakeClient(fake_response(""), fake_response(""), fake_response(""))

    findings, failed = review.request_model(DIFF, client)

    assert findings == []
    assert failed == 1
    assert len(client.responses.calls) == 3
    assert "Chunk 1 skipped." in capsys.readouterr().out


def test_pace_after_response_respects_token_budget(monkeypatch):
    monkeypatch.setattr(review, "TOKEN_BUDGET_PER_MINUTE", 6000)
    monkeypatch.setattr(review, "CHUNK_PAUSE_SECONDS", 5)
    monkeypatch.setattr(review.time, "monotonic", lambda: 100.0)

    response = fake_response()
    response.usage = SimpleNamespace(total_tokens=5000)
    token_window = []

    assert review.pace_after_response(response, token_window) == 5
    assert review.pace_after_response(response, token_window) >= 60


def test_http_400_falls_back_to_best_effort_schema(monkeypatch):
    monkeypatch.setattr(review.time, "sleep", lambda *_: None)
    monkeypatch.setattr(review, "CHUNK_PAUSE_SECONDS", 0)

    client = FakeClient(FakeStatusError(400, {}), fake_response())

    findings, failed = review.request_model(DIFF, client)

    assert findings == []
    assert failed == 0
    assert client.responses.calls[0]["text"]["format"]["strict"] is True
    assert client.responses.calls[1]["text"]["format"]["strict"] is False


def test_rate_limit_retry_respects_retry_after(monkeypatch):
    delays = []
    monkeypatch.setattr(review.time, "sleep", lambda delay: delays.append(delay))
    monkeypatch.setattr(review, "CHUNK_PAUSE_SECONDS", 0)

    error = FakeStatusError(429, {"retry-after": "7"})
    client = FakeClient(error, fake_response())

    findings, failed = review.request_model(DIFF, client)

    assert findings == []
    assert failed == 0
    assert delays == [7.0]


def test_main_publishes_partial_review(monkeypatch):
    info = {
        "repository": "owner/repo",
        "number": 5,
        "base": "aaa",
        "head": "bbb",
    }
    findings = [
        {
            "file": "good.py",
            "start_line": 2,
            "line": 2,
            "severity": "high",
            "title": "Broken value",
            "body": "The new value breaks the caller.",
            "suggested_code": "",
        }
    ]
    published = []

    monkeypatch.setattr(review, "get_pr_info", lambda: info)
    monkeypatch.setattr(review, "get_diff", lambda _: DIFF)
    monkeypatch.setattr(review, "build_client", lambda: object())
    monkeypatch.setattr(
        review, "request_model", lambda *_: (findings, 1)
    )
    monkeypatch.setattr(
        review,
        "publish_review",
        lambda i, comments, failed: published.append((i, comments, failed)),
    )

    assert review.main([]) == 0
    assert published[0][0] == info
    assert len(published[0][1]) == 1
    assert published[0][2] == 1


def test_local_diff_file_runs_offline(tmp_path, capsys):
    diff_path = tmp_path / "change.diff"
    diff_path.write_text(
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n",
        encoding="utf-8",
    )

    assert "FILE: x.py" in review.local_diff(diff_path.read_text("utf-8"))
    assert review.main(["--diff-file", str(diff_path)]) == 0

    output = capsys.readouterr().out
    assert "Stub request:" in output
    assert "Local dry run complete (nothing published)." in output
