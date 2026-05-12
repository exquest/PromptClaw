"""Tests for the IDyOM LTM weekly KL-divergence audit (T-031)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.health import (  # noqa: E402
    DEFAULT_HISTORY_PATH,
    AuditEntry,
    AuditReport,
    _main as generation_health_main,
    idyom_kl_divergence_audit,
)


TEST_NGRAMS: tuple[tuple[int, ...], ...] = (
    (60, 62, 64),
    (62, 64, 65),
    (64, 65, 67),
    (65, 67, 69),
    (67, 69, 71),
)


def _ngram_key(ngram: Sequence[int]) -> str:
    return ",".join(str(p) for p in ngram)


def _write_ltm(path: Path, counts: dict[tuple[int, ...], float]) -> Path:
    payload = {_ngram_key(k): float(v) for k, v in counts.items()}
    path.write_text(json.dumps(payload))
    return path


def _uniform_counts(weight: float = 10.0) -> dict[tuple[int, ...], float]:
    return {ngram: weight for ngram in TEST_NGRAMS}


def _peaked_counts(weight: float = 100.0) -> dict[tuple[int, ...], float]:
    counts = {ngram: 1.0 for ngram in TEST_NGRAMS}
    counts[TEST_NGRAMS[0]] = weight
    return counts


def _fixed_clock(when: datetime):
    def _clock() -> datetime:
        return when

    return _clock


@pytest.fixture
def alert_path(tmp_path: Path) -> Path:
    return tmp_path / "generation_collapse_alert.json"


@pytest.fixture
def history_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "idyom_kl_audit.json"


def test_kl_zero_when_identical(tmp_path: Path, history_path: Path, alert_path: Path) -> None:
    snapshot = _write_ltm(tmp_path / "snapshot.json", _uniform_counts())
    current = _write_ltm(tmp_path / "current.json", _uniform_counts())

    report = idyom_kl_divergence_audit(
        current_ltm_path=current,
        snapshot_path=snapshot,
        test_ngrams=TEST_NGRAMS,
        generated_ratio=0.1,
        clap_centroid_variance=1.0,
        history_path=history_path,
        alert_path=alert_path,
        clock=_fixed_clock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )

    assert isinstance(report, AuditReport)
    assert report.kl_divergence == pytest.approx(0.0, abs=1e-9)
    assert report.flagged is False


def test_kl_positive_when_divergent(
    tmp_path: Path, history_path: Path, alert_path: Path
) -> None:
    snapshot = _write_ltm(tmp_path / "snapshot.json", _uniform_counts())
    current = _write_ltm(tmp_path / "current.json", _peaked_counts())

    report = idyom_kl_divergence_audit(
        current_ltm_path=current,
        snapshot_path=snapshot,
        test_ngrams=TEST_NGRAMS,
        generated_ratio=0.1,
        clap_centroid_variance=1.0,
        history_path=history_path,
        alert_path=alert_path,
        clock=_fixed_clock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )

    assert report.kl_divergence > 0.0


def test_missing_snapshot_raises(tmp_path: Path, history_path: Path, alert_path: Path) -> None:
    current = _write_ltm(tmp_path / "current.json", _uniform_counts())

    with pytest.raises(FileNotFoundError):
        idyom_kl_divergence_audit(
            current_ltm_path=current,
            snapshot_path=tmp_path / "missing-snapshot.json",
            test_ngrams=TEST_NGRAMS,
            generated_ratio=0.1,
            clap_centroid_variance=1.0,
            history_path=history_path,
            alert_path=alert_path,
        )


def test_missing_current_raises(tmp_path: Path, history_path: Path, alert_path: Path) -> None:
    snapshot = _write_ltm(tmp_path / "snapshot.json", _uniform_counts())

    with pytest.raises(FileNotFoundError):
        idyom_kl_divergence_audit(
            current_ltm_path=tmp_path / "missing-current.json",
            snapshot_path=snapshot,
            test_ngrams=TEST_NGRAMS,
            generated_ratio=0.1,
            clap_centroid_variance=1.0,
            history_path=history_path,
            alert_path=alert_path,
        )


def _run_eight_weeks(
    tmp_path: Path,
    history_path: Path,
    alert_path: Path,
    *,
    kl_series: Sequence[float],
    generated_ratios: Sequence[float],
    variances: Sequence[float],
) -> list[AuditReport]:
    """Drive the audit forward week-by-week with the supplied signal series.

    KL is induced by varying the snapshot's peak weight against a fixed
    uniform current LTM; here we just write a current LTM whose KL against
    a uniform snapshot equals the requested target by emulating peak mass
    fractions. For test-set purposes we control the divergence via the
    *generated_ratio* and *clap_centroid_variance* signals directly while
    still exercising the real KL math by writing two distinct LTMs.
    """
    snapshot = _write_ltm(tmp_path / "snapshot.json", _uniform_counts())
    reports: list[AuditReport] = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for week, (target_kl, gr, var) in enumerate(
        zip(kl_series, generated_ratios, variances)
    ):
        # Build a current LTM whose KL trends with `target_kl` by setting
        # the first n-gram's weight proportional to it.
        counts = _uniform_counts()
        counts[TEST_NGRAMS[0]] = 10.0 + target_kl * 200.0
        current = _write_ltm(tmp_path / f"current_w{week}.json", counts)
        report = idyom_kl_divergence_audit(
            current_ltm_path=current,
            snapshot_path=snapshot,
            test_ngrams=TEST_NGRAMS,
            generated_ratio=gr,
            clap_centroid_variance=var,
            history_path=history_path,
            alert_path=alert_path,
            clock=_fixed_clock(base + timedelta(days=7 * week)),
        )
        reports.append(report)
    return reports


def test_history_caps_at_eight(
    tmp_path: Path, history_path: Path, alert_path: Path
) -> None:
    reports = _run_eight_weeks(
        tmp_path,
        history_path,
        alert_path,
        kl_series=[0.1] * 10,
        generated_ratios=[0.1] * 10,
        variances=[1.0] * 10,
    )

    final = reports[-1]
    assert len(final.history) == 8
    # Most recent entry is last; week_index strictly increasing.
    indices = [entry.week_index for entry in final.history]
    assert indices == sorted(indices)
    assert indices[-1] == 9  # 0..9 ran, last 8 retained -> indices 2..9
    # Persisted file matches.
    persisted = json.loads(history_path.read_text())
    assert len(persisted["history"]) == 8


def test_flag_requires_all_three_signals(
    tmp_path: Path, history_path: Path, alert_path: Path
) -> None:
    # All three signals collapse-aligned for 8 weeks:
    # KL increasing, generated_ratio high (>=0.5), variance decreasing.
    reports = _run_eight_weeks(
        tmp_path,
        history_path,
        alert_path,
        kl_series=[0.05 * i for i in range(1, 9)],
        generated_ratios=[0.55] * 8,
        variances=[1.0 - 0.1 * i for i in range(8)],
    )
    final = reports[-1]
    assert final.flagged is True
    assert "collapse" in final.flag_reason.lower()


def test_two_of_three_does_not_flag(
    tmp_path: Path, history_path: Path, alert_path: Path
) -> None:
    # KL increasing + generated high, but variance is also INCREASING
    # (healthy diversity). Should NOT flag.
    reports = _run_eight_weeks(
        tmp_path,
        history_path,
        alert_path,
        kl_series=[0.05 * i for i in range(1, 9)],
        generated_ratios=[0.55] * 8,
        variances=[0.1 + 0.05 * i for i in range(8)],
    )
    assert reports[-1].flagged is False
    assert not alert_path.exists()


def test_flag_writes_alert_file(
    tmp_path: Path, history_path: Path, alert_path: Path
) -> None:
    _run_eight_weeks(
        tmp_path,
        history_path,
        alert_path,
        kl_series=[0.05 * i for i in range(1, 9)],
        generated_ratios=[0.6] * 8,
        variances=[1.0 - 0.1 * i for i in range(8)],
    )

    assert alert_path.exists()
    payload = json.loads(alert_path.read_text())
    assert payload["flagged"] is True
    assert "flag_reason" in payload
    assert "kl_divergence" in payload
    assert "generated_ratio" in payload
    assert "clap_centroid_variance" in payload
    assert "history" in payload
    assert len(payload["history"]) == 8


def test_no_auto_rollback(
    tmp_path: Path, history_path: Path, alert_path: Path
) -> None:
    snapshot = _write_ltm(tmp_path / "snapshot.json", _uniform_counts())
    current = _write_ltm(tmp_path / "current.json", _peaked_counts())

    snapshot_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    current_hash = hashlib.sha256(current.read_bytes()).hexdigest()

    # Drive a full 8-week collapse-aligned series against the same files.
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for week in range(8):
        idyom_kl_divergence_audit(
            current_ltm_path=current,
            snapshot_path=snapshot,
            test_ngrams=TEST_NGRAMS,
            generated_ratio=0.6,
            clap_centroid_variance=1.0 - 0.1 * week,
            history_path=history_path,
            alert_path=alert_path,
            clock=_fixed_clock(base + timedelta(days=7 * week)),
        )

    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == snapshot_hash
    assert hashlib.sha256(current.read_bytes()).hexdigest() == current_hash


def test_default_history_path_constant() -> None:
    assert DEFAULT_HISTORY_PATH.endswith("idyom_kl_audit.json")


def test_audit_entry_is_frozen() -> None:
    entry = AuditEntry(
        week_index=0,
        timestamp="2026-01-01T00:00:00+00:00",
        kl_divergence=0.0,
        generated_ratio=0.1,
        clap_centroid_variance=1.0,
    )
    with pytest.raises(Exception):
        entry.kl_divergence = 1.0  # type: ignore[misc]


def test_insufficient_history_does_not_flag(
    tmp_path: Path, history_path: Path, alert_path: Path
) -> None:
    # Only two data points — even if signals look bad, we can't trend yet.
    reports = _run_eight_weeks(
        tmp_path,
        history_path,
        alert_path,
        kl_series=[0.05, 0.4],
        generated_ratios=[0.6, 0.7],
        variances=[1.0, 0.5],
    )
    final = reports[-1]
    assert final.flagged is False
    assert "insufficient" in final.flag_reason.lower()


class GenerationHealthEndToEndTests:
    """End-to-end checks for IDyOM audit history, alert, and CLI output."""

    __test__ = True

    def test_weekly_audit_persists_history_alert_and_preserves_ltms(
        self,
        tmp_path: Path,
        history_path: Path,
        alert_path: Path,
    ) -> None:
        snapshot = _write_ltm(tmp_path / "snapshot.json", _uniform_counts())
        snapshot_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        current_paths: list[Path] = []
        current_hashes: dict[Path, str] = {}
        reports: list[AuditReport] = []
        base = datetime(2026, 2, 1, tzinfo=timezone.utc)

        for week, (peak_weight, variance) in enumerate(
            ((12.0, 1.0), (70.0, 0.65), (150.0, 0.30))
        ):
            counts = _uniform_counts()
            counts[TEST_NGRAMS[0]] = peak_weight
            current = _write_ltm(tmp_path / f"current_week_{week}.json", counts)
            current_paths.append(current)
            current_hashes[current] = hashlib.sha256(current.read_bytes()).hexdigest()

            report = idyom_kl_divergence_audit(
                current_ltm_path=current,
                snapshot_path=snapshot,
                test_ngrams=TEST_NGRAMS,
                generated_ratio=0.65,
                clap_centroid_variance=variance,
                history_path=history_path,
                alert_path=alert_path,
                clock=_fixed_clock(base + timedelta(days=week * 7)),
            )
            reports.append(report)

        assert [report.week_index for report in reports] == [0, 1, 2]
        assert reports[0].flagged is False
        assert reports[1].flagged is False
        final = reports[-1]
        assert final.flagged is True
        assert "collapse-drift" in final.flag_reason
        assert final.alert_path == str(alert_path)
        assert len(final.history) == 3
        assert [entry.week_index for entry in final.history] == [0, 1, 2]
        assert final.history[-1].timestamp == (
            base + timedelta(days=14)
        ).isoformat()

        persisted = json.loads(history_path.read_text())
        assert [entry["week_index"] for entry in persisted["history"]] == [0, 1, 2]
        assert persisted["history"][-1]["generated_ratio"] == pytest.approx(0.65)

        assert alert_path.exists()
        alert_payload = json.loads(alert_path.read_text())
        assert alert_payload["flagged"] is True
        assert alert_payload["week_index"] == final.week_index
        assert alert_payload["flag_reason"] == final.flag_reason
        assert len(alert_payload["history"]) == 3

        report_json = json.dumps(final.to_dict(), sort_keys=True)
        round_tripped = json.loads(report_json)
        assert round_tripped["alert_path"] == str(alert_path)
        assert round_tripped["history"][-1]["clap_centroid_variance"] == pytest.approx(
            0.30
        )

        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == snapshot_hash
        for current in current_paths:
            assert hashlib.sha256(current.read_bytes()).hexdigest() == current_hashes[
                current
            ]

    def test_config_entrypoint_prints_json_report(
        self,
        tmp_path: Path,
        history_path: Path,
        alert_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        snapshot = _write_ltm(tmp_path / "snapshot.json", _uniform_counts())
        current = _write_ltm(tmp_path / "current.json", _peaked_counts(25.0))
        config_path = tmp_path / "idyom_kl_audit_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "current_ltm_path": str(current),
                    "snapshot_path": str(snapshot),
                    "history_path": str(history_path),
                    "alert_path": str(alert_path),
                    "test_ngrams": [list(ngram) for ngram in TEST_NGRAMS],
                    "generated_ratio": 0.25,
                    "clap_centroid_variance": 0.9,
                }
            )
        )
        monkeypatch.setenv("IDYOM_KL_AUDIT_CONFIG", str(config_path))

        exit_code = generation_health_main()

        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["week_index"] == 0
        assert output["flagged"] is False
        assert "insufficient history" in output["flag_reason"]
        assert output["history"][0]["generated_ratio"] == pytest.approx(0.25)
        assert output["alert_path"] is None
        assert json.loads(history_path.read_text())["history"][0]["week_index"] == 0
