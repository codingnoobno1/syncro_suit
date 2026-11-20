import http from "node:http";
import { evaluatePullRequestGate, type PullRequestEvent } from "./policy.js";

const PORT = Number(process.env.PORT ?? 9102);

export function createWebhookServer(): http.Server {
  return http.createServer((req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ id: "ts-policy-webhook", language: "typescript", status: "healthy" }));
      return;
    }

    if (req.method === "POST" && req.url === "/hooks/pr_gate") {
      let raw = "";
      req.on("data", (chunk) => {
        raw += String(chunk);
      });
      req.on("end", () => {
        try {
          const payload = JSON.parse(raw) as PullRequestEvent;
          const result = evaluatePullRequestGate(payload);
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(result));
        } catch {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Invalid JSON payload" }));
        }
      });
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Not found" }));
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  createWebhookServer().listen(PORT, () => {
    console.log(`AegisOps TypeScript Policy Webhook listening on :${PORT}`);
  });
}
