FROM maven:3.9-eclipse-temurin-17-alpine AS builder
WORKDIR /build
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:17-jre-alpine
RUN addgroup -g 10001 aegis && adduser -u 10001 -G aegis -D aegis
WORKDIR /app
COPY --from=builder /build/target/java-audit-bridge-0.1.0.jar /app/app.jar
USER 10001:10001
EXPOSE 9103
ENTRYPOINT ["java", "-cp", "/app/app.jar", "io.aegisops.audit.AuditBridgeApplication"]
