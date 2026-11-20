package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"time"
)

type ResourceSpec struct {
	ID          string `json:"id"`
	Type        string `json:"type"`
	DesiredHash string `json:"desired_hash"`
	LiveHash    string `json:"live_hash"`
	HasLock     bool   `json:"has_lock"`
}

type HookRequest struct {
	CorrelationID string         `json:"correlation_id"`
	ProjectID     string         `json:"project_id"`
	EnvironmentID string         `json:"environment_id"`
	Resources     []ResourceSpec `json:"resources"`
}

type Finding struct {
	RuleID      string `json:"rule_id"`
	Severity    string `json:"severity"`
	Title       string `json:"title"`
	Resource    string `json:"resource"`
	Remediation string `json:"remediation"`
}

type HookResponse struct {
	Allowed     bool              `json:"allowed"`
	Summary     string            `json:"summary"`
	Findings    []Finding         `json:"findings"`
	Annotations map[string]string `json:"annotations"`
}

// EvaluateDrift concurrently checks desired vs live Azure/K8s state hashes across goroutines.
func EvaluateDrift(resources []ResourceSpec) []Finding {
	var (
		wg       sync.WaitGroup
		mu       sync.Mutex
		findings []Finding
	)

	for _, res := range resources {
		wg.Add(1)
		go func(r ResourceSpec) {
			defer wg.Done()
			if r.DesiredHash != r.LiveHash {
				mu.Lock()
				findings = append(findings, Finding{
					RuleID:      "DRIFT-AZ-001",
					Severity:    "HIGH",
					Title:       fmt.Sprintf("Configuration drift detected on %s (%s)", r.ID, r.Type),
					Resource:    r.ID,
					Remediation: "Run `aegis infra tf-plan` and reconcile live Azure state.",
				})
				mu.Unlock()
			}
		}(res)
	}
	wg.Wait()
	return findings
}

func newMux() *http.ServeMux {
	mux := http.NewServeMux()
	started := time.Now()

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"id":             "go-drift-scanner",
			"language":       "go",
			"status":         "healthy",
			"uptime_seconds": int64(time.Since(started).Seconds()),
		})
	})

	mux.HandleFunc("/hooks/drift_check", func(w http.ResponseWriter, r *http.Request) {
		var req HookRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "invalid json payload", http.StatusBadRequest)
			return
		}
		findings := EvaluateDrift(req.Resources)
		resp := HookResponse{
			Allowed:  len(findings) == 0,
			Summary:  fmt.Sprintf("Scanned %d Azure/K8s resources; %d drift finding(s)", len(req.Resources), len(findings)),
			Findings: findings,
			Annotations: map[string]string{
				"extension": "go-drift-scanner",
				"contract":  "aegisops.v1.ExtensionService",
			},
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	})

	return mux
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "9101"
	}
	log.Printf("AegisOps Go Drift Scanner listening on :%s", port)
	if err := http.ListenAndServe(":"+port, newMux()); err != nil {
		log.Fatal(err)
	}
}
