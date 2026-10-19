"""Deterministic policy priors, not benchmark quality or subscription prices.

Capability/risk floors precede efficiency. Only exact evidence-backed catalog
records are routable. Policy never edits runtime arguments or root settings.
The callback entrypoint enforces pins/modes/consent before any classification;
cross-process exactly-once/dedupe is a separate state-store responsibility.
"""
from dataclasses import dataclass, replace

from .catalog import CatalogRegistry, ModelTarget
from .config import RouterConfig
from .contracts import (EventKind, ProviderResult, ProviderStatus, RiskLevel,
                        RouteDecision, RouteDisposition, TaskBinding, TaskEnvelope, TaskTier)
from .privacy import Consent, DEFAULT_SYNTHETIC_TASKS, PrivacyError, build_task_description
from .snapshots import VersionSnapshot

POLICY_VERSION = "1.0.0"
_RANKS = {"claude": {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3},
          "codex": {"luna": 0, "terra": 1, "sol": 2, "astra": 3}}
_FAMILIES = {"claude": (("haiku", "sonnet", "opus"), ("sonnet", "opus"), ("opus",), ("fable",)),
             "codex": (("luna", "terra", "sol"), ("sol", "terra"), ("sol",), ("astra",))}
_EFFORTS = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}


@dataclass(frozen=True)
class PolicyScope:
    surface: str
    host_version: str
    tool_name: str


def _decision(envelope, disposition, reason, **kwargs):
    return RouteDecision(disposition, reason, POLICY_VERSION, envelope.event,
                         provenance="policy_prior", **kwargs)


def eligibility(envelope, config):
    """Cheap precedence guard: call BEFORE provider/privacy work."""
    if envelope.explicit_model is not None or envelope.explicit_effort is not None or envelope.has_custom_or_unknown_profile:
        return _decision(envelope, RouteDisposition.SKIP, "explicit_override")
    if config.mode == "disabled":
        return _decision(envelope, RouteDisposition.SKIP, "disabled")
    worker = envelope.event in (EventKind.SUBAGENT_SPAWN, EventKind.PREPARED_TASK)
    if worker and envelope.explicit_agent_type is not None and not config.workers.allow_verified_generic_type:
        return _decision(envelope, RouteDisposition.SKIP, "generic_profiles_disabled")
    if worker and config.mode == "warn":
        return _decision(envelope, RouteDisposition.SKIP, "worker_routing_disabled")
    if worker and envelope.task_binding not in (TaskBinding.NATIVE_PLAINTEXT, TaskBinding.ORCHESTRATOR_ATTESTED):
        return _decision(envelope, RouteDisposition.DEFER, "task_binding_unknown")
    if envelope.event is EventKind.PREFLIGHT and not config.boundary.explicit_preflight_enabled:
        return _decision(envelope, RouteDisposition.SKIP, "preflight_disabled")
    if envelope.event is EventKind.ROOT_PROMPT and not config.root.warning_enabled and config.mode != "shadow":
        return _decision(envelope, RouteDisposition.SKIP, "warnings_disabled")
    return None


def _scope_records(envelope, catalog, scope):
    return tuple(record for record in catalog.records
                 if record.runtime == envelope.runtime and record.surface == scope.surface and
                 record.host_version == scope.host_version and record.tool_name == scope.tool_name)


def select_effort(requirements, tier, supported):
    """Choose effort after model support, independent of model identity.

    Do not assume high effort can be replaced by medium, or inject xhigh/max
    without measured benefit. For T0, medium is a supported conservative option
    if low is absent; T1/T2/T3 require their requested effort, else advisory.
    """
    desired = "high" if tier >= 2 or requirements.reasoning >= 0.6 or (requirements.ambiguity or 0) >= 0.6 else "medium"
    if tier == 0:
        return next((value for value in ("low", "medium") if value in supported), None)
    return desired if desired in supported else None


def decide(envelope: TaskEnvelope, provider: ProviderResult, catalog: CatalogRegistry,
           config: RouterConfig, scope: PolicyScope):
    decision = _decide(envelope, provider, catalog, config, scope)
    snapshot = VersionSnapshot.capture(POLICY_VERSION, config, catalog)
    return replace(decision, snapshot_version=snapshot.snapshot_id, catalog_version=snapshot.catalog_id)


