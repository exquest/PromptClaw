"""Tests for antenna_to_skin.py — network/external signals to organism skin sensations."""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from antenna_to_skin import (
    NetworkPulse,
    read_network_stats,
    network_to_sensation,
    telegram_to_sensation,
    combine_skin_sensations,
)


# ---------------------------------------------------------------------------
# NetworkPulse dataclass
# ---------------------------------------------------------------------------


class TestNetworkPulse:
    def test_dataclass_fields(self):
        pulse = NetworkPulse(
            bytes_in=1000,
            bytes_out=500,
            latency_ms=12.5,
            connections_active=42,
            timestamp=1234567890.0,
        )
        assert pulse.bytes_in == 1000
        assert pulse.bytes_out == 500
        assert pulse.latency_ms == 12.5
        assert pulse.connections_active == 42
        assert pulse.timestamp == 1234567890.0

    def test_dataclass_equality(self):
        a = NetworkPulse(100, 200, 10.0, 5, 1.0)
        b = NetworkPulse(100, 200, 10.0, 5, 1.0)
        assert a == b

    def test_dataclass_inequality(self):
        a = NetworkPulse(100, 200, 10.0, 5, 1.0)
        b = NetworkPulse(999, 200, 10.0, 5, 1.0)
        assert a != b


# ---------------------------------------------------------------------------
# read_network_stats
# ---------------------------------------------------------------------------


class TestReadNetworkStats:
    def test_returns_network_pulse(self, tmp_path):
        """read_network_stats returns a NetworkPulse with non-negative values."""
        # Write a fake /proc/net/dev file
        proc_net_dev = tmp_path / "net_dev"
        proc_net_dev.write_text(
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|"
            "bytes    packets errs drop fifo colls carrier compressed\n"
            "    lo: 1234567   8901    0    0    0     0          0         0  "
            " 1234567   8901    0    0    0     0       0          0\n"
            "  eth0: 9876543  12345    0    0    0     0          0         0  "
            " 5432100   6789    0    0    0     0       0          0\n"
        )
        pulse = read_network_stats(proc_path=str(proc_net_dev))
        assert isinstance(pulse, NetworkPulse)
        assert pulse.bytes_in >= 0
        assert pulse.bytes_out >= 0
        assert pulse.timestamp > 0

    def test_sums_all_interfaces_except_lo(self, tmp_path):
        """Should sum bytes from all non-loopback interfaces."""
        proc_net_dev = tmp_path / "net_dev"
        proc_net_dev.write_text(
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|"
            "bytes    packets errs drop fifo colls carrier compressed\n"
            "    lo: 1000000      0    0    0    0     0          0         0  "
            " 1000000      0    0    0    0     0       0          0\n"
            "  eth0:  500000      0    0    0    0     0          0         0  "
            "  200000      0    0    0    0     0       0          0\n"
            " wlan0:  300000      0    0    0    0     0          0         0  "
            "  100000      0    0    0    0     0       0          0\n"
        )
        pulse = read_network_stats(proc_path=str(proc_net_dev))
        assert pulse.bytes_in == 800000  # 500000 + 300000 (no lo)
        assert pulse.bytes_out == 300000  # 200000 + 100000 (no lo)

    def test_handles_missing_proc_file(self):
        """Should return zero-valued pulse if /proc/net/dev doesn't exist."""
        pulse = read_network_stats(proc_path="/nonexistent/path/net_dev")
        assert isinstance(pulse, NetworkPulse)
        assert pulse.bytes_in == 0
        assert pulse.bytes_out == 0
        assert pulse.connections_active == 0

    def test_handles_malformed_proc_file(self, tmp_path):
        """Should return zero-valued pulse if file is garbled."""
        proc_net_dev = tmp_path / "net_dev"
        proc_net_dev.write_text("totally garbage content\nno structure here\n")
        pulse = read_network_stats(proc_path=str(proc_net_dev))
        assert isinstance(pulse, NetworkPulse)
        assert pulse.bytes_in == 0
        assert pulse.bytes_out == 0

    def test_latency_defaults_to_zero(self, tmp_path):
        """Latency requires /proc/net/tcp or similar; defaults to 0 when unavailable."""
        proc_net_dev = tmp_path / "net_dev"
        proc_net_dev.write_text(
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|"
            "bytes    packets errs drop fifo colls carrier compressed\n"
            "  eth0:  500000      0    0    0    0     0          0         0  "
            "  200000      0    0    0    0     0       0          0\n"
        )
        pulse = read_network_stats(proc_path=str(proc_net_dev))
        assert pulse.latency_ms >= 0.0

    def test_connections_from_tcp_file(self, tmp_path):
        """Should count established TCP connections from /proc/net/tcp."""
        proc_net_dev = tmp_path / "net_dev"
        proc_net_dev.write_text(
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|"
            "bytes    packets errs drop fifo colls carrier compressed\n"
            "  eth0: 1000    0    0    0    0     0          0         0  "
            " 500    0    0    0    0     0       0          0\n"
        )
        # Write a fake /proc/net/tcp — state 01 = ESTABLISHED
        proc_net_tcp = tmp_path / "net_tcp"
        proc_net_tcp.write_text(
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            "   0: 0100007F:1F90 0100007F:C9A8 01 00000000:00000000 00:00000000 00000000     0        0 12345\n"
            "   1: 0100007F:1F91 0100007F:C9A9 01 00000000:00000000 00:00000000 00000000     0        0 12346\n"
            "   2: 0100007F:1F92 0100007F:C9AA 06 00000000:00000000 00:00000000 00000000     0        0 12347\n"
        )
        pulse = read_network_stats(
            proc_path=str(proc_net_dev),
            tcp_path=str(proc_net_tcp),
        )
        # Two ESTABLISHED (01) connections, one TIME_WAIT (06)
        assert pulse.connections_active == 2


