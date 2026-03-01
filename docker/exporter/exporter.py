#!/usr/bin/env python3
"""urfd Prometheus metrics exporter.

Parses urfd.xml on every scrape for current-state gauges, and tails
urfd.log incrementally for event counters.

Metrics exposed on :9101/metrics
"""

import datetime
import os
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

from prometheus_client import (
    CollectorRegistry, Counter, generate_latest, CONTENT_TYPE_LATEST,
)
from prometheus_client.core import GaugeMetricFamily

LOGS_DIR = os.environ.get('LOGS_DIR', '/logs')
XML_FILE = os.path.join(LOGS_DIR, 'urfd.xml')
LOG_FILE = os.path.join(LOGS_DIR, 'urfd.log')
PORT     = int(os.environ.get('PORT', '9101'))

registry = CollectorRegistry()

# ── Log-derived counters (persist between scrapes) ───────────────────────────

c_streams  = Counter(
    'urfd_streams', 'Streams opened',
    ['module'], registry=registry)

c_packets  = Counter(
    'urfd_stream_packets', 'Packets in completed transcoded streams',
    ['module'], registry=registry)

c_duration = Counter(
    'urfd_stream_active_seconds', 'Total seconds of active stream time — use rate() for busy graph',
    ['module'], registry=registry)

c_connects = Counter(
    'urfd_client_events', 'Client connect/disconnect events',
    ['protocol', 'module', 'event'], registry=registry)

c_timeouts = Counter(
    'urfd_keepalive_timeouts', 'Keepalive timeouts by protocol',
    ['protocol'], registry=registry)

c_orphaned = Counter(
    'urfd_orphaned_frames', 'Orphaned (header-less) frames received',
    ['module'], registry=registry)

# ── Mutable state (all protected by _lock) ───────────────────────────────────

_tc              = {}   # module -> (min_ms, avg_ms, max_ms)   last stream
_active_streams  = {}   # module -> int   currently open stream count
_open_times      = {}   # module -> [log_timestamp, ...]  FIFO open times
_pending_modules = []   # FIFO: modules awaiting their TC time line
_log_pos         = 0
_lock            = threading.Lock()

# ── Log line patterns ─────────────────────────────────────────────────────────

RE_TS      = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z')
RE_OPEN    = re.compile(r'Opening stream on module (\w)')
RE_CLOSE   = re.compile(r'Closing stream of module (\w)')
RE_TC      = re.compile(r'TC round-trip time\(ms\): ([\d.]+)/([\d.]+)/([\d.]+), (\d+) total packets')
RE_ADD     = re.compile(r'New client .+ added with protocol (\S+) on module (\w)')
RE_REM     = re.compile(r'Client .+ removed with protocol (\S+) on module (\w)')
RE_TIMEOUT = re.compile(r'(\w+) client .+ keepalive timeout')
RE_ORPHAN  = re.compile(r'Orphaned Frame.+module (\w)', re.IGNORECASE)


def _line_ts(line):
    """Parse the ISO 8601 UTC timestamp from a log line; fall back to now."""
    m = RE_TS.match(line)
    if m:
        try:
            return datetime.datetime.strptime(
                m.group(1), '%Y-%m-%dT%H:%M:%S'
            ).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            pass
    return time.time()


def tail_log():
    """Read any new lines appended to urfd.log since the last call."""
    global _log_pos, _pending_modules, _active_streams, _open_times

    try:
        size = os.path.getsize(LOG_FILE)
    except OSError:
        return

    if size < _log_pos:     # log rotated
        _log_pos = 0
    if size == _log_pos:
        return

    with open(LOG_FILE, 'r', errors='replace') as f:
        f.seek(_log_pos)
        for line in f:
            if m := RE_OPEN.search(line):
                mod = m.group(1)
                c_streams.labels(module=mod).inc()
                _active_streams[mod] = _active_streams.get(mod, 0) + 1
                _open_times.setdefault(mod, []).append(_line_ts(line))

            elif m := RE_CLOSE.search(line):
                mod = m.group(1)
                _pending_modules.append(mod)
                _active_streams[mod] = max(0, _active_streams.get(mod, 0) - 1)
                times = _open_times.get(mod, [])
                if times:
                    duration = _line_ts(line) - times.pop(0)
                    if duration > 0:
                        c_duration.labels(module=mod).inc(duration)

            elif m := RE_TC.search(line):
                if _pending_modules:
                    mod = _pending_modules.pop(0)
                    _tc[mod] = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
                    c_packets.labels(module=mod).inc(int(m.group(4)))

            elif m := RE_ADD.search(line):
                c_connects.labels(protocol=m.group(1), module=m.group(2), event='connected').inc()

            elif m := RE_REM.search(line):
                c_connects.labels(protocol=m.group(1), module=m.group(2), event='disconnected').inc()

            elif m := RE_TIMEOUT.search(line):
                c_timeouts.labels(protocol=m.group(1)).inc()

            elif m := RE_ORPHAN.search(line):
                c_orphaned.labels(module=m.group(1)).inc()

        _log_pos = f.tell()


# ── XML parser ────────────────────────────────────────────────────────────────

