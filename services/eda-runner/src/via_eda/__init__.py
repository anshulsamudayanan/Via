"""VIA EDA runner: KiCad's own tools as an internal, credential-free service.

Runs inside the official KiCad image. It has no database, storage or queue access and
no secrets: the worker sends it a bundle (board plus project rule files) and gets KiCad's
report back. See docs/ARCHITECTURE.md and docs/SECURITY.md.
"""

__version__ = "0.1.0"
