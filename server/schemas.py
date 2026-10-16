"""Frozen, bounded inputs for the sixteen RingSight tools.

Amounts are integer paise, times are UTC epoch seconds. No schema admits Cypher,
tenant, role, identity, or session fields from an untrusted caller.
"""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityId = Annotated[str, Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]
Ids = Annotated[list[EntityId], Field(min_length=1, max_length=10)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    as_of: Annotated[int | None, Field(ge=0)] = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    cursor: Annotated[str | None, Field(max_length=100)] = None


class ResolveInput(Input):
    query: Annotated[str, Field(min_length=1, max_length=64)]
    kind: Literal["account", "person", "merchant", "device", "any"] = "any"
    k: Annotated[int, Field(ge=1, le=10)] = 5


class RecallInput(Input):
    entity_ids: Ids
    query: Annotated[str | None, Field(max_length=64)] = None
    include_unreviewed: bool = True


class ProfileInput(Input):
    account_id: EntityId
    window_days: Annotated[int, Field(ge=1, le=365)] = 90


class NeighbourhoodInput(ProfileInput):
    hops: Annotated[int, Field(ge=1, le=4)] = 1
    direction: Literal["out", "in", "both"] = "both"
    min_amount: Annotated[int, Field(ge=0, le=10**15)] = 0


class FanInput(Input):
    account_id: EntityId
    direction: Literal["in", "out"]
    window_hours: Annotated[int, Field(ge=1, le=720)] = 24
    min_counterparties: Annotated[int, Field(ge=2, le=100)] = 5
    drain_hours: Annotated[int, Field(ge=0, le=720)] = 72


class CyclesInput(Input):
    account_id: EntityId
    min_len: Annotated[int, Field(ge=3, le=5)] = 3
    max_len: Annotated[int, Field(ge=3, le=5)] = 5
    window_days: Annotated[int, Field(ge=1, le=365)] = 30
    max_decay_pct: Annotated[int, Field(ge=0, le=100)] = 20
    chronological: bool = True

    @model_validator(mode="after")
    def ordered(self):
        if self.min_len > self.max_len:
            raise ValueError("min_len must not exceed max_len")
        return self


class ScatterInput(Input):
    account_id: EntityId
    mode: Literal["scatter_gather", "gather_scatter"] = "scatter_gather"
    window_hours: Annotated[int, Field(ge=1, le=720)] = 72
    min_mules: Annotated[int, Field(ge=2, le=50)] = 3


class PathInput(Input):
    src_id: EntityId
    dst_id: EntityId
    max_hops: Annotated[int, Field(ge=1, le=6)] = 4
    k: Annotated[int, Field(ge=1, le=5)] = 3
    weight: Literal["hops", "amount"] = "hops"
    rel_types: Annotated[list[Literal["TX", "SHARES_STRONG"]], Field(min_length=1, max_length=2)] = ["TX"]


class RingInput(Input):
    account_id: EntityId
    basis: Literal["shared_ids", "money_wcc", "money_lpa"] = "shared_ids"
    min_size: Annotated[int, Field(ge=2, le=200)] = 3
    max_size: Annotated[int, Field(ge=3, le=500)] = 100

    @model_validator(mode="after")
    def ordered(self):
        if self.min_size > self.max_size:
            raise ValueError("min_size must not exceed max_size")
        return self


class HubInput(Input):
    scope: Literal["ring", "wcc", "global"] = "ring"
    scope_id: int | None = None
    metric: Literal["pagerank", "betweenness", "in_deg", "out_deg"] = "pagerank"
    top_k: Annotated[int, Field(ge=1, le=50)] = 10
    include_legit_hubs: bool = False

    @model_validator(mode="after")
    def scoped(self):
        if self.scope != "global" and self.scope_id is None:
            raise ValueError("scope_id is required for ring and wcc scopes")
        return self


class FlowInput(Input):
    source_ids: Ids
    sink_ids: Ids
    capacity: Literal["amount", "count"] = "amount"


class SharedInput(Input):
    account_id: EntityId
    hops: Annotated[int, Field(ge=1, le=4)] = 2
    kinds: Annotated[list[Literal["device", "phone", "address", "owner"]], Field(min_length=1, max_length=4)] = ["device", "phone", "owner"]
    max_identifier_degree: Annotated[int, Field(ge=2, le=50)] = 10


class RestrictionInput(Input):
    entity_id: EntityId


class CoverageInput(Input):
    rail: Annotated[str | None, Field(min_length=2, max_length=12, pattern=r"^[A-Za-z]+$")] = None
    from_date: Annotated[int | None, Field(ge=19000101, le=21001231)] = None
    to_date: Annotated[int | None, Field(ge=19000101, le=21001231)] = None

    @model_validator(mode="after")
    def ordered(self):
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must not exceed to_date")
        return self


INPUT_MODELS = {
    "rs_resolve_entity": ResolveInput,
    "rs_recall_findings": RecallInput,
    "rs_account_profile": ProfileInput,
    "rs_neighbourhood": NeighbourhoodInput,
    "rs_fan_pattern": FanInput,
    "rs_cycles": CyclesInput,
    "rs_scatter_gather": ScatterInput,
    "rs_path_between": PathInput,
    "rs_ring_members": RingInput,
    "rs_hub_rank": HubInput,
    "rs_money_flow": FlowInput,
    "rs_shared_identifiers": SharedInput,
    "rs_check_restrictions": RestrictionInput,
    "rs_coverage_status": CoverageInput,
}
