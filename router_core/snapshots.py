"""Immutable content-addressed policy/catalog metadata, without task or keys."""
from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
from collections.abc import Mapping
import re

from .catalog import CatalogRegistry, MAX_CATALOG_ENTRIES
from .config import RouterConfig, merge_config_layers
from .privacy import preview_task_description

MAX_SNAPSHOT_BYTES = 1_048_576
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}\Z")


class SnapshotError(ValueError):
    """Sanitized error only; never include snapshot content."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True)


def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _plain(value):
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, frozenset):
        return sorted(value)
    return value


def _label(value):
    if (not isinstance(value, str) or not _LABEL.fullmatch(value) or
            preview_task_description(value).redactions):
        raise SnapshotError("invalid_snapshot_metadata")


def _catalog_metadata(catalog):
    # Free-form evidence may contain paths/prose or accidentally pasted secrets.
    # Preserve its content hash, never the text. All other metadata is labels.
    data = json.loads(catalog.to_json())
    for entry in data["entries"]:
        evidence = entry.pop("mapping_evidence")
        entry["mapping_evidence_sha256"] = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
        for key, value in entry.items():
            for item in value if isinstance(value, list) else (value,):
                if item is not None:
                    _label(item)
    data["entries"].sort(key=_json)
    return data


def _validate_catalog(data):
    if not isinstance(data, dict) or set(data) != {"schema_version", "entries"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise SnapshotError("invalid_snapshot_catalog")
    if not isinstance(data["entries"], list) or len(data["entries"]) > MAX_CATALOG_ENTRIES:
        raise SnapshotError("invalid_snapshot_catalog")
    # Reuse the registry's strict schema, generation/scope and duplicate checks.
    original = json.loads(_json(data))
    for entry in original["entries"]:
        digest = entry.pop("mapping_evidence_sha256", None)
        if not isinstance(digest, str) or not _HASH.fullmatch(digest):
            raise SnapshotError("invalid_snapshot_catalog")
        if "mapping_evidence" in entry:
            raise SnapshotError("invalid_snapshot_catalog")
        entry["mapping_evidence"] = "Evidence content retained as digest only"
    registry = CatalogRegistry.from_json(_json(original))
    for entry in data["entries"]:
        for value in entry.values():
            for item in value if isinstance(value, list) else (value,):
                if item is not None:
                    _label(item)
    if len(registry.records) != len(data["entries"]):
        raise SnapshotError("invalid_snapshot_catalog")


@dataclass(frozen=True)
class VersionSnapshot:
    # Canonical JSON strings prevent mutation through nested dictionaries.
    policy_version: str
    config_json: str
    catalog_json: str

    def __post_init__(self):
        try:
            _label(self.policy_version)
            if not isinstance(self.config_json, str) or not isinstance(self.catalog_json, str):
                raise ValueError()
            if len(self.config_json.encode()) + len(self.catalog_json.encode()) > MAX_SNAPSHOT_BYTES:
                raise ValueError()
            from .classifier import _unique
            config = json.loads(self.config_json, object_pairs_hook=_unique)
            catalog = json.loads(self.catalog_json, object_pairs_hook=_unique)
            normalized = _plain(merge_config_layers(config, {}))
            if normalized != config:
                raise ValueError()
            _validate_catalog(catalog)
            object.__setattr__(self, "config_json", _json(config))
            catalog["entries"].sort(key=_json)
            object.__setattr__(self, "catalog_json", _json(catalog))
        except Exception:
            raise SnapshotError("invalid_version_snapshot") from None

    @classmethod
    def capture(cls, policy_version, config, catalog):
        try:
            if not isinstance(config, RouterConfig) or not isinstance(catalog, CatalogRegistry):
                raise ValueError()
            return cls(policy_version, _json(_plain(config)), _json(_catalog_metadata(catalog)))
        except Exception:
            raise SnapshotError("invalid_version_snapshot") from None

    @property
    def policy_id(self):
        return _digest(_json({"version": self.policy_version, "config": json.loads(self.config_json)}))

    @property
    def catalog_id(self):
        return _digest(self.catalog_json)

    @property
    def snapshot_id(self):
        return _digest(self.policy_id + ":" + self.catalog_id)

    def to_dict(self):
        return {"schema_version": 1, "policy_version": self.policy_version,
                "config": json.loads(self.config_json), "catalog": json.loads(self.catalog_json)}

    @classmethod
    def from_dict(cls, data):
        try:
            if not isinstance(data, dict) or set(data) != {"schema_version", "policy_version", "config", "catalog"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
                raise ValueError()
            return cls(data["policy_version"], _json(data["config"]), _json(data["catalog"]))
        except Exception:
            raise SnapshotError("invalid_version_snapshot") from None
