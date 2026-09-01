"""One discipline for reading somebody's files into this program.

Adoption grew this discipline first — `lstat` before trust, a refusal for
links and special files, `O_NOFOLLOW` on open, an identity re-check after —
and bulk import grew none of it, so the same tree was read two ways and only
one of them could not be led outside itself. This module is the shared owner:
both callers classify with `classify_place` and read with `read_regular`, and
a third capture path added later starts safe instead of starting over.

Nothing here writes, and nothing here follows a link: a symlink, a hardlink,
a Windows reparse point and a device node are each named for what they are and
left for the caller to refuse or report. Following one silently is how bytes
from outside a capture root end up inside a capture.
"""

import os
import stat
from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import redact_home

#: What `classify_place` can answer. `missing` covers both "not there" and
#: "not statable": neither yields bytes and the caller's move is the same.
PLACE_REGULAR = "regular"
PLACE_DIRECTORY = "directory"
PLACE_LINK = "link"
PLACE_HARDLINK = "hardlink"
PLACE_SPECIAL = "special"
PLACE_MISSING = "missing"


def classify_place(place: Path) -> tuple[str, os.stat_result | None]:
    """What sits at this path, asked without following anything.

    `link` covers a POSIX symlink and a Windows reparse point (junctions
    included): both make a name resolve somewhere else, which is the property
    a capture has to refuse. `hardlink` is a regular file with more than one
    name — capturing it captures bytes that another name can swap after the
    fact, and refusing it is cheaper than proving it harmless.
    """
    try:
        held = place.lstat()
    except OSError:
        return PLACE_MISSING, None
    reparse = getattr(held, "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
    )
    if stat.S_ISLNK(held.st_mode) or reparse:
        return PLACE_LINK, held
    if stat.S_ISDIR(held.st_mode):
        return PLACE_DIRECTORY, held
    if not stat.S_ISREG(held.st_mode):
        return PLACE_SPECIAL, held
    if held.st_nlink != 1:
        return PLACE_HARDLINK, held
    return PLACE_REGULAR, held


def read_regular(place: Path, held: os.stat_result, *, limit: int, subject: str) -> bytes:
    """Read one already-classified regular file, refusing substitution.

    The caller classified `place` and got `regular`; this opens it without
    following links, re-checks that the opened file is the very inode that was
    classified, and reads at most `limit + 1` bytes so an oversized file is
    detected rather than swallowed. `subject` names what is being read in the
    refusals — "component", "import" — because the message reaches a person
    who asked for one of those, not for a file descriptor.
    """
    if held.st_size > limit:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this file is larger than one may be",
            details={"source_path": redact_home(place), "subject": subject},
        )
    descriptor = os.open(
        place,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (held.st_dev, held.st_ino):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "this file changed while it was being read",
                details={"source_path": redact_home(place), "subject": subject},
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(limit + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > limit:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this file is larger than one may be",
            details={"source_path": redact_home(place), "subject": subject},
        )
    return payload
