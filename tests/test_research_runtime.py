"""Tests for the CypherClaw research runtime."""

from __future__ import annotations

import json
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


class ResearchRuntimeEndToEndTests:
    """End-to-end coverage for the deterministic research runtime path."""

    __test__ = True

    def test_auto_deep_research_persists_verified_report_and_json_diagnostic(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent_messages: list[str] = []
        observatory = FakeObservatory()
        researcher_runtime = researcher.Researcher(
            send_fn=sent_messages.append,
            observatory=observatory,
        )
        researcher_runtime.tools = FakeTools()
        researcher_runtime.workspace = tmp_path
        agent_calls: list[dict[str, object]] = []

        def fake_run_agent(agent: str, prompt: str, timeout: int = 120) -> str:
            agent_calls.append(
                {
                    "agent": agent,
                    "timeout": timeout,
                    "prompt_prefix": prompt[:80],
                }
            )
            if "Create a detailed research spec" in prompt:
                return (
                    "1. Compare runtime architecture\n"
                    "2. Verify implementation path\n"
                    "3. Check web, academic, and codebase sources"
                )
            if agent == "claude" and "Focus on: architecture" in prompt:
                return "[HIGH] The runtime can keep one public deep-research workflow."
            if agent == "gemini":
                return "[MEDIUM] Current research workflows benefit from cited web context."
            if agent == "codex":
                return "Both agents agree on one workflow; codebase evidence is present."
            if agent == "claude" and "Create a comprehensive research report" in prompt:
                return (
                    "# Research Report: Runtime Path\n\n"
                    "## Executive Summary\n"
                    "Use the existing deep-research workflow with tool findings and "
                    "verification notes.\n\n"
                    "## Recommendations\n"
                    "Ship the one-path coverage."
                )
            return "unexpected prompt"

        monkeypatch.setattr(researcher, "_run_agent", fake_run_agent)

        query = "Compare architecture for our research runtime module"
        result = researcher_runtime.research(query, scope="auto")

        assert result.query == query
        assert result.scope == "deep"
        assert result.verified is True
        assert result.summary.startswith("# Research Report: Runtime Path")
        assert result.sources_count == 3
        assert result.confidence_breakdown == {"high": 2, "medium": 1, "low": 0}
        assert [finding.source_type for finding in result.findings] == [
            "web",
            "academic",
            "codebase",
        ]
        assert [finding.confidence for finding in result.findings] == [
            "medium",
            "high",
            "high",
        ]

        event_types = [event for event, _ in observatory.events]
        assert event_types == ["research_started", "research_completed"]
        assert observatory.events[0][1]["scope"] == "deep"
        assert observatory.events[1][1]["sources"] == 3
        assert any("Research scope: **deep**" in message for message in sent_messages)
        assert any("Spec ready" in message for message in sent_messages)
        assert any("Cross-verifying" in message for message in sent_messages)

        agent_counts = {
            agent: sum(1 for call in agent_calls if call["agent"] == agent)
            for agent in ("claude", "gemini", "codex")
        }
        assert agent_counts == {"claude": 3, "gemini": 1, "codex": 1}
        assert {call["timeout"] for call in agent_calls} == {60, 90, 120}

        report_files = list(tmp_path.glob("research_*.md"))
        assert len(report_files) == 1
        persisted_report = report_files[0].read_text()
        assert f"# Deep Research: {query}" in persisted_report
        assert "### Claude Analysis" in persisted_report
        assert "### Gemini Web Research" in persisted_report
        assert "### Codex Verification" in persisted_report
        assert "https://example.com/fact" in persisted_report
        assert "https://arxiv.org/abs/1234.5678" in persisted_report
        assert "file:///tmp/project/example.py" in persisted_report

        diagnostic = {
            "result": {
                "query": result.query,
                "scope": result.scope,
                "verified": result.verified,
                "sources_count": result.sources_count,
                "confidence_breakdown": result.confidence_breakdown,
                "summary": result.summary,
            },
            "findings": [
                {
                    "claim": finding.claim,
                    "source_url": finding.source_url,
                    "source_type": finding.source_type,
                    "confidence": finding.confidence,
                }
                for finding in result.findings
            ],
            "messages": sent_messages,
            "events": [
                {"event_type": event_type, "data": data}
                for event_type, data in observatory.events
            ],
            "agent_calls": agent_calls,
            "report_name": report_files[0].name,
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped["result"]["scope"] == "deep"
        assert round_tripped["result"]["verified"] is True
        assert round_tripped["result"]["sources_count"] == 3
        assert round_tripped["result"]["confidence_breakdown"] == {
            "high": 2,
            "medium": 1,
            "low": 0,
        }
        assert [finding["source_type"] for finding in round_tripped["findings"]] == [
            "web",
            "academic",
            "codebase",
        ]
        assert [event["event_type"] for event in round_tripped["events"]] == [
            "research_started",
            "research_completed",
        ]
        assert round_tripped["report_name"].startswith("research_")
