package io.aegisops.audit;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

/**
 * Lightweight Java 17 HTTP & Kafka Audit Bridge Extension entrypoint
 * (drop-in compatible with Spring Boot / Spring Kafka enterprise deployments).
 */
public class AuditBridgeApplication {

    public static void main(String[] args) throws IOException {
        if (args.length > 0 && "--self-test".equals(args[0])) {
            ComplianceEvaluator evaluator = new ComplianceEvaluator();
            var ok = evaluator.evaluate(new CloudEventRecord(
                    "evt-101", "io.aegisops.destroy.completed", "/aegisops/control-plane",
                    "env/env-pr-412", "payments-core", "ttl-reaper", false, false, Instant.now()));
            var bad = evaluator.evaluate(new CloudEventRecord(
                    "evt-999", "io.aegisops.destroy.completed", "/aegisops/control-plane",
                    "env/env-prod-core", "payments-core", "rogue-script", true, false, Instant.now()));
            if (!ok.compliant() || bad.compliant() || !"CRITICAL".equals(bad.siemSeverity())) {
                throw new AssertionError("Java ComplianceEvaluator self-test failed");
            }
            System.out.println("PASS: Java 17 ComplianceEvaluator self-test (2/2 assertions passed)");
            return;
        }
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "9103"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);

        server.createContext("/health", exchange -> {
            byte[] body = "{\"id\":\"java-audit-bridge\",\"language\":\"java\",\"status\":\"healthy\"}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });

        server.setExecutor(null);
        System.out.printf("AegisOps Java 17 Audit Bridge listening on :%d%n", port);
        server.start();
    }
}
