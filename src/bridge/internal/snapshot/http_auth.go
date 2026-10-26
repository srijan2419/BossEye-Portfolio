package snapshot

import (
	"context"
	"crypto/md5"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"
)

// httpGetWithAuth GETs url and returns the body bytes. It tries HTTP Basic
// first (most cameras accept it); on a 401 with a Digest challenge it
// parses the challenge, computes an RFC 2617 Digest response, and retries.
// Any other non-2xx status returns an error with the status line.
func httpGetWithAuth(ctx context.Context, url, user, pass string) ([]byte, error) {
	client := &http.Client{Timeout: 15 * time.Second}

	// Attempt 1: Basic auth.
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	if user != "" {
		req.SetBasicAuth(user, pass)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode == http.StatusUnauthorized {
		challenge := resp.Header.Get("WWW-Authenticate")
		resp.Body.Close()
		if strings.HasPrefix(strings.ToLower(challenge), "digest ") {
			return digestRetry(ctx, client, url, user, pass, challenge)
		}
		return nil, fmt.Errorf("http: 401 Unauthorized (no Digest challenge)")
	}

	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("http: %d %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}
	return io.ReadAll(resp.Body)
}

// digestRetry parses the challenge, computes a Digest response per RFC 2617,
// and retries the same URL with an Authorization header.
func digestRetry(ctx context.Context, client *http.Client, url, user, pass, challenge string) ([]byte, error) {
	params := parseDigestChallenge(challenge)
	realm := params["realm"]
	nonce := params["nonce"]
	qop := params["qop"] // may be "", "auth", or "auth,auth-int"

	// Use the path portion of the URL as the "uri" value in the digest
	// response. We parse it out by finding the "://host" segment and
	// taking everything after the host.
	uri := "/"
	if idx := strings.Index(url, "://"); idx > 0 {
		rest := url[idx+3:]
		if slash := strings.Index(rest, "/"); slash >= 0 {
			uri = rest[slash:]
		}
	}

	ha1 := md5hex(user + ":" + realm + ":" + pass)
	ha2 := md5hex("GET:" + uri)

	var response, authHeader string
	if qop != "" {
		// Use "auth" qop with a client-generated cnonce + nc=00000001.
		cnonce := randomHex(8)
		nc := "00000001"
		// If the challenge lists multiple qops, pick "auth".
		qopValue := "auth"
		response = md5hex(ha1 + ":" + nonce + ":" + nc + ":" + cnonce + ":" + qopValue + ":" + ha2)
		authHeader = fmt.Sprintf(
			`Digest username="%s", realm="%s", nonce="%s", uri="%s", qop=%s, nc=%s, cnonce="%s", response="%s", algorithm=MD5`,
			user, realm, nonce, uri, qopValue, nc, cnonce, response,
		)
	} else {
		response = md5hex(ha1 + ":" + nonce + ":" + ha2)
		authHeader = fmt.Sprintf(
			`Digest username="%s", realm="%s", nonce="%s", uri="%s", response="%s", algorithm=MD5`,
			user, realm, nonce, uri, response,
		)
	}

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", authHeader)
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("http: digest retry %d %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}
	return io.ReadAll(resp.Body)
}

// parseDigestChallenge parses `Digest key="val", key2="val2", ...` into a map.
// Naive but sufficient for real camera challenges.
var digestKV = regexp.MustCompile(`(\w+)=("([^"]+)"|([^,\s]+))`)

func parseDigestChallenge(h string) map[string]string {
	out := map[string]string{}
	// Strip leading "Digest "
	if len(h) >= 7 && strings.EqualFold(h[:7], "Digest ") {
		h = h[7:]
	}
	for _, m := range digestKV.FindAllStringSubmatch(h, -1) {
		k := strings.ToLower(m[1])
		v := m[3]
		if v == "" {
			v = m[4]
		}
		out[k] = v
	}
	return out
}

func md5hex(s string) string {
	sum := md5.Sum([]byte(s))
	return hex.EncodeToString(sum[:])
}

func randomHex(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
