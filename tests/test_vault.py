"""The address vault: nothing readable at rest, everything matchable, fail closed."""

import pytest

from docketyard.alerts import subscriptions, vault
from docketyard.store import db
from tests.test_subscriptions_schema import _docket


def test_the_rotation_list_names_every_sealed_and_keyed_column():
    """ADR 0014's rotation is an all-rows pass; `vault.SEALED` and `vault.KEYED_HASHES` are
    its list. Every `*_enc` column and every `email_hash` in the migrated store is on it, and
    nothing on it is missing from the store (deferred, migration 0015's critic)."""
    con = db.connect(":memory:")
    found_enc: dict[str, tuple[str, ...]] = {}
    found_hash: dict[str, tuple[str, ...]] = {}
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        if enc := tuple(c for c in cols if c.endswith("_enc")):
            found_enc[table] = enc
        if hashed := tuple(c for c in cols if c == "email_hash"):
            found_hash[table] = hashed
    assert found_enc == vault.SEALED and len(vault.SEALED) == 4
    assert found_hash == vault.KEYED_HASHES


def test_seal_open_hash():
    v = vault.Vault.from_key(vault.Vault.new_key())
    sealed = v.seal("a@example.org")
    assert "example" not in sealed and v.open(sealed) == "a@example.org"
    assert v.seal("a@example.org") != sealed  # fresh IV every time: no equality by ciphertext
    assert v.hash("a@example.org") == v.hash("a@example.org")  # the HMAC is what matches
    assert v.hash(" A@Example.org ") == v.hash("a@example.org")  # one identity per address
    assert "example" not in repr(v) and repr(v) == "Vault(open)"  # the key is never printed
    assert vault.Vault.from_env({"DY_EMAIL_KEY": "not-a-key"}) is None  # malformed: closed
    other = vault.Vault.from_key(vault.Vault.new_key())
    assert other.hash("a@example.org") != v.hash("a@example.org")
    with pytest.raises(vault.VaultClosed):
        other.open(sealed)
    with pytest.raises(ValueError):
        vault.Vault.from_key("short")


def test_nothing_readable_lands_in_the_store():
    con = db.connect(":memory:")
    d = _docket(con)
    subscriptions.subscribe(con, "Reader@Example.org", d, "pass")
    dump = "\n".join(con.iterdump()).lower()
    assert "reader@example.org" not in dump and "example.org" not in dump
    subscriptions.suppress(con, "gone@example.org", "manual")
    assert "gone@example.org" not in "\n".join(con.iterdump()).lower()
    assert subscriptions.subscribe(con, "gone@example.org", d, "pass") is None


def test_closed_vault_refuses_to_store_or_read():
    con = db.connect(":memory:")
    d = _docket(con)
    vault.configure(None)
    with pytest.raises(vault.VaultClosed):
        subscriptions.subscribe(con, "a@example.org", d, "pass")
    assert not vault.is_open()
