"""The address vault: nothing readable at rest, everything matchable, fail closed."""

import pytest

from docketyard.alerts import subscriptions, vault
from docketyard.store import db
from tests.test_subscriptions_schema import _docket


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