def _decide(envelope, provider, catalog, config, scope):
    guard = eligibility(envelope, config)
    if guard is not None:
        return guard
    if provider.status is not ProviderStatus.SUCCESS:
        return _decision(envelope, RouteDisposition.DEFER, "classifier_unavailable")
    req = provider.requirements
    if req is None or req.tier is TaskTier.ABSTAIN:
        return _decision(envelope, RouteDisposition.DEFER, "classifier_abstained")
    if req.confidence < config.policy.min_confidence_for_auto:
        return _decision(envelope, RouteDisposition.DEFER, "low_confidence", confidence=req.confidence)
    if req.risk is None:
        return _decision(envelope, RouteDisposition.DEFER, "risk_unavailable", confidence=req.confidence)
    tier = int(req.tier.value[1])
    # A contradictory coarse tier cannot undercut richer high-complexity or
    # impact signals. None of these scores are claimed as actual task success.
    if max(req.complexity, req.reasoning, req.tool_complexity, req.ambiguity or 0) >= 0.8:
        tier = max(tier, 2)
    elif max(req.complexity, req.reasoning, req.tool_complexity) >= 0.5:
        tier = max(tier, 1)
    if req.risk is RiskLevel.HIGH:
        tier = max(tier, 2)
    if tier == 3 and not config.policy.frontier_auto_opt_in:
        return _decision(envelope, RouteDisposition.DEFER, "frontier_opt_in_required", confidence=req.confidence)
    runtime = envelope.runtime.value
    scoped = _scope_records(envelope, catalog, scope)
    record = effort = None
    advisory_record = None
    for family in _FAMILIES[runtime][tier]:
        if f"{runtime}.{family}" not in config.policy.enabled_targets:
            continue
        desired_version = config.policy.target_versions.get(runtime, {}).get(family)
        if desired_version is None:
            # Only Haiku lacks a user-fixed generation. Never pick an arbitrary
            # moving-alias mapping when several verified generations remain.
            versions = {item.target_version for item in scoped if item.family == family and item.mapping_status == "verified"}
            if family != "haiku" or len(versions) != 1:
                continue
            desired_version = next(iter(versions))
        result = catalog.lookup(runtime=envelope.runtime, surface=scope.surface,
                                host_version=scope.host_version, tool_name=scope.tool_name,
                                model_field="model", target=ModelTarget(family, desired_version), effort=None)
        if result.record is None:
            continue
        candidate = result.record
        chosen_effort = select_effort(req, tier, candidate.supported_efforts)
        if chosen_effort is None:
            # Model advice only; never pretend unsupported effort is applied or
            # silently inherited in an auto route. Try a supported adequate peer.
            advisory_record = advisory_record or candidate
            continue
        record, effort = candidate, chosen_effort
        break
    if record is None:
        if advisory_record is not None:
            return _decision(envelope, RouteDisposition.DEFER, "effort_advisory_only",
                             recommended_model=advisory_record.runtime_model_id,
                             confidence=req.confidence, catalog_source=advisory_record.mapping_provenance)
        return _decision(envelope, RouteDisposition.DEFER, "no_supported_route", confidence=req.confidence)
    common = dict(confidence=req.confidence, catalog_source=record.mapping_provenance)
    if config.mode == "shadow":
        return _decision(envelope, RouteDisposition.DEFER, "shadow_mode",
                         recommended_model=record.runtime_model_id, recommended_effort=effort, **common)
    if envelope.event is EventKind.PREFLIGHT:
        # Explicit user assessment works without any running root session. It
        # recommends a supported route, not an inferred root capability gap.
        return _decision(envelope, RouteDisposition.WARN_ROOT, "preflight_recommendation",
                         recommended_model=record.runtime_model_id, recommended_effort=effort, **common)
    if envelope.event in (EventKind.ROOT_PROMPT, EventKind.PREFLIGHT):
        if not config.root.warning_enabled:
            return _decision(envelope, RouteDisposition.SKIP, "warnings_disabled")
        active = [item for item in scoped if item.mapping_status == "verified" and
                  (item.runtime_model_id == envelope.active_root_model or envelope.active_root_model in item.root_model_ids)]
        if len(active) != 1 or active[0].family not in _RANKS[runtime]:
            return _decision(envelope, RouteDisposition.DEFER, "active_route_unknown")
        current = active[0]
        gap = _RANKS[runtime][record.family] > _RANKS[runtime][current.family]
        if record.runtime_model_id == current.runtime_model_id:
            current_effort = envelope.active_root_effort
            if current_effort not in current.supported_efforts or current_effort not in _EFFORTS:
                return _decision(envelope, RouteDisposition.DEFER, "active_effort_unknown")
            gap = _EFFORTS[effort] > _EFFORTS[current_effort]
        if not gap:
            return _decision(envelope, RouteDisposition.SKIP, "no_material_gain")
        return _decision(envelope, RouteDisposition.WARN_ROOT, "capability_gap",
                         recommended_model=(envelope.active_root_model if record.runtime_model_id == current.runtime_model_id
                                            else record.runtime_model_id), recommended_effort=effort, **common)
    return _decision(envelope, RouteDisposition.ROUTE_WORKER, "classified",
                     selected_model=record.runtime_model_id, selected_effort=effort, **common)


def assess(envelope, classify, catalog, config, scope, *, boundary_is_new=False,
           synthetic_tasks=DEFAULT_SYNTHETIC_TASKS):
    snapshot = VersionSnapshot.capture(POLICY_VERSION, config, catalog)
    decision = _assess(envelope, classify, catalog, config, scope,
                       boundary_is_new=boundary_is_new, synthetic_tasks=synthetic_tasks)
    return replace(decision, snapshot_version=snapshot.snapshot_id, catalog_version=snapshot.catalog_id)


def _assess(envelope, classify, catalog, config, scope, *, boundary_is_new=False,
            synthetic_tasks=DEFAULT_SYNTHETIC_TASKS):
    """At most one callback per eligible assessment; never run the task.

    Trusted adapters supply boundary proof and registered fixture sets, not
    arbitrary tool arguments. Persistent dedupe wraps this API in RTE-020.
    """
    guard = eligibility(envelope, config)
    if guard is not None:
        return guard
    if envelope.event is EventKind.ROOT_PROMPT and boundary_is_new is not True:
        return _decision(envelope, RouteDisposition.DEFER, "boundary_unknown")
    if not any(item.mapping_status == "verified" and item.availability_source != "unknown"
               for item in _scope_records(envelope, catalog, scope)):
        return _decision(envelope, RouteDisposition.DEFER, "catalog_unavailable")
    consent = (Consent.REAL_TASKS if config.consent.real_tasks else
               Consent.SYNTHETIC if config.consent.synthetic_tasks else Consent.NONE)
    try:
        description = build_task_description(envelope.task_text, consent=consent, synthetic_tasks=synthetic_tasks)
    except PrivacyError:
        return _decision(envelope, RouteDisposition.DEFER, "no_consent_or_payload")
    try:
        result = classify(description)
        if not isinstance(result, ProviderResult):
            raise ValueError()
    except Exception:
        result = ProviderResult(ProviderStatus.FAILURE, reason_code="provider_failure")
    return _decide(envelope, result, catalog, config, scope)
