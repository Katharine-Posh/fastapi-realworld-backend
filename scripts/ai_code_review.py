
#!/usr/bin/env python3

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

MAX_DIFF_CHARS = 60000
MAX_RETRIES = 3
REQUEST_TIMEOUT = 90

GITHUB_API = "https://api.github.com"

IGNORED_FILES = (
    "lock",
    ".min.",
    "package-lock.json",
    "poetry.lock",
    "uv.lock",
    "vendor/",
    "__pycache__/",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".woff",
    ".ttf",
)

SYSTEM_PROMPT = """
You are a senior Python code reviewer.

Review only bugs, security vulnerabilities, reliability issues,
and significant maintainability problems introduced by this diff.

Rules:
- Report only actionable issues.
- Do not report style preferences.
- Do not report issues that existed before this diff.
- Every comment must refer to an added or changed line.
- Use the exact new-file line number.
- Be concise and explain the impact.
- Do not invent code or facts.
- If there are no issues, return an empty findings array.

Return JSON with this exact structure:
{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 10,
      "severity": "high",
      "title": "Short issue title",
      "body": "Explanation and suggested fix"
    }
  ]
}
"""


def github_request(method, path, payload=None):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set")

    url = f"{GITHUB_API}{path}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def get_pr_info():
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH is not set")

    with open(event_path, encoding="utf-8") as file:
        event = json.load(file)

    pr = event.get("pull_request")
    if not pr:
        raise RuntimeError("This workflow was not triggered by a pull request")

    repository = event["repository"]["full_name"]

    return {
        "repository": repository,
        "number": pr["number"],
        "base": pr["base"]["sha"],
        "head": pr["head"]["sha"],
    }


def get_diff(info):
    repository = info["repository"]
    base = info["base"]
    head = info["head"]

    # Three-dot diff: changes introduced by the PR branch.
    path = (
        f"/repos/{repository}/compare/"
        f"{urllib.parse.quote(base, safe='')}"
        f"...{urllib.parse.quote(head, safe='')}"
    )

    result = github_request("GET", path)

    files = result.get("files", [])
    chunks = []

    for file in files:
        filename = file.get("filename", "")

        if any(item in filename.lower() for item in IGNORED_FILES):
            continue

        patch = file.get("patch")
        if not patch:
            continue

        chunks.append(
            f"\n\nFILE: {filename}\n"
            f"STATUS: {file.get('status', 'modified')}\n"
            f"PATCH:\n{patch}"
        )

    diff = "\n".join(chunks)

    if not diff.strip():
        print("No reviewable changes found.")
        return ""

    if len(diff) > MAX_DIFF_CHARS:
        print(
            f"Diff is too large ({len(diff)} chars). "
            f"Truncating to {MAX_DIFF_CHARS} chars."
        )
        diff = diff[:MAX_DIFF_CHARS]

    return diff


def build_prompt(diff):
    return (
        "Review the following pull request diff.\n"
        "Only report issues introduced by these changes.\n"
        "Return JSON matching the required structure.\n\n"
        f"{diff}"
    )


def request_model(diff):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    url = f"{GEMINI_API_URL}/{MODEL}:generateContent"

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": build_prompt(diff)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "findings": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "file": {"type": "STRING"},
                                "line": {"type": "INTEGER"},
                                "severity": {"type": "STRING"},
                                "title": {"type": "STRING"},
                                "body": {"type": "STRING"},
                            },
                            "required": [
                                "file",
                                "line",
                                "severity",
                                "title",
                                "body",
                            ],
                        },
                    }
                },
                "required": ["findings"],
            },
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT
            ) as response:
                result = json.loads(response.read().decode("utf-8"))

            candidates = result.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini returned no candidates")

            text = candidates[0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)

            if not isinstance(parsed, dict):
                raise RuntimeError("Gemini returned invalid JSON structure")

            findings = parsed.get("findings")
            if not isinstance(findings, list):
                raise RuntimeError("Missing findings array")

            return findings

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")

            if exc.code == 429 or 500 <= exc.code <= 599:
                if attempt < MAX_RETRIES:
                    delay = min(2 ** attempt, 30)
                    print(
                        f"Gemini HTTP {exc.code}; retrying in {delay}s"
                    )
                    time.sleep(delay)
                    continue

            raise RuntimeError(
                f"Gemini API HTTP {exc.code}: {body[:1500]}"
            ) from None

        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Gemini connection error: {exc}") from None

        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Invalid Gemini response: {exc}"
            ) from None

    raise RuntimeError("Gemini request failed after retries")


def get_added_lines(diff):
    """
    Build a mapping:
    filename -> set of added line numbers.

    Only added lines from unified diff hunks are accepted.
    """
    result = {}
    current_file = None
    new_line = None

    for line in diff.splitlines():
        if line.startswith("FILE: "):
            current_file = line[6:].strip()
            result.setdefault(current_file, set())
            continue

        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                new_line = int(match.group(1))
            else:
                new_line = None
            continue

        if new_line is None or current_file is None:
            continue

        if line.startswith("+++"):
            continue

        if line.startswith("+"):
            result[current_file].add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        elif line.startswith("\\"):
            continue
        else:
            new_line += 1

    return result


def validate_findings(findings, diff):
    added_lines = get_added_lines(diff)
    valid = []

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        filename = finding.get("file")
        line = finding.get("line")
        severity = finding.get("severity")
        title = finding.get("title")
        body = finding.get("body")

        if not isinstance(filename, str):
            continue

        if not isinstance(line, int) or isinstance(line, bool):
            continue

        if severity not in ("low", "medium", "high", "critical"):
            continue

        if not isinstance(title, str) or not isinstance(body, str):
            continue

        if line not in added_lines.get(filename, set()):
            print(
                f"Skipping out-of-diff finding: {filename}:{line}"
            )
            continue

        if not title.strip() or not body.strip():
            continue

        valid.append({
            "path": filename,
            "line": line,
            "side": "RIGHT",
            "body": f"**{severity.upper()}: {title.strip()}**\n\n{body.strip()}",
        })

    return valid


def publish_review(info, comments):
    repository = info["repository"]
    number = info["number"]

    payload = {
        "commit_id": info["head"],
        "event": "COMMENT",
        "body": (
            "## AI Code Review\n\n"
            f"Found {len(comments)} actionable issue(s)."
            if comments
            else "## AI Code Review\n\nNo actionable issues found."
        ),
        "comments": comments,
    }

    path = f"/repos/{repository}/pulls/{number}/reviews"
    github_request("POST", path, payload)


def main():
    try:
        info = get_pr_info()

        print(f"Reviewing PR #{info['number']}")
        print(f"Repository: {info['repository']}")
        print(f"Model: {MODEL}")

        diff = get_diff(info)

        if not diff:
            print("Nothing to review.")
            return 0

        findings = request_model(diff)
        comments = validate_findings(findings, diff)

        print(f"Model findings: {len(findings)}")
        print(f"Valid findings: {len(comments)}")

        publish_review(info, comments)

        print("Review successfully published.")
        return 0

    except Exception as exc:
        # AI review must not break the CI pipeline.
        print(f"AI review failed: {exc}", file=sys.stderr)
        print("Continuing CI without AI review.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
