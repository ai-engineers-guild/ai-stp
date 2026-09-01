# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false
#
# The same names that force this on the AppContainer launcher force it here:
# `ctypes.WinDLL` and `ctypes.get_last_error` do not exist in the stubs a
# checker on Linux loads, and every entry point is guarded at runtime by the
# platform check in `paths` — importing this module on POSIX touches none of
# them.
"""Owner-only enforcement and verification for Windows paths.

`is_private` used to answer `True` for every Windows path unexamined: POSIX
mode bits carry the whole invariant on two of the three platforms, and the
third returned a promise instead of a measurement. This module measures — the
owner must be the current user and the DACL may grant access to nobody else —
and enforces, by writing a protected owner-only DACL onto the private data
directory the way `chmod 0o700` does on POSIX.

SYSTEM and the built-in Administrators group are permitted alongside the
owner. They hold TakeOwnership over everything on the machine regardless, so
refusing them would fail every real profile while proving nothing; what the
invariant rules out is a grant to another *user*.

Everything here is ctypes over advapi32/kernel32, the same discipline as the
AppContainer launcher: explicit argtypes and restype on every function, so a
64-bit handle is never truncated silently.
"""

from __future__ import annotations

import ctypes
import stat
from ctypes import wintypes
from pathlib import Path
from typing import Final

_OWNER_SECURITY_INFORMATION: Final[int] = 0x00000001
_DACL_SECURITY_INFORMATION: Final[int] = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION: Final[int] = 0x80000000
_SE_FILE_OBJECT: Final[int] = 1
_TOKEN_QUERY: Final[int] = 0x0008
_TOKEN_USER_CLASS: Final[int] = 1
_ACL_REVISION: Final[int] = 2
_ACL_SIZE_INFORMATION_CLASS: Final[int] = 2
_ACCESS_ALLOWED_ACE_TYPE: Final[int] = 0x00
_INHERIT_ONLY_ACE: Final[int] = 0x08
_CONTAINER_INHERIT_ACE: Final[int] = 0x02
_OBJECT_INHERIT_ACE: Final[int] = 0x01
_FILE_ALL_ACCESS: Final[int] = 0x001F01FF
_WIN_LOCAL_SYSTEM_SID: Final[int] = 22
_WIN_BUILTIN_ADMINISTRATORS_SID: Final[int] = 26
_ERROR_SUCCESS: Final[int] = 0
_SECURITY_MAX_SID_SIZE: Final[int] = 68


class _AclSizeInformation(ctypes.Structure):
    _fields_ = (
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    )


class _AceHeader(ctypes.Structure):
    _fields_ = (
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", wintypes.WORD),
    )


class _AccessAllowedAce(ctypes.Structure):
    _fields_ = (
        ("Header", _AceHeader),
        ("Mask", wintypes.DWORD),
        ("SidStart", wintypes.DWORD),
    )


def _advapi() -> ctypes.WinDLL:
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.GetNamedSecurityInfoW.restype = wintypes.DWORD
    api.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    api.SetNamedSecurityInfoW.restype = wintypes.DWORD
    api.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    api.OpenProcessToken.restype = wintypes.BOOL
    api.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.GetTokenInformation.restype = wintypes.BOOL
    api.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    api.EqualSid.restype = wintypes.BOOL
    api.GetLengthSid.argtypes = [ctypes.c_void_p]
    api.GetLengthSid.restype = wintypes.DWORD
    api.CreateWellKnownSid.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.CreateWellKnownSid.restype = wintypes.BOOL
    api.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    api.GetAclInformation.restype = wintypes.BOOL
    api.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.GetAce.restype = wintypes.BOOL
    api.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    api.InitializeAcl.restype = wintypes.BOOL
    api.AddAccessAllowedAceEx.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    api.AddAccessAllowedAceEx.restype = wintypes.BOOL
    return api


def _kernel() -> ctypes.WinDLL:
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.argtypes = []
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.LocalFree.argtypes = [ctypes.c_void_p]
    api.LocalFree.restype = ctypes.c_void_p
    return api


