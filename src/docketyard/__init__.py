import os

# ADR 0010: the release tag is the truth; the packaged version is ceremonial. The image sets
# DOCKETYARD_VERSION to its tag so the User-Agent and the pages say which release is running.
__version__ = os.environ.get("DOCKETYARD_VERSION", "0.0.0")
