"""Deep research engine for CypherClaw.

Adaptive depth: quick questions get fast answers, complex topics get
multi-agent research with verification and confidence scoring.
"""

import hashlib
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Research tools will be imported from research_tools.py
# For now, import what we need
try:
    from research_tools import ResearchTools, SourcedFinding
except ImportError:
    ResearchTools = None


@dataclass
class ResearchResult:
    """Complete result of a research query."""
    query: str
    scope: str  # quick, medium, deep
    summary: str  # short summary for Telegram
    full_report: str  # detailed markdown report
    findings: list = field(default_factory=list)  # list of SourcedFinding
    sources_count: int = 0
    confidence_breakdown: dict = field(default_factory=dict)  # {high: N, medium: N, low: N}
    verified: bool = False
    duration_seconds: float = 0


TOOLS_DIR = Path(__file__).parent
PROJECT_ROOT = TOOLS_DIR.parent
_PACKAGE_STOPWORDS = {
    "how",
    "should",
    "compare",
    "package",
    "packages",
    "library",
    "libraries",
    "module",
    "modules",
    "choice",
    "choices",
    "best",
    "latest",
    "version",
    "versions",
    "and",
    "for",
    "the",
    "with",
    "vs",
    "versus",
}


def _run_agent(agent: str, prompt: str, timeout: int = 120) -> str:
    """Run a CLI agent and return output."""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    if agent == "claude":
        cmd = ["claude", "--dangerously-skip-permissions", "--print", "-p", "-"]
    elif agent == "codex":
        cmd = ["codex", "exec", "--full-auto", "-"]
    elif agent == "gemini":
        cmd = ["gemini", "--yolo", "-p", prompt]
        # gemini uses -p arg, not stdin
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                   cwd=str(PROJECT_ROOT), env=env)
            return result.stdout.strip() or result.stderr.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"[{agent} timed out]"
        except Exception as e:
            return f"[{agent} error: {e}]"
    else:
        return f"Unknown agent: {agent}"

    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                               timeout=timeout, cwd=str(PROJECT_ROOT), env=env,
                               start_new_session=True)
        return result.stdout.strip() or result.stderr.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[{agent} timed out]"
    except Exception as e:
        return f"[{agent} error: {e}]"


def _extract_package_candidates(query: str) -> list[str]:
    """Extract likely package names from a natural-language query.

    Avoid treating every ordinary word as a package candidate; prefer quoted,
    backticked, or context-bound tokens such as "for requests".
    """
    candidates: list[str] = []
    seen: set[str] = set()

    explicit_matches = re.findall(r"[`'\"]([A-Za-z0-9_.-]{2,})[`'\"]", query)
    contextual_matches = re.findall(
        r"(?:for|package|packages|library|libraries|module|modules|npm|pypi)\s+([A-Za-z0-9_.-]{2,})",
        query,
        flags=re.IGNORECASE,
    )

    for raw in [*explicit_matches, *contextual_matches]:
        candidate = raw.strip().lower().strip(".,:;!?()[]{}")
        if (
            len(candidate) < 2
            or candidate in _PACKAGE_STOPWORDS
            or not re.fullmatch(r"[a-z0-9_.-]+", candidate)
            or candidate in seen
        ):
            continue
        seen.add(candidate)
        candidates.append(candidate)
    return candidates


