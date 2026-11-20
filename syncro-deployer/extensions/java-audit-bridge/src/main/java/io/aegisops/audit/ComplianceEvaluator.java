package io.aegisops.audit;

import java.util.ArrayList;
import java.util.List;

/**
 * Evaluates Kafka DevSecOps CloudEvents for SOC2 / CIS Azure compliance evidence
 * and flags high-severity governance anomalies for SIEM escalation.
 */
public class ComplianceEvaluator {

    public record EvaluationReport(
            String eventId,
            boolean compliant,
            String siemSeverity,
            List<String> controlNotes
    ) {}

    public EvaluationReport evaluate(CloudEventRecord event) {
        List<String> notes = new ArrayList<>();
        boolean compliant = true;
        String severity = "INFO";

        if (event.type() == null || !event.type().startsWith("io.aegisops.")) {
            compliant = false;
            severity = "HIGH";
            notes.add("CloudEvent type violates io.aegisops.* namespace contract");
        }

        if ("io.aegisops.destroy.completed".equals(event.type())) {
            severity = "MEDIUM";
            notes.add("SOC2 CC8.1: Ephemeral destruction recorded in immutable audit sink");
            if (event.productionTier() && !event.breakGlassApproved()) {
                compliant = false;
                severity = "CRITICAL";
                notes.add("ALERT: Production destruction without break-glass dual-approval detected");
            }
        }

        if (event.actor() == null || event.actor().isBlank()) {
            compliant = false;
            severity = "HIGH";
            notes.add("Missing non-repudiation actor identity on audit event");
        }

        if (notes.isEmpty()) {
            notes.add("SOC2/CIS Azure audit verification passed");
        }

        return new EvaluationReport(event.id(), compliant, severity, List.copyOf(notes));
    }
}
