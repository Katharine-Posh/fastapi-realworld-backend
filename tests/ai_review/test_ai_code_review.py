import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ai_code_review.py"
spec = importlib.util.spec_from_file_location("ai_code_review", SCRIPT)
review = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(review)


def test_changed_new_lines_tracks_added_lines_only():
    patch = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1,2 +1,3 @@
-old = 1
+new = 2
+another = 3
 keep = True
"""
    assert review.changed_new_lines(patch) == {1, 2}


def test_ignores_generated_lock_and_binary_files():
    assert not review.is_reviewable("dist/app.py")
    assert not review.is_reviewable("generated/client.py")
    assert not review.is_reviewable("uv.lock")
    assert not review.is_reviewable("assets/logo.png")
    assert review.is_reviewable("conduit/services/article.py")


def test_empty_patch_has_no_lines():
    assert review.changed_new_lines("") == set()



def test_validate_model_result_accepts_expected_schema():
    result = review.validate_model_result({
        "comments": [{
            "path": "conduit/api/routes/article.py",
            "line": 42,
            "severity": "high",
            "body": "The ownership check is missing.",
        }]
    })
    assert result == [{
        "path": "conduit/api/routes/article.py",
        "line": 42,
        "severity": "high",
        "body": "The ownership check is missing.",
    }]


def test_validate_model_result_rejects_invalid_fields():
    result = review.validate_model_result({
        "comments": [
            {
                "path": "../outside.py",
                "line": 2,
                "severity": "high",
                "body": "Invalid path will be filtered against the diff later.",
            },
            {
                "path": "conduit/api/routes/article.py",
                "line": True,
                "severity": "high",
                "body": "Boolean is not a valid line number.",
            },
            {
                "path": "conduit/api/routes/article.py",
                "line": 42,
                "severity": "urgent",
                "body": "Unsupported severity.",
            },
        ]
    })
    assert result == []
