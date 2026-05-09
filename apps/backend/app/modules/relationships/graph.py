from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, OperationalEvent, Plant, Shipment, Supplier
from app.modules.operational_events.timeline import (
    build_timeline_for_risk_candidate,
)
from app.modules.rules.engine import RiskCandidate, evaluate_rule_based_risks
from app.modules.shipments.continuity import calculate_shipment_continuity_for
from app.modules.stock.continuity import calculate_inventory_continuity_for
from app.schemas.context import RequestContext

FRESHNESS_ORDER = {"fresh": 0, "delayed": 1, "unknown": 2, "stale": 3, "critical": 4}


class RelationshipGraphContext(BaseModel):
    tenant_id: int
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None


class RelationshipNode(BaseModel):
    id: str
    type: str
    label: str
    reference: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationshipEdge(BaseModel):
    from_node_id: str
    to_node_id: str
    relationship: str


class ConfidenceSummary(BaseModel):
    lowest_confidence_score: Decimal | None = None
    worst_freshness_status: str | None = None


class RelationshipGraphSummary(BaseModel):
    inventory_continuity: dict[str, Any] | None = None
    shipment_continuity: dict[str, Any] | None = None
    timeline_event_count: int = 0
    active_risk_candidate_count: int = 0
    confidence_summary: ConfidenceSummary


class OperationalRelationshipGraph(BaseModel):
    context: RelationshipGraphContext
    nodes: list[RelationshipNode]
    edges: list[RelationshipEdge]
    summary: RelationshipGraphSummary


class GraphScope(BaseModel):
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    source_event_ids: list[int] = Field(default_factory=list)


def build_operational_relationship_graph(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    risk_candidate: RiskCandidate | None = None,
    now: datetime | None = None,
) -> OperationalRelationshipGraph:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    scope = scope_from_inputs(
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        risk_candidate=risk_candidate,
    )
    shipment = find_shipment(db, context, scope.shipment_reference)
    if shipment is not None:
        scope.shipment_reference = shipment.shipment_id
        plant = find_plant_by_id(db, context, shipment.plant_id)
        material = find_material_by_id(db, context, shipment.material_id)
        scope.plant_reference = scope.plant_reference or (plant.code if plant else None)
        scope.material_reference = scope.material_reference or (material.code if material else None)
    else:
        plant = find_plant_by_code(db, context, scope.plant_reference)
        material = find_material_by_code(db, context, scope.material_reference)

    events = relevant_events(db, context, scope)
    timeline_event_count = len(events)
    candidates = relevant_risk_candidates(
        db,
        context,
        scope,
        risk_candidate=risk_candidate,
        now=evaluated_at,
    )

    graph_builder = GraphBuilder()
    add_core_nodes(graph_builder, plant, material, shipment)
    add_supplier_node(graph_builder, db, context, shipment)
    add_event_nodes(graph_builder, events)
    add_risk_nodes(graph_builder, candidates)

    inventory_summary = inventory_continuity_summary(
        db,
        context,
        plant,
        material,
        now=evaluated_at,
    )
    shipment_summary = shipment_continuity_summary(
        db,
        context,
        shipment,
        now=evaluated_at,
    )

    return OperationalRelationshipGraph(
        context=RelationshipGraphContext(
            tenant_id=context.tenant_id,
            plant_reference=scope.plant_reference,
            material_reference=scope.material_reference,
            shipment_reference=scope.shipment_reference,
        ),
        nodes=graph_builder.nodes(),
        edges=graph_builder.edges(),
        summary=RelationshipGraphSummary(
            inventory_continuity=inventory_summary,
            shipment_continuity=shipment_summary,
            timeline_event_count=timeline_event_count,
            active_risk_candidate_count=len(candidates),
            confidence_summary=confidence_summary(events, candidates),
        ),
    )


def scope_from_inputs(
    *,
    plant_reference: str | None,
    material_reference: str | None,
    shipment_reference: str | None,
    risk_candidate: RiskCandidate | None,
) -> GraphScope:
    if risk_candidate is None:
        return GraphScope(
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
        )
    return GraphScope(
        plant_reference=plant_reference or risk_candidate.plant_reference,
        material_reference=material_reference or risk_candidate.material_reference,
        shipment_reference=shipment_reference or risk_candidate.shipment_reference,
        source_event_ids=list(risk_candidate.source_event_ids),
    )


