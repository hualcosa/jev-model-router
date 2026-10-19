"""User-level installation with per-working-directory state and authority."""
import hashlib
import json
import os
from pathlib import Path


def scope_key(project):
    source = os.path.abspath(os.fspath(project))
    return hashlib.sha256(json.dumps([source, os.path.realpath(source)],
        separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def profile_path(root, project):
    return Path(root) / (scope_key(project) + ".json")


def state_path(root, project):
    return Path(root) / scope_key(project)


def scoped_config(global_config, project):
    from .config import load_config
    project = Path(project).resolve()
    return load_config(global_config, project_paths=[
        path / ".intelligent-agent-router.json" for path in reversed((project, *project.parents))])


def codex_profile(root, *, project, binary, surface, version, refresh=False):
    # Lazy imports avoid a cycle with the own-command profile recognizer.
    from .profiles import (load_capability_profile, build_profile_document,
                           write_profile, ProfileError)
    from .native import bootstrap_profile
    from .inventory import discover_codex_models, read_codex_hooks
    from .catalog import CatalogRegistry
    path = profile_path(root, project)
    kwargs = dict(runtime="codex", surface=surface, version=version,
                  project=project, binary=binary)
    try:
        return load_capability_profile(path, **kwargs)
    except ProfileError:
        if not refresh:
            raise
    base = bootstrap_profile("codex", surface, version)
    if base is None:
        raise ProfileError("runtime_unverified")
    # Only read native metadata, never grant trust/permissions or infer models.
    inventory = discover_codex_models(binary, base.spawn)
    hooks = read_codex_hooks(binary, base.spawn, os.path.abspath(project))
    document, _ = build_profile_document(**kwargs, profile_path=path,
        catalog=CatalogRegistry.from_json(json.dumps(inventory["catalog"])), hooks=hooks)
    write_profile(path, document)
    return load_capability_profile(path, **kwargs)
