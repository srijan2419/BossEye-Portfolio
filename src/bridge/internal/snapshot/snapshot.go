// Package snapshot defines the pluggable adapter interface used by the
// scheduler to fetch a single JPEG from a camera. Adapter implementations
// for ONVIF, Hikvision ISAPI, Dahua, Axis VAPIX, and raw RTSP (via ffmpeg)
// are registered into this package's registry at init() time.
package snapshot

import "context"

// Camera is the minimal input a snapshot adapter needs. The fields are a
// superset of what any single adapter uses, so every adapter type-asserts
// what it cares about.
type Camera struct {
	Host        string
	Port        int
	Username    string
	Password    string
	SnapshotURI string
	StreamURI   string
	Profile     string
}

// Snapshotter captures one frame from one camera. Implementations must be
// safe to call concurrently from the scheduler's per-camera goroutines.
type Snapshotter interface {
	Name() string
	Capture(ctx context.Context, cam Camera) ([]byte, error)
}

// registry holds all registered adapters keyed by Name(). Adapters register
// themselves via init() in their own source file.
var registry = map[string]Snapshotter{}

// Register adds an adapter to the registry. Safe to call from init().
// Later calls overwrite earlier ones, which is how tests can stub adapters.
func Register(s Snapshotter) {
	registry[s.Name()] = s
}

// Lookup fetches an adapter by its Name(). Returns (adapter, true) on hit,
// (nil, false) on miss.
func Lookup(name string) (Snapshotter, bool) {
	s, ok := registry[name]
	return s, ok
}
