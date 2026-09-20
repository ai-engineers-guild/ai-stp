"""YAML loading for caller-authored documents.

`SafeLoader` alone silently keeps the last of a duplicated mapping key, which
for a typed input document is a wrong-answer hazard: the caller sees one value
and the validator reads another. Every YAML document the CLI accepts goes
through `UniqueSafeLoader`, which refuses the duplicate instead.
"""

from typing import cast

import yaml


class UniqueSafeLoader(yaml.SafeLoader):
    pass


class DuplicateKeyError(yaml.YAMLError):
    """A mapping repeated a key; `SafeLoader` alone would keep the last value."""


def _unique_mapping(loader: yaml.Loader, node: yaml.Node, deep: bool = False) -> object:
    pairs = cast(
        list[tuple[object, object]],
        loader.construct_pairs(node, deep=deep),  # pyright: ignore[reportUnknownMemberType]
    )
    result: dict[object, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate key: {key}")
        result[key] = value
    return result


UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)