def add_core_nodes(
    graph_builder: GraphBuilder,
    plant: Plant | None,
    material: Material | None,
    shipment: Shipment | None,
) -> None:
    if plant is not None:
        graph_builder.add_node(
            node_id=plant_node_id(plant.code),
            node_type="plant",
            label=plant.name,
            reference=plant.code,
            metadata={"location": plant.location} if plant.location else {},
        )
    if material is not None:
        graph_builder.add_node(
            node_id=material_node_id(material.code),
            node_type="material",
            label=material.name,
            reference=material.code,
            metadata={"category": material.category, "uom": material.uom},
        )
    if shipment is not None:
        graph_builder.add_node(
            node_id=shipment_node_id(shipment.shipment_id),
            node_type="shipment",
            label=shipment.shipment_id,
            reference=shipment.shipment_id,
            metadata={
                "current_state": shipment.current_state.value,
                "current_eta": shipment.current_eta,
                "quantity_mt": shipment.quantity_mt,
            },
        )

    if material is not None and plant is not None:
        graph_builder.add_edge(
            material_node_id(material.code),
            plant_node_id(plant.code),
            "used_at",
        )
    if shipment is not None and material is not None:
        graph_builder.add_edge(
            shipment_node_id(shipment.shipment_id),
            material_node_id(material.code),
            "replenishes",
        )
    if shipment is not None and plant is not None:
        graph_builder.add_edge(
            shipment_node_id(shipment.shipment_id),
            plant_node_id(plant.code),
            "linked_to",
        )


def add_supplier_node(
    graph_builder: GraphBuilder,
    db: Session,
    context: RequestContext,
    shipment: Shipment | None,
) -> None:
    if shipment is None:
        return
    supplier = find_supplier_for_shipment(db, context, shipment)
    supplier_reference = supplier.code if supplier is not None else shipment.supplier_name
    graph_builder.add_node(
        node_id=supplier_node_id(supplier_reference),
        node_type="supplier",
        label=supplier.name if supplier is not None else shipment.supplier_name,
        reference=supplier_reference,
        metadata={"country_of_origin": supplier.country_of_origin}
        if supplier is not None and supplier.country_of_origin
        else {},
    )
    graph_builder.add_edge(
        shipment_node_id(shipment.shipment_id),
        supplier_node_id(supplier_reference),
        "supplied_by",
    )


def add_event_nodes(
    graph_builder: GraphBuilder,
    events: list[OperationalEvent],
) -> None:
    for event in events:
        event_id = event_node_id(event.id)
        graph_builder.add_node(
            node_id=event_id,
            node_type="operational_event",
            label=event.event_type.value,
            reference=str(event.id),
            metadata={
                "event_type": event.event_type.value,
                "event_category": event.event_category.value,
                "confidence_score": event.confidence_score,
                "freshness_status": event.freshness_status.value
                if event.freshness_status
                else None,
            },
        )
        if event.plant_reference:
            graph_builder.add_reference_node(
                plant_node_id(event.plant_reference),
                "plant",
                event.plant_reference,
            )
            graph_builder.add_edge(
                event_id,
                plant_node_id(event.plant_reference),
                "generated_signal",
            )
        if event.material_reference:
            graph_builder.add_reference_node(
                material_node_id(event.material_reference),
                "material",
                event.material_reference,
            )
            graph_builder.add_edge(
                event_id,
                material_node_id(event.material_reference),
                "generated_signal",
            )
        if event.shipment_reference:
            graph_builder.add_reference_node(
                shipment_node_id(event.shipment_reference),
                "shipment",
                event.shipment_reference,
            )
            graph_builder.add_edge(
                event_id,
                shipment_node_id(event.shipment_reference),
                "generated_signal",
            )


