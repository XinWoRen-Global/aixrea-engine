"""Solidation-gated credential-tree hardening (POSIX, cross-platform subset).

Backported from upstream deer-flow 2e859018 (#5141) to close the local race
window where ensure_lark_cli_credential_tree validated each path with is_symlink()
in separate steps. Only the POSIX portion is adopted because the Windows NTFS ACL /
handle-relative walker chunk is Windows-only native code (ctypes/ntdll) that does
not run on this project's Linux production image; it is tracked as pending follow-up.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path


def _credential_tree_path_kind(path: Path) -> str:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"Lark CLI credential path must not be a symlink: {path}")
    if os.name == "nt" and (getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError(f"Lark CLI credential path must not be a reparse point: {path}")
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    if stat.S_ISREG(info.st_mode):
        return "file"
    raise ValueError(f"Unsupported file type in Lark CLI credential tree: {path}")


def _reject_reparse_stat(path: Path, info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"Lark CLI credential path must not be a symlink: {path}")
    if os.name == "nt" and (getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError(f"Lark CLI credential path must not be a reparse point: {path}")


def _reject_credential_reparse(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    _reject_reparse_stat(path, info)


def _walk_and_harden(root: Path, apply_: Callable[[Path, str], None]) -> None:
    pending: list[Path] = [root]
    while pending:
        path = pending.pop()
        kind = _credential_tree_path_kind(path)
        apply_(path, kind)
        if kind == "dir":
            pending.extend(path.iterdir())


def harden_posix_credential_tree(root: Path) -> None:
    def _chmod(path: Path, kind: str) -> None:
        path.chmod(0o700 if kind == "dir" else 0o600)

    _walk_and_harden(root, _chmod)
