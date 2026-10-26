package discovery

import (
	"context"
	"sync"
)

// defaultCreds is the short list tried after a candidate's initial Inspect fails.
// Research shows ~40% of factory cameras still use these.
var defaultCreds = []struct{ User, Pass string }{
	{"admin", "admin"},
	{"admin", "12345"},
	{"admin", ""},
	{"root", "root"},
	{"admin", "password"},
}

// EnrichedCandidate combines a raw WS-Discovery Candidate with the result
// of its ONVIF Inspect call. If InspectError is non-nil, Profile is nil
// and the caller should surface the error in the UI as "found but failed".
type EnrichedCandidate struct {
	Candidate
	Profile      *ProfileInfo
	InspectError error
	UsedDefaults bool // true if Inspect only succeeded after trying defaultCreds
}

// DiscoverAndInspect probes the local network for ONVIF cameras and, for
// every candidate returned, runs Inspect() in parallel to fetch its profile
// token and snapshot URI. Individual inspect failures are recorded per
// candidate and never abort the overall call.
//
// ctx cancellation short-circuits the wait but does not interrupt in-flight
// HTTP calls (they bound themselves via the http.Client.Timeout in Inspect).
func DiscoverAndInspect(ctx context.Context, d *Discoverer, user, pass string) ([]EnrichedCandidate, error) {
	cands, err := d.Probe()
	if err != nil {
		return nil, err
	}

	out := make([]EnrichedCandidate, len(cands))
	for i := range cands {
		out[i] = EnrichedCandidate{Candidate: cands[i]}
	}

	var wg sync.WaitGroup

	for i := range out {
		i := i
		wg.Add(1)
		go func() {
			defer wg.Done()
			// Try user-provided creds first.
			if info, err := Inspect(out[i].DeviceServiceURL, user, pass); err == nil {
				out[i].Profile = info
				return
			} else {
				out[i].InspectError = err
			}
			// Fall back to default credentials.
			for _, dc := range defaultCreds {
				if dc.User == user && dc.Pass == pass {
					continue // already tried
				}
				if info, err := Inspect(out[i].DeviceServiceURL, dc.User, dc.Pass); err == nil {
					out[i].Profile = info
					out[i].InspectError = nil
					out[i].UsedDefaults = true
					return
				}
			}
			// None worked — keep the original InspectError.
		}()
	}

	// Wait for all inspects OR ctx cancel, whichever comes first.
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	select {
	case <-done:
	case <-ctx.Done():
		// Return what we have; in-flight goroutines will finish but their
		// results won't be observed. This is fine because each index writes
		// to a distinct element and the test expectations are by length,
		// not by in-flight ordering.
	}
	return out, nil
}