def add_risk_nodes(
    graph_builder: GraphBuilder,
    candidates: list[RiskCandidate],
) -> None:
    for index, candidate in enumerate(candidates, start=1):
        node_id = risk_node_id(candidate, index)
        graph_builder.add_node(
            node_id=node_id,
            node_type="risk_candidate",
            label=candidate.risk_type,
            reference=node_id,
            metadata={
                "risk_type": candidate.risk_type,
                "severity": candidate.severity,
                "confidence_score": candidate.confidence_score,
                "freshness_status": candidate.freshness_status,
                "source_event_ids": list(candidate.source_event_ids),
            },
        )
        for event_id in candidate.source_event_ids:
            graph_builder.add_edge(event_node_id(event_id), node_id, "contributes_to_risk")
        if candidate.plant_reference:
            graph_builder.add_reference_node(
                plant_node_id(candidate.plant_reference),
                "plant",
                candidate.plant_reference,
            )
            graph_builder.add_edge(node_id, plant_node_id(candidate.plant_reference), "linked_to")
        if candidate.material_reference:
            graph_builder.add_reference_node(
                material_node_id(candidate.material_reference),
                "material",
                candidate.material_reference,
            )
            graph_builder.add_edge(
                node_id,
                material_node_id(candidate.material_reference),
                "linked_to",
            )
        if candidate.shipment_reference:
            graph_builder.add_reference_node(
                shipment_node_id(candidate.shipment_reference),
                "shipment",
                candidate.shipment_reference,
            )
            graph_builder.add_edge(
                node_id,
                shipment_node_id(candidate.shipment_reference),
                "linked_to",
            )
        if candidate.recommended_owner_role:
            owner_id = owner_node_id(candidate.recommended_owner_role)
            graph_builder.add_node(
                node_id=owner_id,
                node_type="owner",
                label=candidate.recommended_owner_role,
                reference=candidate.recommended_owner_role,
            )
            graph_builder.add_edge(node_id, owner_id, "owned_by")


def inventory_continuity_summary(
    db: Session,
    context: RequestContext,
    plant: Plant | None,
    material: Material | None,
    *,
    now: datetime,
) -> dict[str, Any] | None:
    if plant is None or material is None:
        return None
    continuity = calculate_inventory_continuity_for(
        db,
        context,
        plant.id,
        material.id,
        now=now,
    )
    return continuity.model_dump(mode="python") if continuity is not None else None


def shipment_continuity_summary(
    db: Session,
    context: RequestContext,
    shipment: Shipment | None,
    *,
    now: datetime,
) -> dict[str, Any] | None:
    if shipment is None:
        return None
    continuity = calculate_shipment_continuity_for(
        db,
        context,
        shipment.shipment_id,
        now=now,
    )
    return continuity.model_dump(mode="python") if continuity is not None else None


def relevant_events(
    db: Session,
    context: RequestContext,
    scope: GraphScope,
) -> list[OperationalEvent]:
    candidate_like = RiskCandidate(
        risk_type="relationship_graph_context",
        severity="low",
        plant_reference=scope.plant_reference,
        material_reference=scope.material_reference,
        shipment_reference=scope.shipment_reference,
        rule_reasons=["Relationship graph context lookup"],
        source_event_ids=scope.source_event_ids,
    )
    entries = build_timeline_for_risk_candidate(db, context, candidate_like)
    event_ids = [entry.event_id for entry in entries]
    if not event_ids:
        return []
    return list(
        db.scalars(
            select(OperationalEvent)
            .where(
                OperationalEvent.tenant_id == context.tenant_id,
                OperationalEvent.id.in_(event_ids),
            )
            .order_by(OperationalEvent.occurred_at, OperationalEvent.id)
        )
    )


def relevant_risk_candidates(
    db: Session,
    context: RequestContext,
    scope: GraphScope,
    *,
    risk_candidate: RiskCandidate | None,
    now: datetime,
) -> list[RiskCandidate]:
    candidates = [risk_candidate] if risk_candidate is not None else []
    candidates.extend(evaluate_rule_based_risks(db, context, now=now))
    unique: dict[tuple, RiskCandidate] = {}
    for candidate in candidates:
        if candidate is not None and candidate_matches_scope(candidate, scope):
            unique[risk_key(candidate)] = candidate
    return [unique[key] for key in sorted(unique)]


def candidate_matches_scope(candidate: RiskCandidate, scope: GraphScope) -> bool:
    if scope.shipment_reference and candidate.shipment_reference == scope.shipment_reference:
        return True
    if (
        scope.plant_reference
        and scope.material_reference
        and candidate.plant_reference == scope.plant_reference
        and candidate.material_reference == scope.material_reference
    ):
        return True
    if scope.source_event_ids and set(candidate.source_event_ids).intersection(
        scope.source_event_ids
    ):
        return True
    return False


def confidence_summary(
    events: list[OperationalEvent],
    candidates: list[RiskCandidate],
) -> ConfidenceSummary:
    confidence_values = [
        event.confidence_score for event in events if event.confidence_score is not None
    ]
    confidence_values.extend(
        candidate.confidence_score
        for candidate in candidates
        if candidate.confidence_score is not None
    )
    freshness_values = [
        event.freshness_status.value for event in events if event.freshness_status is not None
    ]
    freshness_values.extend(
        candidate.freshness_status for candidate in candidates if candidate.freshness_status
    )
    return ConfidenceSummary(
        lowest_confidence_score=min(confidence_values) if confidence_values else None,
        worst_freshness_status=worst_freshness(freshness_values),
    )


