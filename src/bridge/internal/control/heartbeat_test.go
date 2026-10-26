package control

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type fakeStore struct {
	mu      sync.Mutex
	cameras map[string]FakeCamera
	meta    map[string]string
}

type FakeCamera struct {
	UUID              string
	Name              string
	Adapter           string
	Host              string
	Port              int
	Username          string
	Password          string
	BackendCameraUUID string
}

func newFakeStore() *fakeStore {
	return &fakeStore{
		cameras: map[string]FakeCamera{},
		meta:    map[string]string{},
	}
}

func (f *fakeStore) ListBackendCameraUUIDs() ([]string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]string, 0, len(f.cameras))
	for _, c := range f.cameras {
		if c.BackendCameraUUID != "" {
			out = append(out, c.BackendCameraUUID)
		}
	}
	return out, nil
}

func (f *fakeStore) UpsertBackendCamera(backendUUID, name string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	c := f.cameras[backendUUID]
	c.BackendCameraUUID = backendUUID
	c.Name = name
	f.cameras[backendUUID] = c
	return nil
}

func (f *fakeStore) UpsertBackendCameraFull(backendUUID, name, adapterType, host string, port int, snapshotURI, username, password string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	c := f.cameras[backendUUID]
	c.UUID = backendUUID
	c.BackendCameraUUID = backendUUID
	c.Name = name
	c.Adapter = adapterType
	c.Host = host
	c.Port = port
	c.Username = username
	c.Password = password
	f.cameras[backendUUID] = c
	return nil
}

func (f *fakeStore) DeleteBackendCamera(backendUUID string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	delete(f.cameras, backendUUID)
	return nil
}

func (f *fakeStore) GetMeta(k string) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.meta[k], nil
}

func (f *fakeStore) SetMeta(k, v string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.meta[k] = v
	return nil
}

func (f *fakeStore) CameraCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.cameras)
}

func TestHeartbeatPostsAndReceivesTargetVersion(t *testing.T) {
	var gotAuth string
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/bridge/heartbeat":
			gotAuth = r.Header.Get("Authorization")
			json.NewDecoder(r.Body).Decode(&gotBody)
			w.Header().Set("Content-Type", "application/json")
			w.Write([]byte(`{"ok":true,"target_agent_version":"1.2.3"}`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	store := newFakeStore()
	p := &Poller{
		BackendURL: srv.URL,
		AgentJWT:   "abc",
		Store:      store,
		AgentVer:   "1.0.0",
	}
	target, err := p.Heartbeat(context.Background())
	require.NoError(t, err)
	require.Equal(t, "1.2.3", target)
	require.Equal(t, "Bearer abc", gotAuth)
	require.Equal(t, "1.0.0", gotBody["agent_version"])
}

func TestFetchConfigDiffsLocalState(t *testing.T) {
	// Backend returns 2 cameras; local state has 1 (cam-old).
	// Expect: cam-old deleted, cam-1 and cam-2 upserted.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/bridge/config" {
			http.NotFound(w, r)
			return
		}
		w.Write([]byte(`{"cameras":[
            {"camera_uuid":"cam-1","name":"Front","capture_interval_seconds":60},
            {"camera_uuid":"cam-2","name":"Back","capture_interval_seconds":60}
        ],"target_agent_version":"1.0.0","heartbeat_interval_seconds":30}`))
	}))
	defer srv.Close()

	store := newFakeStore()
	store.UpsertBackendCamera("cam-old", "Stale")
	require.Equal(t, 1, store.CameraCount())

	p := &Poller{
		BackendURL: srv.URL,
		AgentJWT:   "j",
		Store:      store,
	}
	require.NoError(t, p.FetchConfig(context.Background()))

	// cam-old should be gone, cam-1 and cam-2 should be present
	uuids, _ := store.ListBackendCameraUUIDs()
	require.ElementsMatch(t, []string{"cam-1", "cam-2"}, uuids)
}

// TestFetchConfigPreservesLocalOnlyCameras verifies that cameras whose
// BackendCameraUUID is empty (added via the local web UI and not yet known to
// the backend) are never deleted by the reconcile loop, even when the backend
// returns an empty camera list.
//
// This is the regression test for the smoke-test failure: a local-only camera
// disappeared from SQLite after bridge restart → FetchConfig tick.  The root
// cause was that wire.go's webuiStoreAdapter.UpsertCamera set
// BackendCameraUUID = c.UUID for every camera it persisted, causing
// ListBackendCameraUUIDs to return local UUIDs that the backend then
// "deleted" via the reconcile diff.  The fix is to leave BackendCameraUUID
// empty for web-UI-created cameras so that this loop never touches them.
func TestFetchConfigPreservesLocalOnlyCameras(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"cameras":[],"target_agent_version":"1.0.0","heartbeat_interval_seconds":30}`))
	}))
	defer srv.Close()

	store := newFakeStore()
	// A camera that came from the backend — reconcile may delete it if backend removes it.
	store.mu.Lock()
	store.cameras["backend-1"] = FakeCamera{UUID: "backend-1", BackendCameraUUID: "backend-1", Name: "Lobby"}
	// A camera added via the local web UI — BackendCameraUUID is empty.
	store.cameras["local-only-1"] = FakeCamera{UUID: "local-only-1", BackendCameraUUID: "", Name: "Side Door"}
	store.mu.Unlock()

	p := &Poller{
		BackendURL: srv.URL,
		AgentJWT:   "j",
		Store:      store,
	}
	require.NoError(t, p.FetchConfig(context.Background()))

	// backend-1 was in local state but NOT in the backend response → must be deleted.
	store.mu.Lock()
	_, backendStillExists := store.cameras["backend-1"]
	_, localStillExists := store.cameras["local-only-1"]
	store.mu.Unlock()

	require.False(t, backendStillExists, "backend-1 should have been removed by reconcile")
	require.True(t, localStillExists, "local-only-1 must NOT be deleted by reconcile")
}

func TestRunLoopExitsOnContextDone(t *testing.T) {
	var beats int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/bridge/heartbeat":
			atomic.AddInt32(&beats, 1)
			w.Write([]byte(`{"ok":true,"target_agent_version":"1.0.0"}`))
		case "/bridge/config":
			w.Write([]byte(`{"cameras":[],"target_agent_version":"1.0.0","heartbeat_interval_seconds":30}`))
		}
	}))
	defer srv.Close()

	store := newFakeStore()
	p := &Poller{
		BackendURL: srv.URL,
		AgentJWT:   "j",
		Store:      store,
		Interval:   50 * time.Millisecond,
	}
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	p.Run(ctx)
	require.GreaterOrEqual(t, atomic.LoadInt32(&beats), int32(2))
}
