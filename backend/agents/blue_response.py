"""Blue Response: Safe recovery and mitigation recommendation agent."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable
from uuid import uuid4

from backend.agents.ollama_client import OllamaClient
from backend.network.simulation import SimulationController
from backend.schemas.blue import (
    ApprovalStatus,
    DetectionStatus,
    ExecutionResult,
    RecoveryActionType,
    RecoveryRecommendation,
    SentinelReport,
    ValidationResult,
    VerificationReport,
    VerificationStatus,
)


class BlueResponse:
    """Recommends, validates, gates behind approval, and executes safe recovery actions."""

    SYSTEM_PROMPT = """You are NetMindAI's Blue Response mitigation planner.
Given the detected anomalies and affected network entities, propose exactly one safe recovery action from the allowed actions.

Allowed action types:
- "restore_link": Re-enables a disabled network link (target format: "source<->target").
- "restore_node": Re-enables a disabled network node (target format: "node_id").
- "no_action": Used when the network is healthy.

Return ONLY a JSON object in this exact format:
{
  "action_type": "restore_link",
  "target": "router-1<->server-1",
  "reason": "Clear explanation grounded in the observed anomaly",
  "expected_effect": "Expected operational recovery outcome"
}
"""

    def __init__(
        self,
        simulation: SimulationController | Callable[[], SimulationController],
        llm: OllamaClient | None = None,
    ) -> None:
        self._simulation_source = simulation
        self.llm = llm or OllamaClient()
        self.recommendations: dict[str, RecoveryRecommendation] = {}

    @property
    def simulation(self) -> SimulationController:
        """Dynamically resolve active simulation controller."""
        if callable(self._simulation_source):
            return self._simulation_source()
        return self._simulation_source

    def validate_action(
        self,
        action_type: str | RecoveryActionType,
        target: str | None,
    ) -> ValidationResult:
        """Validate an action type and target against the current simulator state."""
        errors: list[str] = []
        action_val = action_type.value if isinstance(action_type, RecoveryActionType) else str(action_type)
        topology = self.simulation.topology

        if action_val == RecoveryActionType.NO_ACTION.value:
            # Check if network actually has disruptions
            has_inactive_node = any(not n.active for n in topology.nodes.values())
            has_inactive_link = any(not l.active for l in topology.links)
            if has_inactive_node or has_inactive_link:
                errors.append("Cannot recommend 'no_action' when network has active disruptions.")
            return ValidationResult(valid=len(errors) == 0, errors=errors)

        if action_val == RecoveryActionType.RESTORE_LINK.value:
            if not target or "<->" not in target:
                errors.append(f"Invalid target '{target}' for restore_link. Expected format 'source<->target'.")
                return ValidationResult(valid=False, errors=errors)

            source, dest = target.split("<->", 1)
            source, dest = source.strip(), dest.strip()

            if source not in topology.nodes:
                errors.append(f"Source node '{source}' does not exist in topology.")
            if dest not in topology.nodes:
                errors.append(f"Target node '{dest}' does not exist in topology.")

            matching_link = next(
                (l for l in topology.links if {l.source, l.target} == {source, dest}),
                None,
            )

            if matching_link is None:
                errors.append(f"Link between '{source}' and '{dest}' does not exist.")
            elif matching_link.active:
                errors.append(f"Link '{source}<->{dest}' is already active. Recommendation is stale.")

            return ValidationResult(valid=len(errors) == 0, errors=errors)

        if action_val == RecoveryActionType.RESTORE_NODE.value:
            if not target or not target.strip():
                errors.append("Target node ID cannot be empty.")
                return ValidationResult(valid=False, errors=errors)

            node_id = target.strip()
            if node_id not in topology.nodes:
                errors.append(f"Node '{node_id}' does not exist in topology.")
            else:
                node = topology.get_node(node_id)
                if node.active:
                    errors.append(f"Node '{node_id}' is already active. Recommendation is stale.")

            return ValidationResult(valid=len(errors) == 0, errors=errors)

        errors.append(f"Unsupported action type '{action_val}'. Allowed: restore_link, restore_node, no_action.")
        return ValidationResult(valid=False, errors=errors)

    def recommend(
        self,
        detection_report: SentinelReport | dict[str, Any],
        use_llm: bool = True,
    ) -> RecoveryRecommendation:
        """Formulate a structured recovery recommendation grounded in detection evidence."""
        if isinstance(detection_report, dict):
            report = SentinelReport.model_validate(detection_report)
        else:
            report = detection_report

        rec_id = f"rec-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)

        # 1. Healthy network case
        if report.status == DetectionStatus.HEALTHY:
            rec = RecoveryRecommendation(
                recommendation_id=rec_id,
                detection_id=report.detection_id,
                action_type=RecoveryActionType.NO_ACTION,
                target=None,
                reason="Network is healthy. No recovery action required.",
                expected_effect="Network maintains normal operating parameters.",
                preconditions=["network_healthy"],
                approval_required=False,
                approval_status=ApprovalStatus.APPROVED,
                validation_result=ValidationResult(valid=True, errors=[]),
                created_at=now,
            )
            self.recommendations[rec_id] = rec
            return rec

        # 2. Determine default deterministic action candidate
        candidate_action: RecoveryActionType
        candidate_target: str
        candidate_reason: str
        candidate_effect: str

        if report.affected_links:
            candidate_action = RecoveryActionType.RESTORE_LINK
            candidate_target = report.affected_links[0]
            candidate_reason = f"Link '{candidate_target}' was detected as disabled in detection {report.detection_id}."
            candidate_effect = f"Re-enables link '{candidate_target}' and restores primary shortest paths."
        elif report.affected_nodes:
            candidate_action = RecoveryActionType.RESTORE_NODE
            candidate_target = report.affected_nodes[0]
            candidate_reason = f"Node '{candidate_target}' was detected as disabled in detection {report.detection_id}."
            candidate_effect = f"Reactivates node '{candidate_target}' and restores traffic flow reachability."
        else:
            # Fallback for investigation required without explicit entity
            candidate_action = RecoveryActionType.NO_ACTION
            candidate_target = ""
            candidate_reason = "No directly disrupted links or nodes identified for automated restoration."
            candidate_effect = "Awaiting manual operator investigation."

        # 3. Optional LLM Formulation with deterministic validation
        action_type = candidate_action
        target = candidate_target
        reason = candidate_reason
        expected_effect = candidate_effect

        if use_llm and self.llm is not None and candidate_action != RecoveryActionType.NO_ACTION:
            llm_schema = {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string"},
                    "target": {"type": "string"},
                    "reason": {"type": "string"},
                    "expected_effect": {"type": "string"},
                },
                "required": ["action_type", "target", "reason", "expected_effect"],
                "additionalProperties": False,
            }

            prompt_data = {
                "detection_id": report.detection_id,
                "findings": report.findings,
                "affected_links": report.affected_links,
                "affected_nodes": report.affected_nodes,
                "affected_flows": report.affected_flows,
                "allowed_actions": ["restore_link", "restore_node", "no_action"],
            }

            try:
                llm_response = self.llm.chat_json(
                    system=self.SYSTEM_PROMPT,
                    prompt=json.dumps(prompt_data, ensure_ascii=False),
                    schema=llm_schema,
                    num_predict=150,
                )
                proposed_action = llm_response.get("action_type")
                proposed_target = llm_response.get("target")
                proposed_reason = llm_response.get("reason")
                proposed_effect = llm_response.get("expected_effect")

                # Validate LLM proposal
                val = self.validate_action(proposed_action, proposed_target)
                if val.valid:
                    action_type = RecoveryActionType(proposed_action)
                    target = proposed_target
                    if isinstance(proposed_reason, str) and proposed_reason.strip():
                        reason = proposed_reason.strip()
                    if isinstance(proposed_effect, str) and proposed_effect.strip():
                        expected_effect = proposed_effect.strip()
            except Exception:
                # Fall back to deterministic proposal
                pass

        val_result = self.validate_action(action_type, target)
        preconditions = ["target_exists", "target_currently_inactive"]

        rec = RecoveryRecommendation(
            recommendation_id=rec_id,
            detection_id=report.detection_id,
            action_type=action_type,
            target=target,
            reason=reason,
            expected_effect=expected_effect,
            preconditions=preconditions,
            approval_required=True,
            approval_status=ApprovalStatus.PENDING,
            validation_result=val_result,
            created_at=now,
        )

        self.recommendations[rec_id] = rec

        # Record recommendation event
        try:
            self.simulation.telemetry.record_event(
                event_type="blue_action_recommended",
                message=f"Blue Response proposed {rec.action_type.value} against '{rec.target}' (pending approval).",
                severity="info",
                source="blue_response",
                entity_id=rec.recommendation_id,
                details=rec.model_dump(mode="json"),
            )
        except Exception:
            pass

        return rec

    def get_recommendation(self, recommendation_id: str) -> RecoveryRecommendation:
        """Lookup a recommendation by ID or raise KeyError."""
        if recommendation_id not in self.recommendations:
            raise KeyError(f"Recommendation '{recommendation_id}' not found.")
        return self.recommendations[recommendation_id]

    def list_recommendations(
        self,
        status: str | ApprovalStatus | None = None,
    ) -> list[RecoveryRecommendation]:
        """List stored recommendations, optionally filtered by approval status."""
        status_val = status.value if isinstance(status, ApprovalStatus) else status
        if status_val is None:
            return list(self.recommendations.values())
        return [
            r for r in self.recommendations.values()
            if r.approval_status.value == status_val
        ]

    def approve_recommendation(
        self,
        recommendation_id: str,
        approver: str = "operator",
        notes: str = "",
    ) -> RecoveryRecommendation:
        """Explicitly approve a pending recovery recommendation after revalidation."""
        rec = self.get_recommendation(recommendation_id)

        if rec.approval_status != ApprovalStatus.PENDING:
            raise RuntimeError(
                f"Recommendation '{recommendation_id}' cannot be approved; "
                f"current status is '{rec.approval_status.value}'."
            )

        # Re-validate action against current simulator state
        val = self.validate_action(rec.action_type, rec.target)
        if not val.valid:
            rec.approval_status = ApprovalStatus.CANCELLED
            rec.validation_result = val
            raise RuntimeError(
                f"Recommendation '{recommendation_id}' is no longer valid: {'; '.join(val.errors)}."
            )

        rec.approval_status = ApprovalStatus.APPROVED
        rec.approver = approver
        rec.approval_notes = notes

        try:
            self.simulation.telemetry.record_event(
                event_type="blue_action_approved",
                message=f"Operator '{approver}' approved recommendation {rec.recommendation_id} ({rec.action_type.value} -> {rec.target}).",
                severity="info",
                source="blue_response",
                entity_id=rec.recommendation_id,
                details=rec.model_dump(mode="json"),
            )
        except Exception:
            pass

        return rec

    def reject_recommendation(
        self,
        recommendation_id: str,
        approver: str = "operator",
        reason: str = "",
    ) -> RecoveryRecommendation:
        """Explicitly reject a pending recovery recommendation."""
        rec = self.get_recommendation(recommendation_id)

        if rec.approval_status != ApprovalStatus.PENDING:
            raise RuntimeError(
                f"Recommendation '{recommendation_id}' cannot be rejected; "
                f"current status is '{rec.approval_status.value}'."
            )

        rec.approval_status = ApprovalStatus.REJECTED
        rec.approver = approver
        rec.approval_notes = reason

        try:
            self.simulation.telemetry.record_event(
                event_type="blue_action_rejected",
                message=f"Operator '{approver}' rejected recommendation {rec.recommendation_id}: {reason}",
                severity="info",
                source="blue_response",
                entity_id=rec.recommendation_id,
                details=rec.model_dump(mode="json"),
            )
        except Exception:
            pass

        return rec

    def execute_approved(self, recommendation_id: str) -> ExecutionResult:
        """Execute an explicitly approved recommendation and verify recovery outcome."""
        rec = self.get_recommendation(recommendation_id)

        # 1. Check Approval Requirement
        if rec.approval_status != ApprovalStatus.APPROVED:
            raise PermissionError(
                f"Execution rejected: Recommendation '{recommendation_id}' requires explicit approval "
                f"before execution (current status: '{rec.approval_status.value}')."
            )

        # 2. Re-validate against current simulator state
        val = self.validate_action(rec.action_type, rec.target)
        if not val.valid:
            rec.approval_status = ApprovalStatus.CANCELLED
            rec.validation_result = val
            raise RuntimeError(
                f"Execution aborted: Recommendation '{recommendation_id}' failed pre-execution validation: "
                f"{'; '.join(val.errors)}."
            )

        topology = self.simulation.topology
        now = datetime.now(timezone.utc)

        # 3. Execute recovery operation
        if rec.action_type == RecoveryActionType.RESTORE_LINK:
            source, dest = rec.target.split("<->", 1)
            topology.set_link_status(source.strip(), dest.strip(), active=True)
            action_desc = f"Re-enabled link {rec.target}"

        elif rec.action_type == RecoveryActionType.RESTORE_NODE:
            topology.set_node_status(rec.target.strip(), active=True)
            action_desc = f"Reactivated node {rec.target}"

        elif rec.action_type == RecoveryActionType.NO_ACTION:
            action_desc = "No operation executed"

        rec.approval_status = ApprovalStatus.EXECUTED

        try:
            self.simulation.telemetry.record_event(
                event_type="blue_recovery_executed",
                message=f"Blue Response executed {rec.action_type.value} on '{rec.target}'.",
                severity="info",
                source="blue_response",
                entity_id=rec.recommendation_id,
                details={"recommendation": rec.model_dump(mode="json"), "action_description": action_desc},
            )
        except Exception:
            pass

        # 4. Post-recovery reachability and topology verification
        target_active = False
        route_after: list[str] | None = None

        if rec.action_type == RecoveryActionType.RESTORE_LINK:
            source, dest = rec.target.split("<->", 1)
            matching_link = next(
                (l for l in topology.links if {l.source, l.target} == {source.strip(), dest.strip()}),
                None,
            )
            target_active = matching_link.active if matching_link else False
            route_after = topology.shortest_path("client-1", dest.strip())

        elif rec.action_type == RecoveryActionType.RESTORE_NODE:
            node = topology.get_node(rec.target.strip())
            target_active = node.active if node else False
            route_after = topology.shortest_path("client-1", rec.target.strip())

        elif rec.action_type == RecoveryActionType.NO_ACTION:
            target_active = True

        # Inspect all traffic flows
        try:
            flows = self.simulation.traffic_engine.all_flows()
            reachable_count = sum(1 for f in flows if f["reachable"] and f["active"])
            total_active_flows = sum(1 for f in flows if f["active"])
        except Exception:
            reachable_count = 0
            total_active_flows = 0

        # Verification status determination
        if target_active and (reachable_count == total_active_flows):
            ver_status = VerificationStatus.VERIFIED_SUCCESS
        elif target_active and (reachable_count < total_active_flows):
            ver_status = VerificationStatus.PARTIAL_RECOVERY
        else:
            ver_status = VerificationStatus.VERIFICATION_FAILED

        verification = VerificationReport(
            status=ver_status,
            target_active=target_active,
            route_after=route_after,
            reachable_flows=reachable_count,
            details={
                "action_description": action_desc,
                "total_active_flows": total_active_flows,
                "reachable_active_flows": reachable_count,
            },
        )

        try:
            self.simulation.telemetry.record_event(
                event_type="blue_recovery_verified",
                message=f"Recovery verification for {rec.recommendation_id}: {ver_status.value}.",
                severity="info" if ver_status == VerificationStatus.VERIFIED_SUCCESS else "warning",
                source="blue_response",
                entity_id=rec.recommendation_id,
                details=verification.model_dump(mode="json"),
            )
        except Exception:
            pass

        return ExecutionResult(
            recommendation_id=rec.recommendation_id,
            action_type=rec.action_type,
            target=rec.target,
            execution_status="success",
            verification=verification,
            timestamp=now,
        )