def worst_freshness(values: list[str]) -> str | None:
    if not values:
        return None
    return max(values, key=lambda value: FRESHNESS_ORDER.get(value, 0))


def find_plant_by_code(
    db: Session,
    context: RequestContext,
    plant_reference: str | None,
) -> Plant | None:
    if plant_reference is None:
        return None
    return db.scalar(
        select(Plant).where(
            Plant.tenant_id == context.tenant_id,
            Plant.code == plant_reference,
        )
    )


def find_material_by_code(
    db: Session,
    context: RequestContext,
    material_reference: str | None,
) -> Material | None:
    if material_reference is None:
        return None
    return db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.code == material_reference,
        )
    )


def find_plant_by_id(db: Session, context: RequestContext, plant_id: int) -> Plant | None:
    return db.scalar(
        select(Plant).where(
            Plant.tenant_id == context.tenant_id,
            Plant.id == plant_id,
        )
    )


def find_material_by_id(db: Session, context: RequestContext, material_id: int) -> Material | None:
    return db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.id == material_id,
        )
    )


def find_shipment(
    db: Session,
    context: RequestContext,
    shipment_reference: str | None,
) -> Shipment | None:
    if shipment_reference is None:
        return None
    return db.scalar(
        select(Shipment).where(
            Shipment.tenant_id == context.tenant_id,
            Shipment.shipment_id == shipment_reference,
        )
    )


def find_supplier_for_shipment(
    db: Session,
    context: RequestContext,
    shipment: Shipment,
) -> Supplier | None:
    if shipment.supplier_id is not None:
        supplier = db.scalar(
            select(Supplier).where(
                Supplier.tenant_id == context.tenant_id,
                Supplier.id == shipment.supplier_id,
            )
        )
        if supplier is not None:
            return supplier
    return db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == context.tenant_id,
            Supplier.name == shipment.supplier_name,
        )
    )


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def plant_node_id(reference: str) -> str:
    return f"plant:{reference}"


def material_node_id(reference: str) -> str:
    return f"material:{reference}"


def shipment_node_id(reference: str) -> str:
    return f"shipment:{reference}"


def supplier_node_id(reference: str) -> str:
    return f"supplier:{reference}"


def event_node_id(event_id: int) -> str:
    return f"operational_event:{event_id}"


def owner_node_id(owner_role: str) -> str:
    return f"owner:{owner_role}"


def risk_node_id(candidate: RiskCandidate, index: int) -> str:
    context = candidate.shipment_reference or candidate.material_reference or "unscoped"
    return f"risk_candidate:{candidate.risk_type}:{context}:{index}"


def risk_key(candidate: RiskCandidate) -> tuple:
    return (
        candidate.risk_type,
        candidate.severity,
        candidate.plant_reference or "",
        candidate.material_reference or "",
        candidate.shipment_reference or "",
        tuple(candidate.source_event_ids),
    )


class GraphBuilder:
    def __init__(self) -> None:
        self._nodes: dict[str, RelationshipNode] = {}
        self._edges: set[tuple[str, str, str]] = set()

    def add_node(
        self,
        *,
        node_id: str,
        node_type: str,
        label: str,
        reference: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if node_id in self._nodes:
            if metadata:
                self._nodes[node_id].metadata.update(metadata)
            return
        self._nodes[node_id] = RelationshipNode(
            id=node_id,
            type=node_type,
            label=label,
            reference=reference,
            metadata=metadata or {},
        )

    def add_reference_node(
        self,
        node_id: str,
        node_type: str,
        reference: str,
    ) -> None:
        self.add_node(
            node_id=node_id,
            node_type=node_type,
            label=reference,
            reference=reference,
            metadata={"source": "operational_reference"},
        )

    def add_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        relationship: str,
    ) -> None:
        self._edges.add((from_node_id, to_node_id, relationship))

    def nodes(self) -> list[RelationshipNode]:
        return [self._nodes[node_id] for node_id in sorted(self._nodes)]

    def edges(self) -> list[RelationshipEdge]:
        return [
            RelationshipEdge(
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                relationship=relationship,
            )
            for from_node_id, to_node_id, relationship in sorted(self._edges)
        ]
