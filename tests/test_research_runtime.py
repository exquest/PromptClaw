"""Tests for the CypherClaw research runtime."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import researcher
import research_tools


class FakeObservatory:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def record(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class FakeTools:
    def web_search(self, query: str, num_results: int = 8) -> list[research_tools.SearchResult]:
        return [
            research_tools.SearchResult(
                title="One",
                url="https://example.com/one",
                snippet="first finding",
            ),
            research_tools.SearchResult(
                title="Two",
                url="https://example.com/two",
                snippet="second finding",
            ),
        ]

    def web_search_and_read(self, query: str, max_pages: int = 3) -> list[research_tools.SourcedFinding]:
        return [
            research_tools.SourcedFinding(
                claim="web fact",
                source_url="https://example.com/fact",
                source_type="web",
                confidence="medium",
                raw_excerpt="web excerpt",
            )
        ]

    def arxiv_search(self, query: str, max_results: int = 5) -> list[research_tools.Paper]:
        return [
            research_tools.Paper(
                title="Paper",
                authors=["Ada"],
                abstract="academic abstract",
                url="https://arxiv.org/abs/1234.5678",
                published="2026-01-01",
            )
        ]

    def pypi_package_info(self, package: str) -> dict:
        return {"version": "1.2.3", "summary": f"{package} package"}

    def search_local_code(self, pattern: str, paths: list[str] | None = None) -> list[research_tools.CodeMatch]:
        return [
            research_tools.CodeMatch(
                file="/tmp/project/example.py",
                line=10,
                text="def example():",
                context="ctx",
            )
        ]


def test_classify_scope_distinguishes_quick_medium_and_deep() -> None:
    r = researcher.Researcher()

    assert r.classify_scope("What is Redis?") == "quick"
    assert r.classify_scope("Compare Redis vs Postgres for event storage") == "deep"
    assert r.classify_scope("Investigate recent code patterns") == "medium"


def test_research_logs_events_and_generates_medium_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages: list[str] = []
    observatory = FakeObservatory()
    r = researcher.Researcher(send_fn=sent_messages.append, observatory=observatory)
    r.tools = FakeTools()
    r.workspace = tmp_path

    outputs = iter(
        [
            "- Question one\n- Question two",
            "Structured report with findings and recommendations.",
        ]
    )
    monkeypatch.setattr(researcher, "_run_agent", lambda agent, prompt, timeout=120: next(outputs))

    result = r.research("How should we compare package choices for requests?", scope="medium")

    assert result.scope == "medium"
    assert result.sources_count == 2
    assert result.confidence_breakdown == {"high": 1, "medium": 1, "low": 0}
    assert result.summary.startswith("Structured report")
    assert "research_started" in [event for event, _ in observatory.events]
    assert "research_completed" in [event for event, _ in observatory.events]
    report_files = list(tmp_path.glob("research_*.md"))
    assert len(report_files) == 1
    assert "How should we compare package choices for requests?" in report_files[0].read_text()
    assert any("Research scope:" in message for message in sent_messages)


def test_quick_research_uses_tools_for_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    r = researcher.Researcher()
    r.tools = FakeTools()
    monkeypatch.setattr(researcher, "_run_agent", lambda agent, prompt, timeout=120: "Quick answer")

    result = r._quick_research("What is the latest version of pytest?", "")

    assert result.scope == "quick"
    assert result.summary == "Quick answer"
    assert result.sources_count == 2
    assert len(result.findings) == 2


def test_web_fetch_strips_tags_and_extracts_title(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"""
    <html>
      <head><title>Example Title</title><style>.x{}</style></head>
      <body><script>bad()</script><h1>Hello</h1><p>World</p></body>
    </html>
    """

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return html

    monkeypatch.setattr(research_tools.urllib.request, "urlopen", lambda req, timeout=15: FakeResponse())

    page = research_tools.ResearchTools(Path(".")).web_fetch("https://example.com")

    assert page.title == "Example Title"
    assert "Hello World" in page.text
    assert "bad()" not in page.text
    assert page.raw_length == len(html)


def test_run_experiment_and_benchmark_delegate_to_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tools = research_tools.ResearchTools(tmp_path)

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(research_tools.subprocess, "run", fake_run)

    result = tools.run_experiment("print('ok')", language="python", timeout=5)

    assert result.success is True
    assert result.stdout == "ok"
    assert result.exit_code == 0

    durations = iter([10, 20, 30, 15, 25, 35])
    monkeypatch.setattr(
        tools,
        "run_experiment",
        lambda code, language="python", timeout=30: research_tools.ExperimentResult(
            success=True,
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=next(durations),
        ),
    )

    bench = tools.benchmark("a", "b", iterations=3)

    assert bench["a_results"] == [10, 30, 25]
    assert bench["b_results"] == [20, 15, 35]
    assert bench["a_avg_ms"] == pytest.approx((10 + 30 + 25) / 3)
    assert bench["b_avg_ms"] == pytest.approx((20 + 15 + 35) / 3)
    assert bench["faster"] == "a"
