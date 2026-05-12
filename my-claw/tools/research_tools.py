"""Research tools for CypherClaw's deep research engine.

Provides web search, web reading, academic paper search, local codebase search,
external API queries (GitHub, npm, pypi), and experiment execution.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

@dataclass
class WebPage:
    url: str
    title: str
    text: str  # cleaned text content
    raw_length: int

@dataclass
class Paper:
    title: str
    authors: list[str]
    abstract: str
    url: str
    published: str

@dataclass
class CodeMatch:
    file: str
    line: int
    text: str
    context: str  # surrounding lines

@dataclass
class SourcedFinding:
    claim: str
    source_url: str
    source_type: str  # web, academic, codebase, api, experiment
    confidence: str  # high, medium, low
    verified_by: str | None = None
    raw_excerpt: str = ""

@dataclass
class ExperimentResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class ResearchTools:
    """All research capabilities for the deep research engine."""

    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root)

    # --- Web Search ---
    def web_search(self, query: str, num_results: int = 8) -> list[SearchResult]:
        """Search the web using gemini CLI with search grounding."""
        # Use gemini which has built-in Google Search grounding
        prompt = (
            f"Search the web for: {query}\n\n"
            f"Return ONLY a JSON array of results, each with: title, url, snippet.\n"
            f"Return up to {num_results} results. JSON array only, no other text."
        )
        try:
            result = subprocess.run(
                ["gemini", "--yolo", "-p", prompt],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.project_root),
            )
            output = result.stdout.strip()
            # Try to parse JSON from response
            arr_start = output.find("[")
            arr_end = output.rfind("]") + 1
            if arr_start >= 0 and arr_end > arr_start:
                data = json.loads(output[arr_start:arr_end])
                return [SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                ) for r in data if isinstance(r, dict)]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        return []

    def web_fetch(self, url: str, max_chars: int = 15000) -> WebPage:
        """Fetch and clean a web page."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CypherClaw/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                raw_len = len(raw)
                # Strip HTML tags for clean text
                text = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                title_match = re.search(r'<title[^>]*>(.*?)</title>', raw, re.DOTALL | re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else url
                return WebPage(url=url, title=title, text=text[:max_chars], raw_length=raw_len)
        except Exception as e:
            return WebPage(url=url, title="Error", text=f"Failed to fetch: {e}", raw_length=0)

    def web_search_and_read(self, query: str, max_pages: int = 3) -> list[SourcedFinding]:
        """Search web, read top results, extract findings."""
        results = self.web_search(query)
        findings = []
        for r in results[:max_pages]:
            page = self.web_fetch(r.url)
            if page.raw_length > 0:
                findings.append(SourcedFinding(
                    claim=r.snippet or page.text[:200],
                    source_url=r.url,
                    source_type="web",
                    confidence="medium",
                    raw_excerpt=page.text[:500],
                ))
        return findings

    # --- Academic ---
    def arxiv_search(self, query: str, max_results: int = 5) -> list[Paper]:
        """Search arxiv for academic papers."""
        try:
            encoded = urllib.parse.quote(query)
            url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&max_results={max_results}&sortBy=relevance"
            req = urllib.request.Request(url, headers={"User-Agent": "CypherClaw/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml = resp.read().decode("utf-8")

            papers = []
            # Simple XML parsing (no lxml dependency)
            entries = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
            for entry in entries:
                title = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                abstract = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                link = re.search(r'<id>(.*?)</id>', entry)
                published = re.search(r'<published>(.*?)</published>', entry)
                authors = re.findall(r'<name>(.*?)</name>', entry)
                papers.append(Paper(
                    title=title.group(1).strip() if title else "",
                    authors=authors[:5],
                    abstract=abstract.group(1).strip()[:500] if abstract else "",
                    url=link.group(1).strip() if link else "",
                    published=published.group(1)[:10] if published else "",
                ))
            return papers
        except Exception:
            return []

    # --- Local Codebase ---
    def search_local_code(self, pattern: str, paths: list[str] | None = None) -> list[CodeMatch]:
        """Grep across local codebases."""
        search_paths = paths or [
            str(Path.home() / "Programming"),
            str(Path.home() / "Documents" / "programming"),
        ]
        matches = []
        for search_path in search_paths:
            try:
                result = subprocess.run(
                    ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.js",
                     "--include=*.md", "-l", pattern, search_path],
                    capture_output=True, text=True, timeout=15,
                )
                for line in result.stdout.strip().splitlines()[:20]:
                    matches.append(CodeMatch(file=line, line=0, text="", context=""))
            except (subprocess.TimeoutExpired, Exception):
                pass
        return matches

    def read_file(self, path: str, max_chars: int = 10000) -> str:
        """Read a local file."""
        try:
            return Path(path).read_text()[:max_chars]
        except Exception as e:
            return f"Error reading {path}: {e}"

    def grep_projects(self, pattern: str, project_path: str = "") -> list[CodeMatch]:
        """Search within a specific project."""
        target = project_path or str(self.project_root)
        matches = []
        try:
            result = subprocess.run(
                ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.js",
                 "--include=*.md", "--include=*.yaml", "--include=*.toml",
                 pattern, target],
                capture_output=True, text=True, timeout=15,
            )
            for line in result.stdout.strip().splitlines()[:30]:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append(CodeMatch(
                        file=parts[0], line=int(parts[1]) if parts[1].isdigit() else 0,
                        text=parts[2][:200], context="",
                    ))
        except (subprocess.TimeoutExpired, Exception):
            pass
        return matches

    # --- External APIs ---
    def github_search(self, query: str, search_type: str = "repositories") -> list[dict]:
        """Search GitHub via gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "search", search_type, query, "--json", "name,url,description", "--limit", "10"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        return []

    def github_issues(self, repo: str, query: str = "") -> list[dict]:
        """Search issues in a GitHub repo."""
        try:
            cmd = ["gh", "issue", "list", "--repo", repo, "--json", "title,url,state,body", "--limit", "10"]
            if query:
                cmd.extend(["--search", query])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        return []

    def npm_package_info(self, package: str) -> dict:
        """Get npm package info."""
        try:
            url = f"https://registry.npmjs.org/{urllib.parse.quote(package)}"
            req = urllib.request.Request(url, headers={"User-Agent": "CypherClaw/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                latest = data.get("dist-tags", {}).get("latest", "")
                return {
                    "name": data.get("name", package),
                    "version": latest,
                    "description": data.get("description", ""),
                    "homepage": data.get("homepage", ""),
                    "license": data.get("license", ""),
                }
        except Exception:
            return {}

    def pypi_package_info(self, package: str) -> dict:
        """Get PyPI package info."""
        try:
            url = f"https://pypi.org/pypi/{urllib.parse.quote(package)}/json"
            req = urllib.request.Request(url, headers={"User-Agent": "CypherClaw/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                info = data.get("info", {})
                return {
                    "name": info.get("name", package),
                    "version": info.get("version", ""),
                    "summary": info.get("summary", ""),
                    "home_page": info.get("home_page", ""),
                    "license": info.get("license", ""),
                }
        except Exception:
            return {}

    # --- Experimental ---
    def run_experiment(self, code: str, language: str = "python", timeout: int = 30) -> ExperimentResult:
        """Run code in a sandboxed subprocess."""
        import time
        start = time.time()

        suffix = {"python": ".py", "javascript": ".js", "node": ".js", "bash": ".sh"}.get(language, ".py")
        cmd_map = {
            "python": [sys.executable],
            "javascript": ["node"],
            "node": ["node"],
            "bash": ["bash"],
        }
        cmd = cmd_map.get(language, [sys.executable])

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name

            result = subprocess.run(
                cmd + [tmp_path],
                capture_output=True, text=True, timeout=timeout,
                cwd=str(self.project_root),
            )
            duration = int((time.time() - start) * 1000)
            return ExperimentResult(
                success=result.returncode == 0,
                stdout=result.stdout[:5000],
                stderr=result.stderr[:2000],
                exit_code=result.returncode,
                duration_ms=duration,
            )
        except subprocess.TimeoutExpired:
            return ExperimentResult(False, "", f"Timed out after {timeout}s", -1, timeout * 1000)
        except Exception as e:
            return ExperimentResult(False, "", str(e), -1, 0)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def benchmark(self, code_a: str, code_b: str, iterations: int = 3) -> dict:
        """Benchmark two code snippets."""
        results_a = []
        results_b = []
        for _ in range(iterations):
            ra = self.run_experiment(code_a)
            rb = self.run_experiment(code_b)
            results_a.append(ra.duration_ms)
            results_b.append(rb.duration_ms)
        return {
            "a_avg_ms": sum(results_a) / len(results_a),
            "b_avg_ms": sum(results_b) / len(results_b),
            "a_results": results_a,
            "b_results": results_b,
            "faster": "a" if sum(results_a) < sum(results_b) else "b",
        }