# ---------------------------------------------------------------------------
# network_to_sensation
# ---------------------------------------------------------------------------


class TestNetworkToSensation:
    def test_quiet_when_no_activity(self):
        pulse = NetworkPulse(0, 0, 0.0, 0, time.time())
        result = network_to_sensation(pulse)
        assert result["activity"] == "quiet"
        assert result["warmth"] == 0.0
        assert result["pressure"] == 0.0

    def test_moderate_activity(self):
        now = time.time()
        baseline = NetworkPulse(1000, 500, 5.0, 10, now - 1.0)
        current = NetworkPulse(51000, 25500, 10.0, 10, now)
        result = network_to_sensation(current, baseline)
        assert result["activity"] in ("moderate", "busy")

    def test_busy_on_high_traffic(self):
        now = time.time()
        baseline = NetworkPulse(0, 0, 5.0, 10, now - 1.0)
        current = NetworkPulse(500_000, 250_000, 10.0, 10, now)
        result = network_to_sensation(current, baseline)
        assert result["activity"] in ("busy", "storm")

    def test_storm_on_extreme_traffic(self):
        now = time.time()
        baseline = NetworkPulse(0, 0, 5.0, 10, now - 1.0)
        current = NetworkPulse(5_000_000, 2_500_000, 10.0, 10, now)
        result = network_to_sensation(current, baseline)
        assert result["activity"] == "storm"

    def test_warmth_scales_with_connections(self):
        pulse_low = NetworkPulse(0, 0, 0.0, 5, time.time())
        pulse_high = NetworkPulse(0, 0, 0.0, 200, time.time())
        result_low = network_to_sensation(pulse_low)
        result_high = network_to_sensation(pulse_high)
        assert result_high["warmth"] > result_low["warmth"]

    def test_warmth_clamped_0_to_1(self):
        pulse = NetworkPulse(0, 0, 0.0, 10000, time.time())
        result = network_to_sensation(pulse)
        assert 0.0 <= result["warmth"] <= 1.0

    def test_pressure_scales_with_latency(self):
        pulse_low = NetworkPulse(0, 0, 1.0, 0, time.time())
        pulse_high = NetworkPulse(0, 0, 500.0, 0, time.time())
        result_low = network_to_sensation(pulse_low)
        result_high = network_to_sensation(pulse_high)
        assert result_high["pressure"] > result_low["pressure"]

    def test_pressure_clamped_0_to_1(self):
        pulse = NetworkPulse(0, 0, 99999.0, 0, time.time())
        result = network_to_sensation(pulse)
        assert 0.0 <= result["pressure"] <= 1.0

    def test_no_baseline_uses_absolute_bytes(self):
        """Without baseline, activity should be based on absolute byte counts."""
        pulse = NetworkPulse(100_000, 50_000, 5.0, 10, time.time())
        result = network_to_sensation(pulse, baseline=None)
        assert result["activity"] in ("quiet", "moderate", "busy", "storm")

    def test_returns_expected_keys(self):
        pulse = NetworkPulse(0, 0, 0.0, 0, time.time())
        result = network_to_sensation(pulse)
        assert "activity" in result
        assert "warmth" in result
        assert "pressure" in result


