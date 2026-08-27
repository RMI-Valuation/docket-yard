"""The document address and the viewer (ADR 0013 addendum, 2026-08-27): the bytes at a hash,
inline and ranged; a pruned file fetched from the store and verified before it is served;
the viewer page beside the record with its neighbours, parties, files and cite line."""

import hashlib
import io

from fastapi.testclient import TestClient

from docketyard.capture import documents as fetcher
from docketyard.capture import records
from docketyard.parties import resolve
from docketyard.store import db
from docketyard.web import documents, sitemaps
from docketyard.web.app import create_app
from tests.test_web import build_store

PDF = b"%PDF-1.4 " + bytes(range(256)) * 300  # ~77 KB, well past one range


def _store_with_document(tmp_path):
    """The web tests' store, with the FD 36873 filing's attachment fetched (fake bytes)."""
    path = build_store(tmp_path)
    con = db.connect(path)
    url = con.execute("SELECT source_url FROM filing_attachment LIMIT 1").fetchone()[0]
    fetcher.fetch_attachments(con, tmp_path, lambda u: (200, PDF) if u == url else (404, b""))
    sha = con.execute("SELECT document_sha256 FROM document").fetchone()[0]
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
    assert 'action="/subscribe"' in r.text and 'value="FD 36873"' in r.text
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