def _parse_blocks(content, tag):
    """Return list of field dicts for every <tag>…</tag> block in content."""
    tag_pat   = re.compile(rf'<{re.escape(tag)}>(.*?)</{re.escape(tag)}>', re.DOTALL)
    field_pat = re.compile(r'<([^/\n>][^>\n]*)>(.*?)</\1>', re.DOTALL)
    blocks = []
    for m in tag_pat.finditer(content):
        blocks.append({
            fm.group(1).strip(): fm.group(2).strip()
            for fm in field_pat.finditer(m.group(1))
        })
    return blocks


class UrfdCollector:
    """Custom collector — merges XML gauges with persisted log-derived state."""

    def describe(self):
        return []   # lazy registration; no pre-check needed

    def collect(self):
        # ── Read XML ──────────────────────────────────────────────────────────
        content = ''
        try:
            if os.path.getsize(XML_FILE) > 0:
                with open(XML_FILE, 'r', errors='replace') as f:
                    content = f.read()
        except OSError:
            pass

        now = time.time()

        # ── Reflector version info ─────────────────────────────────────────
        g_info = GaugeMetricFamily(
            'urfd_info', 'Reflector version info (value always 1)',
            labels=['version'])
        m = re.search(r'<Version>(.*?)</Version>', content)
        if m:
            g_info.add_metric([m.group(1).strip()], 1)
        yield g_info

        # ── Connected nodes (by protocol and module) ──────────────────────────
        g_nodes = GaugeMetricFamily(
            'urfd_nodes_connected',
            'Number of connected nodes by protocol and module',
            labels=['protocol', 'module'])
        counts = {}
        for node in _parse_blocks(content, 'NODE'):
            key = (node.get('Protocol', 'unknown'), node.get('LinkedModule', '?'))
            counts[key] = counts.get(key, 0) + 1
        for (proto, mod), n in counts.items():
            g_nodes.add_metric([proto, mod], n)
        yield g_nodes

        # ── Linked interlink peers ─────────────────────────────────────────────
        g_peers = GaugeMetricFamily(
            'urfd_peers_linked',
            'Interlink peers currently linked (1 = linked)',
            labels=['callsign', 'module', 'protocol'])
        g_peer_age = GaugeMetricFamily(
            'urfd_peer_last_heard_seconds',
            'Seconds since this interlink peer was last heard',
            labels=['callsign', 'module', 'protocol'])
        for peer in _parse_blocks(content, 'PEER'):
            callsign = peer.get('Callsign', '?').strip()
            mod      = peer.get('LinkedModule', '?')
            proto    = peer.get('Protocol', '?')
            g_peers.add_metric([callsign, mod, proto], 1)
            lh = peer.get('LastHeardTime', '')
            if lh.isdigit():
                g_peer_age.add_metric([callsign, mod, proto], now - int(lh))
        yield g_peers
        yield g_peer_age

        # ── Heard users per module ────────────────────────────────────────────
        g_heard = GaugeMetricFamily(
            'urfd_users_heard',
            'Number of recently heard users per module',
            labels=['module'])
        heard_counts = {}
        for station in _parse_blocks(content, 'STATION'):
            mod = station.get('On module', '?')
            heard_counts[mod] = heard_counts.get(mod, 0) + 1
        for mod, n in heard_counts.items():
            g_heard.add_metric([mod], n)
        yield g_heard

        # ── Currently active streams ──────────────────────────────────────────
        with _lock:
            active_snapshot = dict(_active_streams)
            tc_snapshot     = dict(_tc)

        g_active = GaugeMetricFamily(
            'urfd_streams_active',
            'Number of streams currently open (currently on-air)',
            labels=['module'])
        for mod, n in active_snapshot.items():
            g_active.add_metric([mod], n)
        yield g_active

        # ── TC round-trip latency (last stream per module) ────────────────────
        g_tc_min = GaugeMetricFamily(
            'urfd_tc_roundtrip_min_milliseconds',
            'Minimum TC round-trip time of last stream (ms)', labels=['module'])
        g_tc_avg = GaugeMetricFamily(
            'urfd_tc_roundtrip_avg_milliseconds',
            'Average TC round-trip time of last stream (ms)', labels=['module'])
        g_tc_max = GaugeMetricFamily(
            'urfd_tc_roundtrip_max_milliseconds',
            'Maximum TC round-trip time of last stream (ms)', labels=['module'])
        for mod, (mn, avg, mx) in tc_snapshot.items():
            g_tc_min.add_metric([mod], mn)
            g_tc_avg.add_metric([mod], avg)
            g_tc_max.add_metric([mod], mx)
        yield g_tc_min
        yield g_tc_avg
        yield g_tc_max


registry.register(UrfdCollector())


# ── HTTP handler ──────────────────────────────────────────────────────────────

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/metrics':
            self.send_response(404)
            self.end_headers()
            return

        with _lock:
            tail_log()

        output = generate_latest(registry)
        self.send_response(200)
        self.send_header('Content-Type', CONTENT_TYPE_LATEST)
        self.send_header('Content-Length', str(len(output)))
        self.end_headers()
        self.wfile.write(output)

    def log_message(self, *args):
        pass    # suppress per-request access log noise


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Start tailing from the current end of the log so we don't replay
    # historical events as a burst of counter increments on first start.
    try:
        _log_pos = os.path.getsize(LOG_FILE)
    except OSError:
        _log_pos = 0

    print(f'urfd-exporter listening on :{PORT}', flush=True)
    HTTPServer(('', PORT), MetricsHandler).serve_forever()
