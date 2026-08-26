"""Test-wide fixtures: the address vault is open under a fixed key for every test."""

import pytest

from docketyard.alerts import vault

TEST_KEY = vault.Vault.new_key()


@pytest.fixture(autouse=True)
def open_vault():
    vault.configure(vault.Vault.from_key(TEST_KEY))
    yield
    vault.configure(None)
