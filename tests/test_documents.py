"""The document address and the viewer (ADR 0013 addendum, 2026-08-27): the bytes at a hash,
inline and ranged; a pruned file fetched from the store and verified before it is served;
the viewer page beside the record with its neighbours, parties, files and cite line."""

import hashlib
import io

import pytest
from fastapi.testclient import TestClient

from docketyard.capture import documents as fetcher
from docketyard.capture import records
from docketyard.parties import resolve
from docketyard.store import db
from docketyard.web import documents, sitemaps
from docketyard.web.app import create_app
from tests.test_web import build_store

PDF = b"%PDF-1.4 " + bytes(range(256)) * 300  # ~77 KB, well past one range
JPG = b"\xff\xd8\xff\xe0 not really a picture"


@pytest.fixture(autouse=True)
def no_store_in_the_environment(monkeypatch):
    """`create_app` falls back to the environment's store: the tests never reach a real
    bucket, whatever the developer's shell exports."""
    for name in ("DY_S3_BUCKET", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)


def _store_with_document(tmp_path):
    """The web tests' store, with the FD 36873 filing's attachment fetched (fake bytes)."""
    path = build_store(tmp_path)
    con = db.connect(path)
    url = con.execute("SELECT source_url FROM filing_attachment LIMIT 1").fetchone()[0]
    fetcher.fetch_attachments(con, tmp_path, lambda u: (200, PDF) if u == url else (404, b""))
    sha = con.execute("SELECT document_sha256 FROM document").fetchone()[0]
    assert con.execute("SELECT COUNT(*) FROM document").fetchone()[0] == 1  # the 404 refused
    resolve.run(con, log=lambda _: 0)  # the filing's party, for the sidebar
    con.close()
    assert sha == hashlib.sha256(PDF).hexdigest()
    return path, sha


