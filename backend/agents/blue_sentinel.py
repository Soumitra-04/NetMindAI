"""Blue Sentinel: Independent detection agent for simulated network disruptions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from typing import Any, Callable
from uuid import uuid4

from backend.agents.ollama_client import OllamaClient
from backend.network.simulation import SimulationController
from backend.schemas.blue import (
    DetectionStatus,
    ModelInferenceStatus,
    SentinelEvidence,
    SentinelReport,
)
from backend.services.inference_service import ModelInferenceService


class BlueSentinel:
    """Independently detects simulated network disruptions and suspicious conditions."""

    SYSTEM_PROMPT = """You are NetMindAI's Blue Sentinel network monitoring analyst.
Analyze the observed network state and telemetry evidence to provide an assessment.
Return ONLY a JSON object in this exact format:
{
  "assessment": "Concise summary of findings",
  "recommended_action": "Recommended remediation"
}
"""

    def __init__(
        self,
        simulation: SimulationController | Callable[[], SimulationController],
        llm: OllamaClient | None = None,
        inference_service: ModelInferenceService | None = None,
    ) -> None:
        self._simulation_source = simulation
        self.llm = llm or OllamaClient()
        self.inference_service = inference_service

    @property
    def simulation(self) -> SimulationController:
        """Dynamically resolve active simulation controller."""
        if callable(self._simulation_source):
            return self._simulation_source()
        return self._simulation_source

    def detect(
        self,
        flow_features: dict[str, Any] | list[dict[str, Any]] | None = None,
        use_llm: bool = True,
    ) -> SentinelReport:
        """Run independent detection across topology, traffic, telemetry, and optional ML."""
        detection_id = f"det-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        topology = self.simulation.topology
        traffic_engine = self.simulation.traffic_engine
        telemetry = self.simulation.telemetry

        errors_or_limitations: list[str] = []

        # 1. Independent Observable State Inspection
        # Inspect topology nodes
        inactive_nodes: list[dict[str, Any]] = [
            asdict(node) for node in topology.nodes.values() if not node.active
        ]

        # Inspect topology links
        inactive_links: list[dict[str, Any]] = [
            asdict(link) for link in topology.links if not link.active
        ]

        # Inspect registered traffic flows and their reachability
        try:
            all_flows = traffic_engine.all_flows()
        except Exception as exc:
            all_flows = []
            errors_or_limitations.append(f"Failed to inspect traffic flows: {exc}")

        unreachable_flows: list[dict[str, Any]] = [
            flow for flow in all_flows if flow["active"] and not flow["reachable"]
        ]

        # Contextual telemetry evidence (recent events)
        contextual_events: list[dict[str, Any]] = []
        try:
            recent_events = telemetry.get_events(limit=20)
            contextual_events = [
                e for e in recent_events
                if e["severity"] in ("warning", "error", "critical")
                or e["source"] == "red_agent"
            ]
        except Exception as exc:
            errors_or_limitations.append(f"Failed to query telemetry events: {exc}")

        # Metrics summary
        try:
            metrics_summary = telemetry.collect_metrics()
        except Exception as exc:
            metrics_summary = {}
            errors_or_limitations.append(f"Failed to collect telemetry metrics: {exc}")

        evidence = SentinelEvidence(
            inactive_nodes=inactive_nodes,
            inactive_links=inactive_links,
            unreachable_flows=unreachable_flows,
            contextual_events=contextual_events,
            metrics_summary=metrics_summary,
        )

        affected_nodes: list[str] = [n["id"] for n in inactive_nodes]
        affected_links: list[str] = [
            f"{l['source']}<->{l['target']}" for l in inactive_links
        ]
        affected_flows: list[str] = [f["id"] for f in unreachable_flows]

        # 2. Random Forest Model Evaluation
        ml_finding: str | None = None
        if flow_features is not None:
            if self.inference_service is None:
                try:
                    self.inference_service = ModelInferenceService()
                except Exception as exc:
                    errors_or_limitations.append(f"Inference service initialization failed: {exc}")

            if self.inference_service is not None:
                try:
                    ml_result = self.inference_service.predict(flow_features)
                    # If batch, check any prediction == 1
                    is_attack = False
                    if isinstance(ml_result, list):
                        is_attack = any(r["prediction"] == 1 for r in ml_result)
                        attack_prob = max(r["attack_probability"] for r in ml_result)
                    else:
                        is_attack = ml_result["prediction"] == 1
                        attack_prob = ml_result["attack_probability"]

                    model_inference = ModelInferenceStatus(
                        status="completed",
                        reason=None,
                        result=ml_result if isinstance(ml_result, dict) else {"batch": ml_result},
                    )

                    if is_attack:
                        ml_finding = (
                            f"ML classifier flagged potential intrusion: "
                            f"attack probability {attack_prob:.4f} exceeds threshold "
                            f"{self.inference_service.threshold:.4f}."
                        )
                except Exception as exc:
                    model_inference = ModelInferenceStatus(
                        status="error",
                        reason=str(exc),
                        result=None,
                    )
                    errors_or_limitations.append(f"ML inference evaluation failed: {exc}")
            else:
                model_inference = ModelInferenceStatus(
                    status="unavailable",
                    reason="Model inference service is not available.",
                    result=None,
                )
        else:
            model_inference = ModelInferenceStatus(
                status="unavailable",
                reason=(
                    "Live simulator operates at graph topology abstraction without generating "
                    "the 67 CICIDS packet-timing/flag features required by the Random Forest model. "
                    "Per project constraints, missing features are never fabricated or zero-filled."
                ),
                result=None,
            )

        # 3. Deterministic Findings Synthesis
        findings: list[str] = []

        if inactive_nodes or inactive_links or unreachable_flows:
            status = DetectionStatus.ANOMALY_DETECTED
            severity = "critical" if inactive_nodes or unreachable_flows else "warning"
            confidence = 1.0

            for node in inactive_nodes:
                findings.append(f"Simulated node '{node['id']}' ({node['name']}) is disabled.")

            for link in inactive_links:
                findings.append(f"Simulated link '{link['source']}<->{link['target']}' is disabled.")

            for flow in unreachable_flows:
                findings.append(f"Traffic flow '{flow['id']}' ({flow['source']} -> {flow['destination']}) is unreachable.")

            if ml_finding:
                findings.append(f"[ML Finding] {ml_finding}")

            # Deterministic recommended action
            if inactive_links:
                recommended_action = f"Restore disabled link {affected_links[0]}."
            elif inactive_nodes:
                recommended_action = f"Reactivate disabled node {affected_nodes[0]}."
            else:
                recommended_action = "Investigate route path obstruction for unreachable flows."

        elif ml_finding:
            status = DetectionStatus.INVESTIGATION_REQUIRED
            severity = "warning"
            confidence = 0.85
            findings.append(f"[ML Finding] {ml_finding}")
            recommended_action = "Investigate suspicious traffic flows flagged by intrusion detection model."

        else:
            status = DetectionStatus.HEALTHY
            severity = "info"
            confidence = 1.0
            findings.append(
                f"All {len(topology.nodes)} network nodes and {len(topology.links)} links are active."
            )
            findings.append(
                f"All {len(all_flows)} traffic flows are reachable with active routes."
            )
            recommended_action = "No recovery action required. Network is operating normally."

        # 4. Optional LLM Evidence Synthesis / Interpretation
        if use_llm and self.llm is not None:
            llm_schema = {
                "type": "object",
                "properties": {
                    "assessment": {"type": "string"},
                    "recommended_action": {"type": "string"},
                },
                "required": ["assessment", "recommended_action"],
                "additionalProperties": False,
            }

            prompt_data = {
                "detection_id": detection_id,
                "status": status.value,
                "inactive_nodes": affected_nodes,
                "inactive_links": affected_links,
                "unreachable_flows": affected_flows,
                "deterministic_findings": findings,
            }

            try:
                llm_response = self.llm.chat_json(
                    system=self.SYSTEM_PROMPT,
                    prompt=json.dumps(prompt_data, ensure_ascii=False),
                    schema=llm_schema,
                    num_predict=150,
                )
                assessment = llm_response.get("assessment")
                llm_rec = llm_response.get("recommended_action")
                if isinstance(assessment, str) and assessment.strip():
                    findings.append(f"[LLM Assessment] {assessment.strip()}")
                if isinstance(llm_rec, str) and llm_rec.strip() and status != DetectionStatus.HEALTHY:
                    recommended_action = llm_rec.strip()
            except Exception as exc:
                errors_or_limitations.append(f"LLM evidence interpretation omitted: {exc}")

        report = SentinelReport(
            detection_id=detection_id,
            timestamp=now,
            status=status,
            findings=findings,
            affected_nodes=affected_nodes,
            affected_links=affected_links,
            affected_flows=affected_flows,
            evidence=evidence,
            severity=severity,
            confidence=confidence,
            recommended_action=recommended_action,
            model_inference=model_inference,
            errors_or_limitations=errors_or_limitations,
        )

        # 5. Record Detection Event to Telemetry
        try:
            telemetry.record_event(
                event_type="blue_detection_completed",
                message=f"Blue Sentinel detection {report.detection_id}: {report.status.value}.",
                severity=report.severity,
                source="blue_sentinel",
                entity_id=report.detection_id,
                details=report.model_dump(mode="json"),
            )
        except Exception as exc:
            errors_or_limitations.append(f"Failed to record detection event: {exc}")

        return report
