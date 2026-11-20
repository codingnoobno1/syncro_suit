package io.aegisops.audit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class ComplianceEvaluatorTest {

    private final ComplianceEvaluator evaluator = new ComplianceEvaluator();

    @Test
    void approvesCompliantEphemeralDestroyEvent() {
        CloudEventRecord evt = new CloudEventRecord(
                "evt-101",
                "io.aegisops.destroy.completed",
                "/aegisops/control-plane",
                "env/env-pr-412",
                "payments-core",
                "ttl-reaper",
                false,
                false,
                Instant.now()
        );
        var report = evaluator.evaluate(evt);
        assertTrue(report.compliant());
        assertEquals("MEDIUM", report.siemSeverity());
    }

    @Test
    void flagsUnapprovedProductionDestructionAsCritical() {
        CloudEventRecord evt = new CloudEventRecord(
                "evt-999",
                "io.aegisops.destroy.completed",
                "/aegisops/control-plane",
                "env/env-prod-core",
                "payments-core",
                "rogue-script",
                true,
                false,
                Instant.now()
        );
        var report = evaluator.evaluate(evt);
        assertFalse(report.compliant());
        assertEquals("CRITICAL", report.siemSeverity());
    }
}
