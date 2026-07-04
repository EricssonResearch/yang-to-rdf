import glob, os
from yang_to_rdf.pyang_context import build_context
from tests._shared import cached_context

def test_full_set_validates_cleanly(yang_dir, external_yams_dir):
    ctx, errors = cached_context(yang_dir, external_yams_dir)
    assert errors == [], f"expected clean validation, got: {errors[:5]}"
    modules = [m for m in ctx.modules.values() if m.keyword == "module"]
    assert len(modules) == 118

def test_incomplete_set_surfaces_errors(yang_dir):
    # No external-yams on the path -> unresolved imports must be reported, not swallowed.
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    ctx, errors = build_context(files, [yang_dir])
    assert any("MODULE_NOT_FOUND" in e for e in errors)
