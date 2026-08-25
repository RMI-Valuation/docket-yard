"""No pipeline exists yet; this keeps pytest and CI honest in the meantime."""

import docketyard


def test_package_imports():
    assert docketyard.__version__