class Researcher:
    """Deep research engine with adaptive depth and cross-agent verification."""

    def __init__(self, send_fn: Callable = None, send_file_fn: Callable = None,
                 observatory=None):
        self.send = send_fn or (lambda x: None)
        self.send_file = send_file_fn or (lambda x, y: None)
        self.observatory = observatory
        self.tools = ResearchTools(PROJECT_ROOT) if ResearchTools else None
        self.workspace = TOOLS_DIR / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def research(self, query: str, context: str = "", scope: str = "auto") -> ResearchResult:
        """Main entry point. Classifies scope and runs appropriate workflow."""
        start_time = time.time()

        if scope == "auto":
            scope = self.classify_scope(query)

        self.send(f"🔬 Research scope: **{scope}**")

        if self.observatory:
            self.observatory.record("research_started", data={"query": query[:100], "scope": scope})

        if scope == "quick":
            result = self._quick_research(query, context)
        elif scope == "medium":
            result = self._medium_research(query, context)
        else:
            result = self._deep_research(query, context)

        result.duration_seconds = time.time() - start_time

        if self.observatory:
            self.observatory.record("research_completed", data={
                "query": query[:100], "scope": scope,
                "findings": len(result.findings),
                "sources": result.sources_count,
                "duration_s": result.duration_seconds,
            })

        return result

    def classify_scope(self, query: str) -> str:
        """Determine research depth: quick, medium, deep."""
        lower = query.lower()

        # Quick: factual lookups
        quick_signals = ["what is", "what's", "latest version", "how to install",
                        "what does", "define", "when was", "who is", "current price"]
        if any(s in lower for s in quick_signals) and len(query) < 100:
            return "quick"

        # Deep: complex analysis
        deep_signals = ["should we", "compare", "migrate", "architecture",
                       "strategy", "evaluate", "pros and cons", "best approach",
                       "market analysis", "competitive", "feasibility"]
        if any(s in lower for s in deep_signals):
            return "deep"

        # Medium: everything else
        return "medium"

    def _quick_research(self, query: str, context: str) -> ResearchResult:
        """Fast answer with 1-2 sources."""
        self.send("🔍 Quick search...")

        # Use claude for a direct answer with web context
        prompt = (
            f"Answer this question concisely with sources.\n"
            f"Question: {query}\n"
            f"{'Context: ' + context if context else ''}\n\n"
            f"Include the source URL for any facts. Be concise — this goes to Telegram."
        )
        answer = _run_agent("claude", prompt, timeout=60)

        # Also do a quick web search for verification
        findings = []
        if self.tools:
            results = self.tools.web_search(query, num_results=3)
            for r in results[:2]:
                findings.append(SourcedFinding(
                    claim=r.snippet, source_url=r.url,
                    source_type="web", confidence="medium",
                    raw_excerpt=r.snippet,
                ))

        return ResearchResult(
            query=query, scope="quick",
            summary=answer[:2000],
            full_report=answer,
            findings=findings,
            sources_count=len(findings),
            confidence_breakdown={"medium": len(findings)},
        )

    def _medium_research(self, query: str, context: str) -> ResearchResult:
        """Structured research with outline, multiple sources, report."""
        self.send("📋 Generating research outline...")

        # Step 1: Generate outline
        outline_prompt = (
            f"Create a brief research outline (5-7 bullet points) for:\n"
            f"Topic: {query}\n"
            f"{'Context: ' + context if context else ''}\n\n"
            f"List the key questions to answer. Be concise."
        )
        outline = _run_agent("claude", outline_prompt, timeout=45)
        self.send(f"📋 Outline:\n{outline[:1000]}")

        # Step 2: Multi-source research
        self.send("🔍 Researching across sources...")
        all_findings = []

        # Web search
        if self.tools:
            web_findings = self.tools.web_search_and_read(query)
            all_findings.extend(web_findings)

            # Academic search if relevant
            academic_keywords = ["algorithm", "model", "framework", "theory", "research",
                               "study", "paper", "analysis", "method"]
            if any(kw in query.lower() for kw in academic_keywords):
                papers = self.tools.arxiv_search(query, max_results=3)
                for p in papers:
                    all_findings.append(SourcedFinding(
                        claim=p.abstract[:200], source_url=p.url,
                        source_type="academic", confidence="high",
                        raw_excerpt=p.abstract,
                    ))

            # Package info if relevant
            if "package" in query.lower() or "library" in query.lower() or "npm" in query.lower():
                for package_name in _extract_package_candidates(query):
                    info = self.tools.pypi_package_info(package_name)
                    if info.get("version"):
                        all_findings.append(SourcedFinding(
                            claim=f"{package_name}: {info.get('summary', '')} (v{info['version']})",
                            source_url=f"https://pypi.org/project/{package_name}/",
                            source_type="api", confidence="high",
                        ))

        # Step 3: Synthesize with claude
        self.send("📝 Synthesizing findings...")
        findings_text = "\n".join(
            f"- [{f.source_type}/{f.confidence}] {f.claim} (source: {f.source_url})"
            for f in all_findings
        )

        synthesis_prompt = (
            f"Research topic: {query}\n"
            f"Outline: {outline}\n\n"
            f"Findings from multiple sources:\n{findings_text}\n\n"
            f"Write a clear, structured research report with:\n"
            f"1. Summary (2-3 sentences)\n"
            f"2. Key findings with confidence levels [HIGH/MEDIUM/LOW]\n"
            f"3. Sources cited\n"
            f"4. Recommendations if applicable\n"
            f"Use markdown formatting."
        )
        report = _run_agent("claude", synthesis_prompt, timeout=90)

        # Score confidence
        confidence = {"high": 0, "medium": 0, "low": 0}
        for f in all_findings:
            confidence[f.confidence] = confidence.get(f.confidence, 0) + 1

        # Save report
        report_id = hashlib.md5(f"{query}{time.time()}".encode()).hexdigest()[:8]
        report_path = self.workspace / f"research_{report_id}.md"
        full_report = f"# Research: {query}\n\n{report}\n\n---\n## Sources\n"
        for f in all_findings:
            full_report += f"\n- [{f.confidence}] {f.source_url}: {f.claim[:100]}"
        report_path.write_text(full_report)

        summary = report[:2000] if len(report) <= 2000 else report[:1500] + "\n\n(full report attached)"

        return ResearchResult(
            query=query, scope="medium",
            summary=summary,
            full_report=full_report,
            findings=all_findings,
            sources_count=len(all_findings),
            confidence_breakdown=confidence,
        )

    def _deep_research(self, query: str, context: str) -> ResearchResult:
        """Multi-agent deep research with verification."""
        self.send("🔬 Deep research mode — this will take a few minutes...")

        # Step 1: Research spec
        self.send("📋 Phase 1: Creating research spec...")
        spec_prompt = (
            f"Create a detailed research spec for:\n"
            f"Topic: {query}\n"
            f"{'Context: ' + context if context else ''}\n\n"
            f"Include:\n"
            f"1. Research questions (numbered)\n"
            f"2. Sources to check (web, academic, codebase, APIs)\n"
            f"3. Experiments to run if applicable\n"
            f"4. How to verify findings\n"
            f"Be thorough but concise."
        )
        spec = _run_agent("claude", spec_prompt, timeout=60)
        self.send("📋 Spec ready. Starting multi-agent research...")

        # Step 2: Parallel research — claude does analysis, gemini does web research
        self.send("🔀 Dispatching claude (analysis) + gemini (web research) in parallel...")

        import concurrent.futures
        all_findings = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            # Claude: deep analysis
            claude_prompt = (
                f"Research spec:\n{spec}\n\n"
                f"Conduct thorough analysis for: {query}\n"
                f"Focus on: architecture, trade-offs, technical depth.\n"
                f"Cite specific sources. Mark confidence [HIGH/MEDIUM/LOW] on each finding."
            )

            # Gemini: web research + current info
            gemini_prompt = (
                f"Research this topic thoroughly using web search:\n"
                f"Topic: {query}\n"
                f"Research questions:\n{spec[:500]}\n\n"
                f"Search for current information, recent developments, community opinions.\n"
                f"For each finding, include the source URL and your confidence level."
            )

            f_claude = pool.submit(_run_agent, "claude", claude_prompt, 120)
            f_gemini = pool.submit(_run_agent, "gemini", gemini_prompt, 120)

            claude_output = f_claude.result()
            gemini_output = f_gemini.result()

        self.send("📊 Both agents returned. Cross-verifying...")

        # Step 3: Additional tool-based research
        if self.tools:
            web_findings = self.tools.web_search_and_read(query)
            all_findings.extend(web_findings)

            papers = self.tools.arxiv_search(query, max_results=3)
            for p in papers:
                all_findings.append(SourcedFinding(
                    claim=p.abstract[:200], source_url=p.url,
                    source_type="academic", confidence="high",
                    raw_excerpt=p.abstract,
                ))

            # Local codebase search if relevant
            code_keywords = ["implement", "code", "function", "class", "module", "our"]
            if any(kw in query.lower() for kw in code_keywords):
                matches = self.tools.search_local_code(query.split()[-1])
                for m in matches[:5]:
                    all_findings.append(SourcedFinding(
                        claim=f"Found in local codebase: {m.file}",
                        source_url=f"file://{m.file}",
                        source_type="codebase", confidence="high",
                    ))

        # Step 4: Cross-verification with codex
        self.send("✅ Phase 3: Independent verification...")
        verify_prompt = (
            f"You are independently verifying research on: {query}\n\n"
            f"Agent 1 (Claude) found:\n{claude_output[:2000]}\n\n"
            f"Agent 2 (Gemini) found:\n{gemini_output[:2000]}\n\n"
            f"Cross-verify:\n"
            f"1. Where do both agents agree? (HIGH confidence)\n"
            f"2. Where do they disagree? (LOW confidence, flag for review)\n"
            f"3. What's missing that neither covered?\n"
            f"4. Overall confidence assessment\n"
            f"Be rigorous and specific."
        )
        verification = _run_agent("codex", verify_prompt, timeout=90)

        # Step 5: Final synthesis
        self.send("📝 Synthesizing final report...")
        final_prompt = (
            f"Create a comprehensive research report on: {query}\n\n"
            f"Primary research (Claude):\n{claude_output[:1500]}\n\n"
            f"Web research (Gemini):\n{gemini_output[:1500]}\n\n"
            f"Verification (Codex):\n{verification[:1500]}\n\n"
            f"Tool findings:\n"
            + "\n".join(f"- [{f.source_type}/{f.confidence}] {f.claim[:100]}" for f in all_findings[:10])
            + f"\n\nWrite a well-structured markdown report with:\n"
            f"# Research Report: {query}\n"
            f"## Executive Summary\n"
            f"## Key Findings (with confidence levels)\n"
            f"## Analysis\n"
            f"## Verification Notes\n"
            f"## Sources\n"
            f"## Recommendations\n"
        )
        final_report = _run_agent("claude", final_prompt, timeout=120)

        # Save full report
        report_id = hashlib.md5(f"{query}{time.time()}".encode()).hexdigest()[:8]
        report_path = self.workspace / f"research_{report_id}.md"

        full_report = (
            f"# Deep Research: {query}\n\n"
            f"{final_report}\n\n"
            f"---\n## Raw Agent Outputs\n\n"
            f"### Claude Analysis\n{claude_output[:3000]}\n\n"
            f"### Gemini Web Research\n{gemini_output[:3000]}\n\n"
            f"### Codex Verification\n{verification[:2000]}\n\n"
            f"---\n## Tool-Based Sources\n"
        )
        for f in all_findings:
            full_report += f"\n- [{f.source_type}/{f.confidence}] {f.source_url}: {f.claim[:100]}"

        report_path.write_text(full_report)

        confidence = {"high": 0, "medium": 0, "low": 0}
        for f in all_findings:
            confidence[f.confidence] = confidence.get(f.confidence, 0) + 1

        summary = final_report[:2000] if len(final_report) <= 2000 else final_report[:1500] + "\n\n(full report attached)"

        return ResearchResult(
            query=query, scope="deep",
            summary=summary,
            full_report=full_report,
            findings=all_findings,
            sources_count=len(all_findings),
            confidence_breakdown=confidence,
            verified=True,
            duration_seconds=0,
        )
