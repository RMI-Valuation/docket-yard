"""`tools/rmi-ai-machine/claude_refused.py`: the render rule, the request, and that what
`collect` writes from a batch's results is what `docketyard text load` takes — a page that did
not read counted as failed, never loaded as blank. No request is sent here."""

import importlib.util
import sys
from pathlib import Path

from docketyard.store import db
from docketyard.text import load
from tests.test_documents import (  # noqa: F401 — the fixture registers itself here too
    _store_with_document,
    no_store_in_the_environment,
)

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "rmi-ai-machine"
sys.path.insert(0, str(TOOLS))


def _module():
    spec = importlib.util.spec_from_file_location("claude_refused", TOOLS / "claude_refused.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_letter_page_renders_at_200_and_a_plan_sheet_fits_the_long_edge():
    c = _module()
    assert c.render_dpi(612, 792) == 200  # letter: 2200 px long edge, under the limit
    dpi = c.render_dpi(1440, 1080)  # a 20 x 15 inch sheet
    assert dpi < 200 and round(1440 / 72 * dpi) == c.MAX_EDGE
    assert c.RENDER_PROFILE == "200-max2576-grey" and "/" not in c.RENDER_PROFILE


def test_batches_stay_within_budget_and_an_oversize_page_is_never_sent():
    c = _module()
    sizes = {"page-0000": 40, "page-0001": 50, "page-0002": 30, "page-0003": 70, "page-0004": 10}
    batches, too_large = c.plan_batches(sizes, budget=90, cap=60)
    assert too_large == ["page-0003"]
    assert batches == [["page-0000", "page-0001"], ["page-0002", "page-0004"]]
    assert all(sum(sizes[i] for i in b) <= 90 for b in batches)
    assert c.b64_len(3) == 4 and c.b64_len(4) == 8


def test_a_resume_sends_only_the_groups_without_a_batch():
    c = _module()
    state = {"groups": [["page-0000"], ["page-0001"], ["page-0002"]], "batch_ids": ["msgbatch_a"]}
    assert c.unsent(state) == [["page-0001"], ["page-0002"]]
    state["batch_ids"] += ["msgbatch_b", "msgbatch_c"]
    assert c.unsent(state) == []


def test_the_request_is_the_benchmarks_prompt_with_no_thinking_or_sampling():
    c = _module()
    params = c.request_params(b"\x89PNG")
    assert params["model"] == "claude-sonnet-5"
    assert params["messages"][0]["content"][1]["text"] == c.PROMPT
    assert not {"thinking", "temperature", "top_p", "top_k"} & set(params)
    assert c.custom_id(7) == "page-0007"


def _result(cid, text=None, stop="end_turn", kind="succeeded"):
    if kind != "succeeded":
        return {"custom_id": cid, "result": {"type": kind}}
    message = {
        "model": "claude-sonnet-5",
        "stop_reason": stop,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    return {"custom_id": cid, "result": {"type": "succeeded", "message": message}}


def test_collect_writes_what_the_loader_takes_and_a_cut_or_errored_page_is_a_failure(tmp_path):
    c = _module()
    path, sha = _store_with_document(tmp_path)
    state = {
        "ended_at": "2026-09-15T23:00:00+00:00",
        "ids": {
            "page-0000": {"sha": sha, "page_no": 1},
            "page-0001": {"sha": sha, "page_no": 2},
            "page-0002": {"sha": sha, "page_no": 3},
        },
    }
    manifest = {f"{sha}:{n}": {"dpi": 200, "width": 1700, "height": 2200} for n in (1, 2, 3)}
    results = [
        _result("page-0000", "a faint fax page read well"),
        _result("page-0001", "half a pa", stop="max_tokens"),
        _result("page-0002", kind="errored"),
    ]
    (doc,) = c.reading_documents(manifest, state, results)
    assert doc["outcome"] == "read" and doc["pages_failed"] == 2
    assert [p["page_no"] for p in doc["pages"]] == [1]
    assert doc["pages"][0]["route"]["class"] == "degraded"
    assert (doc["method"], doc["render_profile"]) == ("claude-sonnet-5", "200-max2576-grey")

    con = db.connect(path)
    assert load.load_reading(con, tmp_path, load.from_reading(doc, b"{}", load.run_outcomes(con)))
    con.commit()
    rows = con.execute(
        "SELECT page_no, reading_channel, method, render_profile, text FROM document_text"
        " WHERE document_sha256 = ? AND superseded_by IS NULL AND reading_channel = 'ocr'",
        (sha,),
    ).fetchall()
    con.close()
    assert rows == [(1, "ocr", "claude-sonnet-5", "200-max2576-grey", "a faint fax page read well")]


def test_every_page_failed_is_a_failed_reading_with_no_pages():
    c = _module()
    sha = "d" * 64
    state = {"ended_at": "x", "ids": {"page-0000": {"sha": sha, "page_no": 1}}}
    (doc,) = c.reading_documents({}, state, [_result("page-0000", "x", stop="refusal")])
    assert (doc["outcome"], doc["pages_failed"], doc["pages"]) == ("failed", 1, [])
