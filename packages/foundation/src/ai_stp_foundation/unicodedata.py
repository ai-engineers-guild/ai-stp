"""The Unicode database every Python normalization owner uses.

The interpreter's own `unicodedata` follows its Python release (Unicode 16 on
3.14, 17 on 3.15), while the native CLI normalizes with one pinned table. This
module pins the same Unicode version everywhere, so canonical bytes, display
identities and refusals agree between the CLI, the API, the worker and CI.
"""

from __future__ import annotations

from typing import Literal, cast

import unicodedata2 as _database

#: The Unicode version shared with the CLI's `unicode-normalization` table.
CONTRACT_VERSION = "18.0.0"
unidata_version: str = cast(str, _database.unidata_version)


def normalize(form: Literal["NFC", "NFD", "NFKC", "NFKD"], value: str) -> str:
    return cast(str, _database.normalize(form, value))  # pyright: ignore[reportUnknownMemberType]


def category(character: str) -> str:
    return cast(str, _database.category(character))  # pyright: ignore[reportUnknownMemberType]


__all__ = ["CONTRACT_VERSION", "category", "normalize", "unidata_version"]
