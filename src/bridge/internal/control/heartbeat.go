package control

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

// StateStore is the narrow interface the Poller needs. It is intentionally
// decoupled from internal/state.Store so this package can be tested in
// isolation and main.go (Task 11.4) wires a real store into it.
type StateStore interface {
	ListBackendCameraUUIDs() ([]string, error)
	UpsertBackendCamera(backendUUID, name string) error
	UpsertBackendCameraFull(backendUUID, name, adapterType, host string, port int, snapshotURI, username, password string) error
	DeleteBackendCamera(backendUUID string) error
	GetMeta(k string) (string, error)
	SetMeta(k, v string) error
}

// Poller heartbeats + pulls config on a fixed interval.
type Poller struct {
	BackendURL string
	AgentJWT   string
	AgentVer   string
	Store      StateStore
	Interval   time.Duration // default 30s
	HTTP       *http.Client
}

type heartbeatRequest struct {
	AgentVersion     string `json:"agent_version"`
	CamerasOnline    int    `json:"cameras_online"`
	FramesLastMinute int    `json:"frames_last_minute"`
}

type heartbeatResponse struct {
	OK                 bool   `json:"ok"`
	TargetAgentVersion string `json:"target_agent_version"`
}

type configCamera struct {
	CameraUUID             string `json:"camera_uuid"`
	Name                   string `json:"name"`
	CaptureIntervalSeconds int    `json:"capture_interval_seconds"`
	AdapterType            string `json:"adapter_type,omitempty"`
	Host                   string `json:"host,omitempty"`
	Port                   int    `json:"port,omitempty"`
	SnapshotURI            string `json:"snapshot_uri,omitempty"`
	Username               string `json:"username,omitempty"`
	Password               string `json:"password,omitempty"`
}

type configResponse struct {
	Cameras                  []configCamera `json:"cameras"`
	TargetAgentVersion       string         `json:"target_agent_version"`
	HeartbeatIntervalSeconds int            `json:"heartbeat_interval_seconds"`
}

func (p *Poller) httpClient() *http.Client {
	if p.HTTP != nil {
		return p.HTTP
	}
	return &http.Client{Timeout: 15 * time.Second}
}

// Heartbeat POSTs one heartbeat and returns the backend's target_agent_version.
func (p *Poller) Heartbeat(ctx context.Context) (string, error) {
	cams, _ := p.Store.ListBackendCameraUUIDs()
	body, _ := json.Marshal(heartbeatRequest{
		AgentVersion:  p.AgentVer,
		CamerasOnline: len(cams),
	})
	req, err := http.NewRequestWithContext(ctx, "POST", p.BackendURL+"/bridge/heartbeat", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+p.AgentJWT)
	req.Header.Set("Content-Type", "application/json")

	resp, err := p.httpClient().Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return "", fmt.Errorf("heartbeat: %d %s: %s", resp.StatusCode, resp.Status, string(b))
	}
	var hr heartbeatResponse
	if err := json.NewDecoder(resp.Body).Decode(&hr); err != nil {
		return "", err
	}
	return hr.TargetAgentVersion, nil
}

// FetchConfig GETs /bridge/config and diffs against local state, upserting
// new/updated cameras and deleting any local camera whose backend_camera_uuid
// is no longer in the response.
func (p *Poller) FetchConfig(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "GET", p.BackendURL+"/bridge/config", nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+p.AgentJWT)

	resp, err := p.httpClient().Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("config: %s", resp.Status)
	}
	var cr configResponse
	if err := json.NewDecoder(resp.Body).Decode(&cr); err != nil {
		return err
	}

	wanted := map[string]bool{}
	for _, c := range cr.Cameras {
		wanted[c.CameraUUID] = true
		if c.AdapterType != "" {
			if err := p.Store.UpsertBackendCameraFull(c.CameraUUID, c.Name, c.AdapterType, c.Host, c.Port, c.SnapshotURI, c.Username, c.Password); err != nil {
				log.Printf("control: upsert full camera %s: %v", c.CameraUUID, err)
			}
		} else {
			if err := p.Store.UpsertBackendCamera(c.CameraUUID, c.Name); err != nil {
				log.Printf("control: upsert camera %s: %v", c.CameraUUID, err)
			}
		}
	}
	have, _ := p.Store.ListBackendCameraUUIDs()
	for _, uuid := range have {
		if !wanted[uuid] {
			if err := p.Store.DeleteBackendCamera(uuid); err != nil {
				log.Printf("control: delete camera %s: %v", uuid, err)
			}
		}
	}
	return nil
}

// Run loops Heartbeat + FetchConfig at Interval until ctx is done.
func (p *Poller) Run(ctx context.Context) {
	iv := p.Interval
	if iv == 0 {
		iv = 30 * time.Second
	}
	tick := func() {
		if _, err := p.Heartbeat(ctx); err != nil {
			log.Printf("control: heartbeat error: %v", err)
		}
		if err := p.FetchConfig(ctx); err != nil {
			log.Printf("control: fetch config error: %v", err)
		}
	}
	tick()
	t := time.NewTicker(iv)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			tick()
		}
	}
}
