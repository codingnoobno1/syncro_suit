package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEvaluateDriftAndHookEndpoint(t *testing.T) {
	payload := HookRequest{
		ProjectID:     "edge-gateway",
		EnvironmentID: "env-staging-edge",
		Resources: []ResourceSpec{
			{ID: "aks-edge-staging", Type: "Microsoft.ContainerService/managedClusters", DesiredHash: "aaa", LiveHash: "aaa"},
			{ID: "nsg-edge-staging", Type: "Microsoft.Network/networkSecurityGroups", DesiredHash: "bbb", LiveHash: "drifted"},
		},
	}
	body, _ := json.Marshal(payload)
	req := httptest.NewRequest(http.MethodPost, "/hooks/drift_check", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	newMux().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d", rec.Code)
	}
	var resp HookResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.Allowed {
		t.Fatalf("expected drift finding to set allowed=false")
	}
	if len(resp.Findings) != 1 || resp.Findings[0].Resource != "nsg-edge-staging" {
		t.Fatalf("unexpected findings: %+v", resp.Findings)
	}
}
