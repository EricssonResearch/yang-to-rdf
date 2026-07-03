"""Bootstrap a validated pyang Context using pyang's real option handling."""
from __future__ import annotations

import optparse

from pyang import plugin
from pyang.context import Context
from pyang.repository import FileRepository

SUPPRESSED_ERROR_TAGS = {"UNUSED_IMPORT"}

_plugins_initialized = False


def _build_optparser() -> optparse.OptionParser:
    global _plugins_initialized
    op = optparse.OptionParser("", add_help_option=False)
    op.add_option("-p", "--path", dest="path", default=[], action="append")
    if not _plugins_initialized:
        plugin.init([])
        _plugins_initialized = True
    for p in plugin.plugins:
        p.add_opts(op)
    return op


def build_context(
    yang_files: list[str], search_paths: list[str]
) -> tuple[Context, list[str]]:
    """Parse and validate yang_files. Returns (context, error_messages).

    error_messages excludes benign tags (SUPPRESSED_ERROR_TAGS); an empty list
    means validation is clean enough to convert.
    """
    primary = search_paths[0] if search_paths else "."
    repo = FileRepository(primary, use_env=False, no_path_recurse=True)
    repo.dirs = list(search_paths)

    ctx = Context(repo)
    (opts, _) = _build_optparser().parse_args([])
    opts.path = list(search_paths)
    ctx.opts = opts

    for fpath in yang_files:
        with open(fpath, "r", encoding="utf-8") as f:
            ctx.add_module(fpath, f.read())
    ctx.validate()

    errors: list[str] = []
    for epos, tag, args in ctx.errors:
        if tag in SUPPRESSED_ERROR_TAGS:
            continue
        errors.append(f"{epos}: {tag} {args}")
    return ctx, errors