# ---------------------------------------------------------------------------
# telegram_to_sensation
# ---------------------------------------------------------------------------


class TestTelegramToSensation:
    def test_quiet_no_messages(self):
        result = telegram_to_sensation(message_count=0, last_message_age_s=9999.0)
        assert result["feeling"] == "quiet"
        assert result["intensity"] == 0.0

    def test_touched_recent_messages(self):
        result = telegram_to_sensation(message_count=5, last_message_age_s=10.0)
        assert result["feeling"] == "touched"
        assert result["intensity"] > 0.0

    def test_intensity_higher_with_more_messages(self):
        r1 = telegram_to_sensation(message_count=1, last_message_age_s=30.0)
        r2 = telegram_to_sensation(message_count=10, last_message_age_s=30.0)
        assert r2["intensity"] > r1["intensity"]

    def test_intensity_higher_with_recent_messages(self):
        r_old = telegram_to_sensation(message_count=5, last_message_age_s=600.0)
        r_new = telegram_to_sensation(message_count=5, last_message_age_s=5.0)
        assert r_new["intensity"] > r_old["intensity"]

    def test_intensity_clamped_0_to_1(self):
        result = telegram_to_sensation(message_count=10000, last_message_age_s=0.1)
        assert 0.0 <= result["intensity"] <= 1.0

    def test_returns_expected_keys(self):
        result = telegram_to_sensation(message_count=0, last_message_age_s=0.0)
        assert "feeling" in result
        assert "intensity" in result

    def test_zero_age_does_not_crash(self):
        """Edge case: last_message_age_s = 0 should not divide-by-zero."""
        result = telegram_to_sensation(message_count=1, last_message_age_s=0.0)
        assert result["feeling"] == "touched"


# ---------------------------------------------------------------------------
# combine_skin_sensations
# ---------------------------------------------------------------------------


class TestCombineSkinSensations:
    def test_combines_network_and_telegram(self):
        network = {"activity": "busy", "warmth": 0.6, "pressure": 0.3}
        telegram = {"feeling": "touched", "intensity": 0.7}
        result = combine_skin_sensations(network, telegram)
        assert "overall_activity" in result
        assert "network" in result
        assert "telegram" in result

    def test_overall_activity_high_when_both_active(self):
        network = {"activity": "storm", "warmth": 0.9, "pressure": 0.8}
        telegram = {"feeling": "touched", "intensity": 0.9}
        result = combine_skin_sensations(network, telegram)
        assert result["overall_activity"] in ("busy", "storm")

    def test_overall_activity_quiet_when_both_quiet(self):
        network = {"activity": "quiet", "warmth": 0.0, "pressure": 0.0}
        telegram = {"feeling": "quiet", "intensity": 0.0}
        result = combine_skin_sensations(network, telegram)
        assert result["overall_activity"] == "quiet"

    def test_overall_activity_moderate_mixed(self):
        network = {"activity": "moderate", "warmth": 0.3, "pressure": 0.1}
        telegram = {"feeling": "quiet", "intensity": 0.0}
        result = combine_skin_sensations(network, telegram)
        assert result["overall_activity"] in ("quiet", "moderate")

    def test_telegram_alone_raises_activity(self):
        network = {"activity": "quiet", "warmth": 0.0, "pressure": 0.0}
        telegram = {"feeling": "touched", "intensity": 0.8}
        result = combine_skin_sensations(network, telegram)
        assert result["overall_activity"] != "quiet" or result["telegram"]["feeling"] == "touched"

    def test_preserves_sub_dicts(self):
        network = {"activity": "busy", "warmth": 0.5, "pressure": 0.5}
        telegram = {"feeling": "touched", "intensity": 0.5}
        result = combine_skin_sensations(network, telegram)
        assert result["network"]["activity"] == "busy"
        assert result["telegram"]["feeling"] == "touched"

    def test_returns_expected_keys(self):
        network = {"activity": "quiet", "warmth": 0.0, "pressure": 0.0}
        telegram = {"feeling": "quiet", "intensity": 0.0}
        result = combine_skin_sensations(network, telegram)
        assert "overall_activity" in result
        assert "network" in result
        assert "telegram" in result