def _current_user_sid(api: ctypes.WinDLL, kernel: ctypes.WinDLL) -> bytes:
    """The process token's user SID, copied out so its buffer is ours."""
    token = wintypes.HANDLE()
    if not api.OpenProcessToken(kernel.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken")
    try:
        needed = wintypes.DWORD(0)
        api.GetTokenInformation(token, _TOKEN_USER_CLASS, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not api.GetTokenInformation(
            token, _TOKEN_USER_CLASS, buffer, needed, ctypes.byref(needed)
        ):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation")
        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents
        length = api.GetLengthSid(sid_pointer)
        return ctypes.string_at(sid_pointer, length)
    finally:
        kernel.CloseHandle(token)


def _well_known_sid(api: ctypes.WinDLL, kind: int) -> bytes:
    size = wintypes.DWORD(_SECURITY_MAX_SID_SIZE)
    buffer = ctypes.create_string_buffer(size.value)
    if not api.CreateWellKnownSid(kind, None, buffer, ctypes.byref(size)):
        raise OSError(ctypes.get_last_error(), "CreateWellKnownSid")
    return buffer.raw[: size.value]


def is_private(path: Path) -> bool:
    """Whether `path` is owned by the current user and grants nobody else.

    A missing DACL is everyone-full-control and answers `False`. An empty DACL
    grants nobody and answers `True`, matching what POSIX `0o000` answers
    through the mode-bit check: the owner can always widen it back.
    Inherit-only entries are skipped — they shape children, not this object.
    """
    api = _advapi()
    kernel = _kernel()
    me = _current_user_sid(api, kernel)
    system = _well_known_sid(api, _WIN_LOCAL_SYSTEM_SID)
    administrators = _well_known_sid(api, _WIN_BUILTIN_ADMINISTRATORS_SID)

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = api.GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != _ERROR_SUCCESS:
        raise OSError(result, "GetNamedSecurityInfoW")
    try:
        me_buffer = ctypes.create_string_buffer(me)
        if not owner.value or not api.EqualSid(owner, me_buffer):
            return False
        if not dacl.value:
            return False

        info = _AclSizeInformation()
        if not api.GetAclInformation(
            dacl, ctypes.byref(info), ctypes.sizeof(info), _ACL_SIZE_INFORMATION_CLASS
        ):
            raise OSError(ctypes.get_last_error(), "GetAclInformation")
        system_buffer = ctypes.create_string_buffer(system)
        administrators_buffer = ctypes.create_string_buffer(administrators)
        for index in range(info.AceCount):
            ace_pointer = ctypes.c_void_p()
            if not api.GetAce(dacl, index, ctypes.byref(ace_pointer)):
                raise OSError(ctypes.get_last_error(), "GetAce")
            header = ctypes.cast(ace_pointer, ctypes.POINTER(_AceHeader)).contents
            if header.AceFlags & _INHERIT_ONLY_ACE:
                continue
            if header.AceType != _ACCESS_ALLOWED_ACE_TYPE:
                # A deny entry narrows access; it cannot widen it.
                continue
            ace = ctypes.cast(ace_pointer, ctypes.POINTER(_AccessAllowedAce)).contents
            sid = ctypes.c_void_p(ctypes.addressof(ace) + _AccessAllowedAce.SidStart.offset)
            if (
                api.EqualSid(sid, me_buffer)
                or api.EqualSid(sid, system_buffer)
                or api.EqualSid(sid, administrators_buffer)
            ):
                continue
            return False
        return True
    finally:
        kernel.LocalFree(descriptor)


def make_private(path: Path) -> None:
    """Write a protected owner-only DACL: owner, SYSTEM and Administrators.

    Protected, so a permissive inherited entry from the profile's parents
    stops applying — the same effect `chmod 0o700` has of not caring what the
    parent directory would have handed down.
    """
    api = _advapi()
    kernel = _kernel()
    me = _current_user_sid(api, kernel)
    system = _well_known_sid(api, _WIN_LOCAL_SYSTEM_SID)
    administrators = _well_known_sid(api, _WIN_BUILTIN_ADMINISTRATORS_SID)

    acl = ctypes.create_string_buffer(1024)
    if not api.InitializeAcl(acl, len(acl), _ACL_REVISION):
        raise OSError(ctypes.get_last_error(), "InitializeAcl")
    inherit = (
        _CONTAINER_INHERIT_ACE | _OBJECT_INHERIT_ACE if stat.S_ISDIR(path.stat().st_mode) else 0
    )
    for principal in (me, system, administrators):
        buffer = ctypes.create_string_buffer(principal)
        if not api.AddAccessAllowedAceEx(acl, _ACL_REVISION, inherit, _FILE_ALL_ACCESS, buffer):
            raise OSError(ctypes.get_last_error(), "AddAccessAllowedAceEx")
    result = api.SetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
        None,
        None,
        acl,
        None,
    )
    if result != _ERROR_SUCCESS:
        raise OSError(result, "SetNamedSecurityInfoW")