def test_document_address_serves_the_bytes_inline_with_ranges(tmp_path):
    path, sha = _store_with_document(tmp_path)
    client = TestClient(create_app(path))
    r = client.get(f"/document/{sha}.pdf")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["cache-control"] == documents.CACHE and r.headers["etag"] == f'"{sha}"'
    assert "Set-Cookie" not in r.headers
    # a browser's viewer asks for ranges
    r = client.get(f"/document/{sha}.pdf", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == PDF[:10]
    assert client.head(f"/document/{sha}.pdf").status_code == 200
    # one spelling of the address; nothing else answers
    r = client.get(f"/document/{sha}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/document/{sha}.pdf"
    assert client.get(f"/document/{sha.upper()}.pdf").status_code == 404
    assert client.get("/document/" + "0" * 64 + ".pdf").status_code == 404
    assert client.get("/document/../etc/passwd").status_code == 404


def test_a_pruned_document_is_fetched_from_the_store_and_verified(tmp_path):
    path, sha = _store_with_document(tmp_path)
    blob = records.blob_path(tmp_path, sha)
    blob.unlink()  # the prune timer took it
    asked = []

    def store(key):
        asked.append(key)
        return io.BytesIO(PDF)

    client = TestClient(create_app(path, store_fetch=store))
    r = client.get(f"/document/{sha}.pdf")
    assert r.status_code == 200 and r.content == PDF and asked == [f"blobs/{sha[:2]}/{sha}"]
    assert blob.exists()  # cached again
    # the store answering with other bytes is never served under this address
    blob.unlink()
    client = TestClient(create_app(path, store_fetch=lambda key: io.BytesIO(b"%PDF-other")))
    assert client.get(f"/document/{sha}.pdf").status_code == 503
    assert not blob.exists() and not list(records.staging_dir(tmp_path).glob("dl-*"))
    # no store configured: a miss is a miss, said plainly
    assert TestClient(create_app(path)).get(f"/document/{sha}.pdf").status_code == 503


def test_viewer_page_shows_the_file_beside_the_record(tmp_path):
    path, sha = _store_with_document(tmp_path)
    client = TestClient(create_app(path))
    r = client.get("/filing/311981/view")
    assert r.status_code == 200
    assert f'<iframe class="viewer-frame" src="/document/{sha}.pdf#toolbar=1"' in r.text
    assert "FD 36873" in r.text and "UP/NS CONTROL" in r.text and "Motion" in r.text
    assert 'href="/p/' in r.text  # the resolved party links to its page
    assert f"docketyard.org/document/{sha}.pdf" in r.text  # the cite box carries the file
    assert 'action="/subscribe"' in r.text and 'name="docket" value="FD 36873"' in r.text
    # the neighbour on the sheet (its file is held too: the fixture shares one URL)
    assert "On this sheet" in r.text and 'href="/filing/311900/view"' in r.text
    assert '<link rel="canonical" href="https://docketyard.org/filing/311981/view">' in r.text
    # a record whose file is not held yet still has a page, without the frame (the
    # decision's file answered 404 and was refused, never stored)
    r = client.get("/decision/53210/view")
    assert r.status_code == 200 and "<iframe" not in r.text and "not been fetched" in r.text
    assert client.get("/filing/999999/view").status_code == 404
    # the sheet and the record page open the viewer in a new tab
    sheet = client.get("/d/FD-36873").text
    assert 'href="/filing/311981/view" target="_blank"' in sheet
    assert 'href="/decision/53210/view"' not in sheet  # nothing to view yet
    record = client.get("/filing/311981").text
    assert 'href="/filing/311981/view"' in record and f"/document/{sha}.pdf" in record
    # the sitemap lists the document
    con = db.connect(path)
    assert f"/document/{sha}.pdf<" in sitemaps.section(con, "docketyard.org", "documents", 1, "t")
    con.close()
    assert "sitemap-documents-1.xml" in client.get("/sitemap.xml").text


def test_the_suffix_says_what_the_bytes_are_and_the_hash_validates(tmp_path):
    path, sha = _store_with_document(tmp_path)
    con = db.connect(path)
    # the decision's file, refused above, is a picture on a second try (a week later)
    con.execute("DELETE FROM capture WHERE http_status != 200")
    con.commit()
    fetcher.fetch_attachments(con, tmp_path, lambda u: (200, JPG))
    jpg = hashlib.sha256(JPG).hexdigest()
    assert (
        con.execute("SELECT media_type FROM document WHERE document_sha256 = ?", (jpg,)).fetchone()[
            0
        ]
        == "jpg"
    )
    # a kind nothing sniffed is held too, as an opaque download
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 3, NULL, '2026-08-27T00:00:00+00:00')",
        ("f" * 64,),
    )
    con.commit()
    con.close()
    opaque = records.blob_path(tmp_path, "f" * 64)
    opaque.parent.mkdir(parents=True)
    opaque.write_bytes(b"???")
    client = TestClient(create_app(path))
    r = client.get(f"/document/{jpg}.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.headers["content-disposition"] == f'inline; filename="{jpg}.jpg"'
    r = client.get(f"/document/{jpg}.pdf", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/document/{jpg}.jpg"
    r = client.get("/document/" + "f" * 64 + ".bin")
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment")
    # the hash is the validator: a revalidation never opens the file
    r = client.get(f"/document/{sha}.pdf", headers={"If-None-Match": f'"{sha}"'})
    assert r.status_code == 304 and r.headers["etag"] == f'"{sha}"'
    r = client.get(f"/document/{sha}.pdf", headers={"If-None-Match": '"other"'})
    assert r.status_code == 200 and r.headers["etag"] == f'"{sha}"'  # not the page stamp
    # the viewer shows a picture; the sitemap lists every kind at its own suffix
    assert "<iframe" in client.get("/decision/53210/view").text
    con = db.connect(path)
    listed = sitemaps.section(
        con, "docketyard.org", "documents", 1, "t2"
    )  # a fresh stamp: memoised
    con.close()
    assert f"/document/{jpg}.jpg<" in listed and "/document/" + "f" * 64 + ".bin<" in listed


def test_viewable_is_the_first_held_file_a_browser_shows():
    class A:
        def __init__(self, sha, kind):
            self.document_sha256, self.media_type = sha, kind

    class E:
        def __init__(self, *a):
            self.attachments = list(a)

    assert documents.viewable_index(E(A(None, None), A("x", "pdf"))) == 1
    assert documents.viewable_index(E(A("x", "zip"), A("y", "jpg"))) == 1
    assert documents.viewable_index(E(A("x", "zip"), A(None, None))) is None
    assert set(fetcher._EXTENSION_TYPES.values()) <= set(documents.MEDIA)


def test_the_store_read_is_a_get_of_one_key(monkeypatch):
    from docketyard.capture import s3

    with pytest.raises(ValueError):
        s3.signed_get("b", "", region="us-east-2", access_key="k", secret_key="s")
    sent = {}

    def fake_urlopen(req, timeout=None):
        sent.update(req.headers, url=req.full_url, method=req.get_method())
        return io.BytesIO(b"")

    monkeypatch.setattr(s3.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DY_S3_BUCKET", "docketyard-test")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "tok")
    fetch = s3.from_env()
    fetch("blobs/ab/abc")
    assert sent["method"] == "GET"
    assert sent["url"] == "https://docketyard-test.s3.us-east-2.amazonaws.com/blobs/ab/abc"
    assert sent["X-amz-security-token"] == "tok" and "secret" not in sent["Authorization"]
    assert "x-amz-security-token" in sent["Authorization"]  # the token is signed
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    with pytest.raises(RuntimeError):  # a bucket without keys is a misconfiguration
        s3.from_env()
    monkeypatch.delenv("DY_S3_BUCKET")
    assert s3.from_env() is None


def test_one_fetch_per_hash_however_many_ask(tmp_path):
    import threading
    import time

    path, sha = _store_with_document(tmp_path)
    records.blob_path(tmp_path, sha).unlink()
    fetched = []

    def slow_store(key):
        fetched.append(key)
        time.sleep(0.2)
        return io.BytesIO(PDF)

    client = TestClient(create_app(path, store_fetch=slow_store))
    results = []

    def ask(i):
        r = client.get(f"/document/{sha}.pdf", headers={"Range": f"bytes={i}-{i + 9}"})
        results.append(r.status_code)

    threads = [threading.Thread(target=ask, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [206] * 4 and len(fetched) == 1
    # the transient failure says when to try again; a missing store does not
    records.blob_path(tmp_path, sha).unlink()

    def down(key):
        raise ConnectionError("no route")

    r = TestClient(create_app(path, store_fetch=down)).get(f"/document/{sha}.pdf")
    assert r.status_code == 503 and r.headers["retry-after"] == "60"
    r = TestClient(create_app(path)).get(f"/document/{sha}.pdf")
    assert r.status_code == 503 and "retry-after" not in r.headers
