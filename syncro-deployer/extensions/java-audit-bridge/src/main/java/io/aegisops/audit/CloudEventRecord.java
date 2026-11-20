package io.aegisops.audit;

import java.time.Instant;

/**
 * Immutable CloudEvents 1.0 audit record consumed from Apache Kafka topics
 * (aegis.audit.events and aegis.destroy.events).
 */
public record CloudEventRecord(
        String id,
        String type,
        String source,
        String subject,
        String projectId,
        String actor,
        boolean productionTier,
        boolean breakGlassApproved,
        Instant timestamp
) {}
