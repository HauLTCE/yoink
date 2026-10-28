"""Emitters: bundle dir, single flat file, zip."""

from __future__ import annotations

from yoink.emit.bundle import emit_bundle
from yoink.emit.flat import emit_flat
from yoink.emit.zip import emit_zip

__all__ = ["emit_bundle", "emit_flat", "emit_zip"]
