#!/usr/bin/env python3
"""
PromptClaw Project Scanner v1.0
Comprehensive local project discovery, analysis, and migration readiness tool.

Scans directories for git repos and project directories, collects metadata,
classifies activity, assesses migration readiness, and correlates with GitHub.

Usage:
    python project_scanner.py --dirs ~/Programming ~/Documents/programming \
        --github-json github_repos.json --output-dir ./reports
"""

import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys
import textwrap

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIRS = frozenset({
    "node_modules", ".venv", "venv", "__pycache__", ".git", "build", "dist",
    ".tox", ".eggs", "site-packages", ".mypy_cache", ".pytest_cache",
    ".next", ".nuxt", ".cache", ".gradle", ".idea", ".vscode",
    "Pods", "DerivedData", ".build", ".swiftpm",
    "target",  # Rust / Java
    "vendor",  # Go / PHP
    "bower_components",
    "egg-info",
    "Library",  # Unity project Library cache
    "PackageCache",  # Unity package cache
    "Logs",
})

PROJECT_MARKERS = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "Dockerfile",
    "Podfile",
    "requirements.txt",
    "Gemfile",
    "build.gradle",
    "pom.xml",
    "CMakeLists.txt",
    "meson.build",
    "composer.json",
    "mix.exs",
    "stack.yaml",
    "cabal.project",
    "dune-project",
    "Project.toml",   # Julia
    "pubspec.yaml",   # Dart / Flutter
    "flake.nix",
}

# Glob-style markers (checked separately)
GLOB_MARKERS = [
    "*.xcodeproj",
    "*.xcworkspace",
    "*.sln",
    "*.csproj",
]

EXTENSION_TO_LANGUAGE = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".mm": "Objective-C",
    ".h": "C/C++/ObjC Header",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".scala": "Scala",
    ".clj": "Clojure",
    ".cljs": "ClojureScript",
    ".lua": "Lua",
    ".r": "R",
    ".R": "R",
    ".jl": "Julia",
    ".dart": "Dart",
    ".sol": "Solidity",
    ".vy": "Vyper",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".pl": "Perl",
    ".pm": "Perl",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SASS",
    ".less": "LESS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".nim": "Nim",
    ".zig": "Zig",
    ".v": "V",
    ".nix": "Nix",
    ".tf": "Terraform",
    ".proto": "Protobuf",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".sql": "SQL",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".xml": "XML",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".tex": "LaTeX",
    ".ipynb": "Jupyter Notebook",
}

# Activity thresholds in days
ACTIVITY_THRESHOLDS = [
    (30, "active"),
    (90, "recent"),
    (180, "stale"),
    (365, "inactive"),
]
ACTIVITY_DEAD = "dead"

CI_INDICATORS = [
    ".github/workflows",
    ".gitlab-ci.yml",
    ".circleci",
    "Jenkinsfile",
    ".travis.yml",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    ".buildkite",
    "appveyor.yml",
    ".drone.yml",
    "cloudbuild.yaml",
    "Taskfile.yml",
]

MAC_FRAMEWORK_IMPORTS = [
    "CoreML", "SwiftUI", "UIKit", "AppKit", "Foundation",
    "CoreData", "CoreGraphics", "CoreImage", "CoreLocation",
    "CoreBluetooth", "CoreMotion", "HealthKit", "MapKit",
    "ARKit", "RealityKit", "Metal", "SceneKit", "SpriteKit",
    "WatchKit", "WidgetKit", "StoreKit", "CloudKit",
    "Combine", "XCTest",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    """Print progress message to stderr."""
    print(f"[scanner] {msg}", file=sys.stderr, flush=True)


def run_git(args: list[str], cwd: str, timeout: int = 15) -> str | None:
    """Run a git command; return stdout or None on any failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def dir_size_mb(path: str) -> float:
    """Return directory size in MB using du. Falls back to 0.0."""
    try:
        result = subprocess.run(
            ["du", "-sk", path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            kb = int(result.stdout.split()[0])
            return round(kb / 1024.0, 2)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        pass
    return 0.0


def classify_activity(age_days: int | None) -> str:
    """Return activity label based on commit age in days."""
    if age_days is None:
        return "unknown"
    for threshold, label in ACTIVITY_THRESHOLDS:
        if age_days <= threshold:
            return label
    return ACTIVITY_DEAD


def read_json_safe(path: str) -> dict | list | None:
    """Read a JSON file, return parsed data or None."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def safe_read_text(path: str, max_bytes: int = 512_000) -> str:
    """Read text file, capping at max_bytes, ignoring errors."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_projects(root_dirs: list[str], max_depth: int = 10) -> list[str]:
    """
    Walk root directories, find project roots (git repos or marker files).
    Returns de-duplicated sorted list of absolute paths.
    """
    projects: set[str] = set()

    for root_dir in root_dirs:
        root_dir = os.path.expanduser(root_dir)
        root_dir = os.path.abspath(root_dir)
        if not os.path.isdir(root_dir):
            log(f"WARNING: root directory does not exist: {root_dir}")
            continue
        log(f"Scanning: {root_dir}")
        _walk_for_projects(root_dir, projects, depth=0, max_depth=max_depth)

    result = sorted(projects)
    log(f"Discovered {len(result)} project(s)")
    return result


def _walk_for_projects(directory: str, found: set[str], depth: int, max_depth: int) -> None:
    """Recursively walk looking for project roots."""
    if depth > max_depth:
        return

    try:
        entries = os.listdir(directory)
    except PermissionError:
        return
    except OSError:
        return

    entry_set = set(entries)

    # Check if this directory is a project root
    is_project = False

    # Git repo?
    if ".git" in entry_set:
        is_project = True

    # Marker files?
    if not is_project:
        for marker in PROJECT_MARKERS:
            if marker in entry_set:
                is_project = True
                break

    # Glob markers (*.xcodeproj, etc.)
    if not is_project:
        for pattern in GLOB_MARKERS:
            suffix = pattern.replace("*", "")
            for entry in entries:
                if entry.endswith(suffix):
                    is_project = True
                    break
            if is_project:
                break

    if is_project:
        found.add(directory)
        # Still recurse into subdirs to find monorepo children / nested projects
        # but skip heavy dirs
        for entry in entries:
            if entry in SKIP_DIRS:
                continue
            child = os.path.join(directory, entry)
            if os.path.isdir(child) and not os.path.islink(child):
                _walk_for_projects(child, found, depth + 1, max_depth)
    else:
        # Not a project, keep recursing
        for entry in entries:
            if entry in SKIP_DIRS:
                continue
            child = os.path.join(directory, entry)
            if os.path.isdir(child) and not os.path.islink(child):
                _walk_for_projects(child, found, depth + 1, max_depth)


# ---------------------------------------------------------------------------
# Per-project analysis
# ---------------------------------------------------------------------------

def analyze_project(project_path: str, now: datetime.datetime) -> dict:
    """Collect all metadata for a single project."""
    info: dict = {
        "name": os.path.basename(project_path),
        "path": project_path,
        "disk_size_mb": 0.0,
        "has_git": False,
        "git_remote": None,
        "last_commit_date": None,
        "last_commit_age_days": None,
        "total_commits": None,
        "primary_language": None,
        "languages": [],
        "frameworks": [],
        "has_tests": False,
        "has_ci": False,
        "has_docker": False,
        "mac_specific": False,
        "mac_specific_reasons": [],
        "dependencies_file": None,
        "is_monorepo": False,
        "nested_projects": [],
        "deployment_status": "unknown",
        "deployment_targets": [],
        "deployment_notes": [],
        "activity": "unknown",
        "migration_ready": "yes",
        "migration_notes": [],
    }

    # Disk size
    info["disk_size_mb"] = dir_size_mb(project_path)

    # Git info
    git_dir = os.path.join(project_path, ".git")
    if os.path.exists(git_dir):
        info["has_git"] = True
        _collect_git_info(project_path, info, now)

    # Language detection
    _detect_languages(project_path, info)

    # Framework detection
    _detect_frameworks(project_path, info)

    # Tests
    info["has_tests"] = _detect_tests(project_path)

    # CI
    info["has_ci"] = _detect_ci(project_path)

    # Docker
    info["has_docker"] = _detect_docker(project_path)

    # Mac-specific
    _detect_mac_specific(project_path, info)

    # Dependencies file
    info["dependencies_file"] = _detect_deps_file(project_path)

    # Monorepo
    _detect_monorepo(project_path, info)

    # Deployment status
    _detect_deployment(project_path, info)

    # Activity classification
    info["activity"] = classify_activity(info["last_commit_age_days"])

    # Migration readiness
    _assess_migration(info)

    return info


def _collect_git_info(project_path: str, info: dict, now: datetime.datetime) -> None:
    """Populate git-related fields."""
    # Remote
    remote = run_git(["config", "--get", "remote.origin.url"], cwd=project_path)
    if remote:
        info["git_remote"] = remote

    # Last commit date
    date_str = run_git(["log", "-1", "--format=%aI"], cwd=project_path)
    if date_str:
        info["last_commit_date"] = date_str
        try:
            commit_dt = datetime.datetime.fromisoformat(date_str)
            # Make both offset-aware or both naive for subtraction
            if commit_dt.tzinfo is not None:
                delta = now.astimezone(datetime.timezone.utc) - commit_dt.astimezone(datetime.timezone.utc)
            else:
                delta = now.replace(tzinfo=None) - commit_dt
            info["last_commit_age_days"] = max(0, delta.days)
        except (ValueError, TypeError):
            pass

    # Total commits
    count_str = run_git(["rev-list", "--count", "HEAD"], cwd=project_path)
    if count_str and count_str.isdigit():
        info["total_commits"] = int(count_str)


def _detect_languages(project_path: str, info: dict) -> None:
    """Walk files and count by language extension."""
    counts: collections.Counter[str] = collections.Counter()
    file_limit = 50_000  # safety valve
    visited = 0

    for dirpath, dirnames, filenames in os.walk(project_path):
        # Prune skip dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            if visited >= file_limit:
                break
            ext = os.path.splitext(fname)[1].lower()
            lang = EXTENSION_TO_LANGUAGE.get(ext)
            if lang and lang not in ("JSON", "YAML", "TOML", "XML", "Markdown",
                                      "reStructuredText", "SQL", "LaTeX"):
                counts[lang] += 1
                visited += 1
        if visited >= file_limit:
            break

    if counts:
        ranked = counts.most_common()
        info["primary_language"] = ranked[0][0]
        info["languages"] = [lang for lang, _ in ranked]


def _detect_frameworks(project_path: str, info: dict) -> None:
    """Detect frameworks from config files and imports."""
    frameworks: list[str] = []

    # Python frameworks
    manage_py = os.path.join(project_path, "manage.py")
    if os.path.isfile(manage_py):
        content = safe_read_text(manage_py, 4096)
        if "django" in content.lower():
            frameworks.append("Django")

    # Check requirements / pyproject for Flask, FastAPI, etc.
    for deps_file in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"):
        fp = os.path.join(project_path, deps_file)
        if os.path.isfile(fp):
            content = safe_read_text(fp).lower()
            if "flask" in content:
                frameworks.append("Flask")
            if "fastapi" in content:
                frameworks.append("FastAPI")
            if "django" in content and "Django" not in frameworks:
                frameworks.append("Django")
            if "streamlit" in content:
                frameworks.append("Streamlit")
            if "celery" in content:
                frameworks.append("Celery")
            if "sqlalchemy" in content:
                frameworks.append("SQLAlchemy")
            if "pytorch" in content or "torch" in content:
                frameworks.append("PyTorch")
            if "tensorflow" in content:
                frameworks.append("TensorFlow")
            if "langchain" in content:
                frameworks.append("LangChain")
            if "openai" in content:
                frameworks.append("OpenAI")
            if "transformers" in content:
                frameworks.append("HuggingFace Transformers")

    # JavaScript / TypeScript frameworks via package.json
    pkg_json_path = os.path.join(project_path, "package.json")
    if os.path.isfile(pkg_json_path):
        pkg = read_json_safe(pkg_json_path)
        if isinstance(pkg, dict):
            all_deps: dict[str, object] = {}
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                deps = pkg.get(key)
                if isinstance(deps, dict):
                    all_deps.update(deps)

            dep_names = set(all_deps.keys())

            if "react" in dep_names:
                frameworks.append("React")
            if "next" in dep_names:
                frameworks.append("Next.js")
            if "vue" in dep_names:
                frameworks.append("Vue")
            if "nuxt" in dep_names:
                frameworks.append("Nuxt")
            if "@angular/core" in dep_names:
                frameworks.append("Angular")
            if "svelte" in dep_names:
                frameworks.append("Svelte")
            if "express" in dep_names:
                frameworks.append("Express")
            if "fastify" in dep_names:
                frameworks.append("Fastify")
            if "nestjs" in dep_names or "@nestjs/core" in dep_names:
                frameworks.append("NestJS")
            if "electron" in dep_names:
                frameworks.append("Electron")
            if "react-native" in dep_names:
                frameworks.append("React Native")
            if "expo" in dep_names:
                frameworks.append("Expo")
            if "tailwindcss" in dep_names:
                frameworks.append("Tailwind CSS")
            if "three" in dep_names:
                frameworks.append("Three.js")
            if "hardhat" in dep_names:
                frameworks.append("Hardhat")
            if "ethers" in dep_names:
                frameworks.append("Ethers.js")
            if "web3" in dep_names:
                frameworks.append("Web3.js")
            if "@solana/web3.js" in dep_names:
                frameworks.append("Solana Web3")
            if "vite" in dep_names:
                frameworks.append("Vite")
            if "webpack" in dep_names:
                frameworks.append("Webpack")
            if "prisma" in dep_names or "@prisma/client" in dep_names:
                frameworks.append("Prisma")
            if "drizzle-orm" in dep_names:
                frameworks.append("Drizzle ORM")
            if "supabase" in dep_names or "@supabase/supabase-js" in dep_names:
                frameworks.append("Supabase")

    # Rust frameworks via Cargo.toml
    cargo_path = os.path.join(project_path, "Cargo.toml")
    if os.path.isfile(cargo_path):
        content = safe_read_text(cargo_path).lower()
        if "actix" in content:
            frameworks.append("Actix")
        if "rocket" in content:
            frameworks.append("Rocket")
        if "axum" in content:
            frameworks.append("Axum")
        if "tokio" in content:
            frameworks.append("Tokio")
        if "wasm" in content:
            frameworks.append("WebAssembly")

    # Go frameworks via go.mod
    gomod_path = os.path.join(project_path, "go.mod")
    if os.path.isfile(gomod_path):
        content = safe_read_text(gomod_path).lower()
        if "gin-gonic" in content:
            frameworks.append("Gin")
        if "gorilla" in content:
            frameworks.append("Gorilla")
        if "fiber" in content:
            frameworks.append("Fiber")
        if "echo" in content:
            frameworks.append("Echo")

    # Ruby frameworks
    gemfile_path = os.path.join(project_path, "Gemfile")
    if os.path.isfile(gemfile_path):
        content = safe_read_text(gemfile_path).lower()
        if "rails" in content:
            frameworks.append("Rails")
        if "sinatra" in content:
            frameworks.append("Sinatra")

    # Solidity
    for sol_marker in ("hardhat.config.js", "hardhat.config.ts", "truffle-config.js", "foundry.toml"):
        if os.path.isfile(os.path.join(project_path, sol_marker)):
            if sol_marker.startswith("hardhat") and "Hardhat" not in frameworks:
                frameworks.append("Hardhat")
            elif sol_marker.startswith("truffle"):
                frameworks.append("Truffle")
            elif sol_marker == "foundry.toml":
                frameworks.append("Foundry")

    # Swift frameworks (Package.swift)
    spm_path = os.path.join(project_path, "Package.swift")
    if os.path.isfile(spm_path):
        content = safe_read_text(spm_path)
        if "Vapor" in content or "vapor" in content.lower():
            frameworks.append("Vapor")

    # Flutter / Dart
    pubspec_path = os.path.join(project_path, "pubspec.yaml")
    if os.path.isfile(pubspec_path):
        content = safe_read_text(pubspec_path).lower()
        if "flutter" in content:
            frameworks.append("Flutter")

    # Docker compose
    for dc in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        if os.path.isfile(os.path.join(project_path, dc)):
            frameworks.append("Docker Compose")
            break

    # Terraform
    try:
        for tf in os.listdir(project_path):
            if tf.endswith(".tf"):
                frameworks.append("Terraform")
                break
    except OSError:
        pass

    # Deduplicate while preserving order
    seen = set()
    unique: list[str] = []
    for fw in frameworks:
        if fw not in seen:
            seen.add(fw)
            unique.append(fw)
    info["frameworks"] = unique


def _detect_tests(project_path: str) -> bool:
    """Check for test files or directories."""
    # Quick check for common test directories at project root
    for test_dir in ("tests", "test", "spec", "specs", "__tests__", "test_suite"):
        candidate = os.path.join(project_path, test_dir)
        if os.path.isdir(candidate):
            return True

    # Check for pytest.ini, tox.ini, jest.config, etc.
    for cfg in ("pytest.ini", "tox.ini", "jest.config.js", "jest.config.ts",
                "vitest.config.ts", "vitest.config.js", ".mocharc.yml",
                "karma.conf.js", "cypress.config.js", "cypress.config.ts",
                "playwright.config.ts", "playwright.config.js"):
        if os.path.isfile(os.path.join(project_path, cfg)):
            return True

    # Check package.json for test script
    pkg_path = os.path.join(project_path, "package.json")
    if os.path.isfile(pkg_path):
        pkg = read_json_safe(pkg_path)
        if isinstance(pkg, dict):
            scripts = pkg.get("scripts", {})
            if isinstance(scripts, dict) and "test" in scripts:
                test_cmd = scripts["test"]
                # Ignore the npm init placeholder
                if isinstance(test_cmd, str) and "no test specified" not in test_cmd:
                    return True

    # Walk a bit looking for test files (limit scope)
    checked = 0
    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            if checked > 5000:
                return False
            lower = fname.lower()
            if (lower.startswith("test_") or lower.endswith("_test.py") or
                    lower.endswith(".test.js") or lower.endswith(".test.ts") or
                    lower.endswith(".test.tsx") or lower.endswith(".test.jsx") or
                    lower.endswith(".spec.js") or lower.endswith(".spec.ts") or
                    lower.endswith(".spec.tsx") or lower.endswith("_test.go") or
                    lower.endswith("_test.rs")):
                return True
            checked += 1
    return False


def _detect_ci(project_path: str) -> bool:
    """Check for CI/CD configuration."""
    for indicator in CI_INDICATORS:
        full = os.path.join(project_path, indicator)
        if os.path.exists(full):
            return True
    return False


def _detect_docker(project_path: str) -> bool:
    """Check for Docker files."""
    for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                 "compose.yml", "compose.yaml", ".dockerignore"):
        if os.path.isfile(os.path.join(project_path, name)):
            return True
    # Also check for Dockerfile.* variants
    try:
        for entry in os.listdir(project_path):
            if entry.startswith("Dockerfile"):
                return True
    except OSError:
        pass
    return False


def _detect_mac_specific(project_path: str, info: dict) -> None:
    """Detect macOS / Apple platform specific dependencies."""
    reasons: list[str] = []

    # .xcodeproj / .xcworkspace
    try:
        for entry in os.listdir(project_path):
            if entry.endswith(".xcodeproj"):
                reasons.append(f"Xcode project: {entry}")
            elif entry.endswith(".xcworkspace"):
                reasons.append(f"Xcode workspace: {entry}")
    except OSError:
        pass

    # Podfile / Podfile.lock
    if os.path.isfile(os.path.join(project_path, "Podfile")):
        reasons.append("CocoaPods (Podfile)")
    if os.path.isfile(os.path.join(project_path, "Podfile.lock")):
        reasons.append("CocoaPods (Podfile.lock)")

    # Cartfile
    if os.path.isfile(os.path.join(project_path, "Cartfile")):
        reasons.append("Carthage dependency manager")

    # Package.swift with Apple platform targets
    spm_path = os.path.join(project_path, "Package.swift")
    if os.path.isfile(spm_path):
        content = safe_read_text(spm_path, 8192)
        if ".macOS" in content or ".iOS" in content or ".tvOS" in content or ".watchOS" in content:
            reasons.append("Swift Package with Apple platform targets")

    # Info.plist
    if os.path.isfile(os.path.join(project_path, "Info.plist")):
        reasons.append("Info.plist (Apple bundle)")

    # Check Swift/ObjC files for macOS framework imports (sample first 200 files)
    mac_imports_found: set[str] = set()
    checked = 0
    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            if checked > 200:
                break
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".swift", ".m", ".mm", ".h"):
                fpath = os.path.join(dirpath, fname)
                content = safe_read_text(fpath, 8192)
                for fw in MAC_FRAMEWORK_IMPORTS:
                    if f"import {fw}" in content:
                        mac_imports_found.add(fw)
                checked += 1
        if checked > 200:
            break

    if mac_imports_found:
        reasons.append(f"Apple framework imports: {', '.join(sorted(mac_imports_found))}")

    # React Native with iOS directory
    ios_dir = os.path.join(project_path, "ios")
    if os.path.isdir(ios_dir) and os.path.isfile(os.path.join(project_path, "package.json")):
        # Check if React Native
        pkg = read_json_safe(os.path.join(project_path, "package.json"))
        if isinstance(pkg, dict):
            all_deps: set[str] = set()
            for key in ("dependencies", "devDependencies"):
                d = pkg.get(key)
                if isinstance(d, dict):
                    all_deps.update(d.keys())
            if "react-native" in all_deps:
                reasons.append("React Native iOS directory")

    info["mac_specific_reasons"] = reasons
    info["mac_specific"] = len(reasons) > 0


def _detect_deps_file(project_path: str) -> str | None:
    """Return the primary dependency file found."""
    priority = [
        "package.json", "pyproject.toml", "requirements.txt", "Pipfile",
        "setup.py", "setup.cfg", "Cargo.toml", "go.mod", "Gemfile",
        "composer.json", "build.gradle", "pom.xml", "pubspec.yaml",
        "Package.swift", "mix.exs", "stack.yaml", "CMakeLists.txt",
    ]
    for f in priority:
        if os.path.isfile(os.path.join(project_path, f)):
            return f
    return None


def _detect_monorepo(project_path: str, info: dict) -> None:
    """Detect if project is a monorepo with nested projects."""
    nested: list[str] = []
    # Look for multiple package.json or nested .git
    pkg_count = 0
    checked = 0

    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        rel = os.path.relpath(dirpath, project_path)
        if rel == ".":
            # Root level: don't count as nested
            if "package.json" in filenames:
                pkg_count += 1
            continue

        # Nested git repo
        if ".git" in set(os.listdir(dirpath)) if os.path.isdir(dirpath) else set():
            nested.append(dirpath)

        if "package.json" in filenames:
            pkg_count += 1
            if pkg_count > 1:
                nested.append(dirpath)

        for marker in ("pyproject.toml", "Cargo.toml", "go.mod"):
            if marker in filenames:
                nested.append(dirpath)
                break

        checked += 1
        if checked > 3000:
            break

    # Also check for workspace configs
    root_pkg = os.path.join(project_path, "package.json")
    if os.path.isfile(root_pkg):
        pkg = read_json_safe(root_pkg)
        if isinstance(pkg, dict) and "workspaces" in pkg:
            if not nested:
                nested.append("(workspaces declared in package.json)")

    # Cargo workspace
    cargo = os.path.join(project_path, "Cargo.toml")
    if os.path.isfile(cargo):
        content = safe_read_text(cargo)
        if "[workspace]" in content:
            if not nested:
                nested.append("(workspace declared in Cargo.toml)")

    # lerna.json
    if os.path.isfile(os.path.join(project_path, "lerna.json")):
        if not nested:
            nested.append("(Lerna monorepo)")

    # pnpm-workspace.yaml
    if os.path.isfile(os.path.join(project_path, "pnpm-workspace.yaml")):
        if not nested:
            nested.append("(pnpm workspace)")

    # Deduplicate
    nested = list(dict.fromkeys(nested))
    info["nested_projects"] = nested
    info["is_monorepo"] = len(nested) > 0


def _detect_deployment(project_path: str, info: dict) -> None:
    """Detect deployment configuration and infer deployment status."""
    targets: list[str] = []
    notes: list[str] = []

    # --- Cloud provider configs ---
    # AWS
    for aws_marker in ("serverless.yml", "serverless.yaml", "template.yaml",
                       "samconfig.toml", "appspec.yml", "buildspec.yml",
                       "cdk.json", ".elasticbeanstalk", "zappa_settings.json",
                       "copilot", "amplify.yml"):
        if os.path.exists(os.path.join(project_path, aws_marker)):
            targets.append(f"AWS ({aws_marker})")

    # GCP
    for gcp_marker in ("app.yaml", "app.yml", ".gcloudignore",
                        "cloudbuild.yaml", "firebase.json", ".firebaserc"):
        if os.path.exists(os.path.join(project_path, gcp_marker)):
            targets.append(f"GCP/Firebase ({gcp_marker})")

    # Azure
    for az_marker in ("azure-pipelines.yml", ".azure", "host.json"):
        if os.path.exists(os.path.join(project_path, az_marker)):
            targets.append(f"Azure ({az_marker})")

    # --- Hosting / PaaS ---
    # Vercel
    if os.path.isfile(os.path.join(project_path, "vercel.json")):
        targets.append("Vercel")
    # Netlify
    if os.path.isfile(os.path.join(project_path, "netlify.toml")):
        targets.append("Netlify")
    # Heroku
    if os.path.isfile(os.path.join(project_path, "Procfile")):
        targets.append("Heroku (Procfile)")
    if os.path.isfile(os.path.join(project_path, "app.json")):
        targets.append("Heroku/Render (app.json)")
    # Render
    if os.path.isfile(os.path.join(project_path, "render.yaml")):
        targets.append("Render")
    # Fly.io
    if os.path.isfile(os.path.join(project_path, "fly.toml")):
        targets.append("Fly.io")
    # Railway
    if os.path.isfile(os.path.join(project_path, "railway.json")):
        targets.append("Railway")
    # DigitalOcean App Platform
    if os.path.isfile(os.path.join(project_path, ".do/app.yaml")):
        targets.append("DigitalOcean App Platform")

    # --- Container orchestration ---
    for k8s_marker in ("k8s", "kubernetes", "helm", "chart", "kustomization.yaml"):
        candidate = os.path.join(project_path, k8s_marker)
        if os.path.exists(candidate):
            targets.append(f"Kubernetes ({k8s_marker})")
            break

    # Docker Compose (already detected as framework, but relevant for deployment)
    for dc in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        if os.path.isfile(os.path.join(project_path, dc)):
            if not any("Docker" in t for t in targets):
                targets.append(f"Docker Compose ({dc})")
            break

    # --- Blockchain deployment ---
    for chain_marker in ("hardhat.config.js", "hardhat.config.ts",
                         "truffle-config.js", "foundry.toml",
                         "migrations", "deploy"):
        candidate = os.path.join(project_path, chain_marker)
        if os.path.exists(candidate):
            # Check if deploy/ has actual deploy scripts
            if chain_marker == "deploy" and os.path.isdir(candidate):
                deploy_files = os.listdir(candidate)
                if any(f.endswith((".js", ".ts", ".py", ".sol")) for f in deploy_files):
                    targets.append("Blockchain (deploy scripts)")
            elif chain_marker != "deploy":
                targets.append(f"Blockchain ({chain_marker})")

    # --- CI/CD with deploy steps ---
    gh_workflows = os.path.join(project_path, ".github", "workflows")
    if os.path.isdir(gh_workflows):
        try:
            for wf_file in os.listdir(gh_workflows):
                if wf_file.endswith((".yml", ".yaml")):
                    content = safe_read_text(os.path.join(gh_workflows, wf_file), 16384).lower()
                    if any(kw in content for kw in ("deploy", "publish", "release",
                                                     "aws-actions", "azure/", "gcloud",
                                                     "vercel", "netlify", "heroku",
                                                     "docker push", "ghcr.io")):
                        targets.append(f"GitHub Actions deploy ({wf_file})")
                        break
        except OSError:
            pass

    # --- GitHub Pages ---
    # Check if homepageUrl suggests GitHub Pages or if there's a docs/ folder with index.html
    docs_index = os.path.join(project_path, "docs", "index.html")
    gh_pages_config = os.path.join(project_path, "_config.yml")
    if os.path.isfile(docs_index) or os.path.isfile(gh_pages_config):
        targets.append("GitHub Pages")

    # --- PyPI ---
    pyproject = os.path.join(project_path, "pyproject.toml")
    setup_py = os.path.join(project_path, "setup.py")
    if os.path.isfile(pyproject):
        content = safe_read_text(pyproject, 8192).lower()
        if "build-system" in content and ("setuptools" in content or "hatchling" in content
                                           or "flit" in content or "poetry" in content):
            if "[project]" in content or "[tool.poetry]" in content:
                targets.append("PyPI (publishable package)")
    elif os.path.isfile(setup_py):
        targets.append("PyPI (setup.py)")

    # --- npm ---
    pkg_json = os.path.join(project_path, "package.json")
    if os.path.isfile(pkg_json):
        pkg = read_json_safe(pkg_json)
        if isinstance(pkg, dict):
            if pkg.get("private") is not True and pkg.get("name", "").strip():
                if "publishConfig" in pkg or pkg.get("files"):
                    targets.append("npm (publishable package)")

    # --- Systemd / cron / supervisor ---
    for svc_marker in ("systemd", "supervisor", "supervisord.conf", "crontab"):
        if os.path.exists(os.path.join(project_path, svc_marker)):
            targets.append(f"System service ({svc_marker})")

    # --- .env files (suggest configured deployment) ---
    env_files = [f for f in (".env", ".env.production", ".env.staging")
                 if os.path.isfile(os.path.join(project_path, f))]
    if env_files:
        notes.append(f"Environment files found: {', '.join(env_files)}")

    # Deduplicate targets
    seen = set()
    unique_targets: list[str] = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            unique_targets.append(t)

    # Classify deployment status
    if unique_targets:
        # Check for evidence of actual deployment vs just config
        has_ci_deploy = any("Actions deploy" in t or "pipeline" in t.lower() for t in unique_targets)
        has_hosting = any(h in " ".join(unique_targets) for h in
                         ("Vercel", "Netlify", "Heroku", "Fly.io", "Render", "Railway",
                          "Firebase", "GitHub Pages", "DigitalOcean"))
        has_cloud = any(c in " ".join(unique_targets) for c in ("AWS", "GCP", "Azure"))

        if has_ci_deploy or has_hosting:
            info["deployment_status"] = "deployed"
            notes.append("Has automated deployment pipeline or hosting config")
        elif has_cloud:
            info["deployment_status"] = "configured"
            notes.append("Has cloud provider config but no clear deploy automation")
        else:
            info["deployment_status"] = "configured"
            notes.append("Has deployment-related config files")
    else:
        if info["has_docker"]:
            info["deployment_status"] = "containerized"
            notes.append("Dockerized but no deployment target detected")
        else:
            info["deployment_status"] = "local_only"
            notes.append("No deployment configuration detected")

    info["deployment_targets"] = unique_targets
    info["deployment_notes"] = notes


def _assess_migration(info: dict) -> None:
    """Compute migration readiness and notes."""
    notes: list[str] = []

    if info["mac_specific"]:
        # Check if there are non-mac components too
        non_mac_langs = [
            lang for lang in info["languages"]
            if lang not in ("Swift", "Objective-C", "C/C++/ObjC Header")
        ]
        non_mac_frameworks = [
            fw for fw in info["frameworks"]
            if fw not in ("SwiftUI", "UIKit", "AppKit", "CoreData", "Vapor")
        ]

        if non_mac_langs or non_mac_frameworks:
            info["migration_ready"] = "partial"
            notes.append("Has mac-specific components but also cross-platform code")
            for reason in info["mac_specific_reasons"]:
                notes.append(f"Mac dependency: {reason}")
        else:
            info["migration_ready"] = "no"
            notes.append("Fully mac/Apple-platform dependent")
            for reason in info["mac_specific_reasons"]:
                notes.append(f"Mac dependency: {reason}")
    else:
        info["migration_ready"] = "yes"
        notes.append("No mac-specific dependencies detected")

    # Additional notes
    if info["has_docker"]:
        notes.append("Has Docker config - good for containerized migration")
    if info["has_ci"]:
        notes.append("Has CI/CD - review pipeline for platform assumptions")
    if not info["has_tests"]:
        notes.append("No tests detected - migration validation will be manual")

    info["migration_notes"] = notes


# ---------------------------------------------------------------------------
# GitHub Correlation
# ---------------------------------------------------------------------------

def correlate_github(projects: list[dict], github_json_path: str | None) -> dict:
    """
    Match local projects to GitHub repos.
    Returns correlation report dict.
    """
    matched_entries: list[dict[str, object]] = []
    local_only: list[dict[str, object]] = []
    github_only: list[dict[str, object]] = []
    result: dict[str, object] = {
        "github_file_loaded": False,
        "total_github_repos": 0,
        "matched": matched_entries,
        "local_only": local_only,
        "github_only": github_only,
    }

    if not github_json_path or not os.path.isfile(github_json_path):
        # If no github json, just report all as local-only
        for p in projects:
            local_only.append({
                "name": p["name"],
                "path": p["path"],
                "git_remote": p.get("git_remote"),
            })
        return result

    github_data = read_json_safe(github_json_path)
    if github_data is None:
        log(f"WARNING: Could not parse GitHub JSON: {github_json_path}")
        return result

    result["github_file_loaded"] = True

    # Normalize github repos: support list of objects or gh api format
    gh_repos: list[dict] = []
    if isinstance(github_data, list):
        gh_repos = github_data
    elif isinstance(github_data, dict) and "repositories" in github_data:
        gh_repos = github_data["repositories"]
    elif isinstance(github_data, dict):
        # Maybe a single repo
        gh_repos = [github_data]

    result["total_github_repos"] = len(gh_repos)

    # Build lookup structures
    # By clone URLs (https and ssh variants)
    gh_by_url: dict[str, dict] = {}
    gh_by_name: dict[str, dict] = {}

    for repo in gh_repos:
        name = repo.get("name", repo.get("full_name", "")).split("/")[-1].lower()
        if name:
            gh_by_name[name] = repo

        for url_key in ("clone_url", "ssh_url", "html_url", "git_url", "url"):
            url = repo.get(url_key, "")
            if url:
                normalized = _normalize_git_url(url)
                if normalized:
                    gh_by_url[normalized] = repo

    matched_gh_names: set[str] = set()

    for project in projects:
        is_matched = False
        match_info = {
            "name": project["name"],
            "path": project["path"],
            "github_repo": None,
            "match_method": None,
            "sync_status": None,
        }

        # Try matching by remote URL first
        remote = project.get("git_remote", "")
        if remote:
            norm_remote = _normalize_git_url(remote)
            if norm_remote and norm_remote in gh_by_url:
                gh_repo = gh_by_url[norm_remote]
                match_info["github_repo"] = gh_repo.get("full_name", gh_repo.get("name", ""))
                match_info["match_method"] = "remote_url"
                is_matched = True
                repo_name = gh_repo.get("name", "").lower()
                matched_gh_names.add(repo_name)

        # Try matching by name
        if not is_matched:
            proj_name_lower = project["name"].lower()
            if proj_name_lower in gh_by_name:
                gh_repo = gh_by_name[proj_name_lower]
                match_info["github_repo"] = gh_repo.get("full_name", gh_repo.get("name", ""))
                match_info["match_method"] = "name"
                is_matched = True
                matched_gh_names.add(proj_name_lower)

        if is_matched:
            # Check sync status
            if project["has_git"]:
                match_info["sync_status"] = _check_sync_status(project["path"])
            matched_entries.append(match_info)
        else:
            local_only.append({
                "name": project["name"],
                "path": project["path"],
                "git_remote": project.get("git_remote"),
            })

    # Find GitHub repos not matched locally
    for repo in gh_repos:
        name = repo.get("name", "").lower()
        if name and name not in matched_gh_names:
            github_only.append({
                "name": repo.get("name", ""),
                "full_name": repo.get("full_name", ""),
                "html_url": repo.get("html_url", ""),
                "description": repo.get("description", ""),
            })

    return result


def _normalize_git_url(url: str) -> str:
    """Normalize a git URL to a comparable form (owner/repo)."""
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # SSH: git@github.com:owner/repo
    ssh_match = re.search(r"[:/]([^/:]+/[^/:]+)$", url)
    if ssh_match:
        return ssh_match.group(1).lower()

    # HTTPS: https://github.com/owner/repo
    https_match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", url)
    if https_match:
        return https_match.group(1).lower()

    return ""


def _check_sync_status(project_path: str) -> str:
    """Check if local repo is ahead/behind/diverged from remote."""
    # Try to fetch without actually downloading (just check)
    run_git(["fetch", "--dry-run", "origin"], cwd=project_path, timeout=10)

    local_hash = run_git(["rev-parse", "HEAD"], cwd=project_path)
    remote_ref = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=project_path)

    if not remote_ref:
        return "no_upstream"

    remote_hash = run_git(["rev-parse", remote_ref], cwd=project_path)

    if not local_hash or not remote_hash:
        return "unknown"

    if local_hash == remote_hash:
        return "in_sync"

    # Check ahead/behind
    counts = run_git(["rev-list", "--left-right", "--count", f"{remote_ref}...HEAD"], cwd=project_path)
    if counts:
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])
            if ahead > 0 and behind > 0:
                return f"diverged (ahead {ahead}, behind {behind})"
            elif ahead > 0:
                return f"ahead by {ahead}"
            elif behind > 0:
                return f"behind by {behind}"
            else:
                return "in_sync"

    return "unknown"


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_json_report(projects: list[dict], correlation: dict, output_path: str) -> None:
    """Write JSON report."""
    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scanner_version": "1.0",
        "total_projects": len(projects),
        "projects": projects,
        "github_correlation": correlation,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    log(f"JSON report written to: {output_path}")


def generate_markdown_report(projects: list[dict], correlation: dict, output_path: str) -> None:
    """Write markdown report."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    def add(line: str = "") -> None:
        lines.append(line)

    # ---- Executive Summary ----
    add("# Project Scanner Report")
    add(f"\n*Generated: {now_str}*\n")

    total = len(projects)
    total_disk = sum(p["disk_size_mb"] for p in projects)
    git_count = sum(1 for p in projects if p["has_git"])
    test_count = sum(1 for p in projects if p["has_tests"])
    ci_count = sum(1 for p in projects if p["has_ci"])
    docker_count = sum(1 for p in projects if p["has_docker"])
    mac_count = sum(1 for p in projects if p["mac_specific"])

    add("## Executive Summary\n")
    add("| Metric | Value |")
    add("|--------|-------|")
    add(f"| Total projects | {total} |")
    add(f"| Total disk usage | {total_disk:,.1f} MB ({total_disk/1024:.1f} GB) |")
    add(f"| Git repositories | {git_count} |")
    add(f"| With tests | {test_count} |")
    add(f"| With CI/CD | {ci_count} |")
    add(f"| With Docker | {docker_count} |")
    add(f"| Mac-specific | {mac_count} |")
    add()

    # Language breakdown
    lang_counts: dict[str, int] = collections.Counter()
    for p in projects:
        if p["primary_language"]:
            lang_counts[p["primary_language"]] += 1

    if lang_counts:
        add("### Language Breakdown\n")
        add("| Language | Projects |")
        add("|----------|----------|")
        for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
            bar = "#" * count
            add(f"| {lang} | {count} {bar} |")
        add()

    # Activity breakdown
    activity_counts: dict[str, int] = collections.Counter()
    for p in projects:
        activity_counts[p["activity"]] += 1

    add("### Activity Breakdown\n")
    add("| Status | Projects | Description |")
    add("|--------|----------|-------------|")
    status_desc = {
        "active": "Last commit within 30 days",
        "recent": "Last commit 31-90 days ago",
        "stale": "Last commit 91-180 days ago",
        "inactive": "Last commit 181-365 days ago",
        "dead": "Last commit over 365 days ago",
        "unknown": "No git history available",
    }
    for status in ["active", "recent", "stale", "inactive", "dead", "unknown"]:
        count = activity_counts.get(status, 0)
        if count > 0:
            add(f"| **{status.upper()}** | {count} | {status_desc.get(status, '')} |")
    add()

    # ---- Migration Readiness ----
    add("## Migration Readiness Summary\n")
    migration_counts: dict[str, int] = collections.Counter()
    for p in projects:
        migration_counts[p["migration_ready"]] += 1

    ready = migration_counts.get("yes", 0)
    partial = migration_counts.get("partial", 0)
    blocked = migration_counts.get("no", 0)

    add("| Readiness | Count | Percentage |")
    add("|-----------|-------|------------|")
    if total > 0:
        add(f"| Ready (cross-platform) | {ready} | {ready*100//total}% |")
        add(f"| Partial (mixed) | {partial} | {partial*100//total}% |")
        add(f"| Blocked (mac-dependent) | {blocked} | {blocked*100//total}% |")
    add()

    # ---- Deployment Status ----
    deploy_counts: dict[str, int] = collections.Counter()
    for p in projects:
        deploy_counts[p.get("deployment_status", "unknown")] += 1

    add("### Deployment Status\n")
    add("| Status | Projects | Description |")
    add("|--------|----------|-------------|")
    deploy_desc = {
        "deployed": "Has hosting/CI-deploy pipeline",
        "configured": "Has cloud/deploy config but no automation",
        "containerized": "Dockerized but no deploy target",
        "local_only": "No deployment config detected",
        "unknown": "Could not determine",
    }
    for status in ["deployed", "configured", "containerized", "local_only", "unknown"]:
        count = deploy_counts.get(status, 0)
        if count > 0:
            add(f"| **{status}** | {count} | {deploy_desc.get(status, '')} |")
    add()

    # Deployed projects detail
    deployed_projects = [p for p in projects if p.get("deployment_status") in ("deployed", "configured")]
    if deployed_projects:
        add("#### Deployed / Configured Projects\n")
        add("| Project | Status | Targets |")
        add("|---------|--------|---------|")
        for p in deployed_projects:
            targets_str = ", ".join(p.get("deployment_targets", [])[:3]) or "-"
            add(f"| {p['name']} | {p.get('deployment_status')} | {targets_str} |")
        add()

    # ---- Full Project Table ----
    add("## All Projects (sorted by activity)\n")

    # Sort: active first, then by commit age
    activity_order = {"active": 0, "recent": 1, "stale": 2, "inactive": 3, "dead": 4, "unknown": 5}
    sorted_projects = sorted(
        projects,
        key=lambda p: (activity_order.get(p["activity"], 5), p.get("last_commit_age_days") or 9999),
    )

    add("| # | Name | Language | Activity | Age (days) | Size (MB) | Git | Tests | CI | Docker | Deploy | Migration |")
    add("|---|------|----------|----------|------------|-----------|-----|-------|-----|--------|--------|-----------|")

    def yes_no(value: bool) -> str:
        return "Y" if value else "-"

    for i, p in enumerate(sorted_projects, 1):
        age = p["last_commit_age_days"] if p["last_commit_age_days"] is not None else "-"
        lang = p["primary_language"] or "-"
        deploy = p.get("deployment_status", "unknown")
        add(
            f"| {i} | [{p['name']}]({p['path']}) | {lang} | "
            f"{p['activity']} | {age} | {p['disk_size_mb']} | "
            f"{yes_no(p['has_git'])} | {yes_no(p['has_tests'])} | "
            f"{yes_no(p['has_ci'])} | {yes_no(p['has_docker'])} | "
            f"{deploy} | {p['migration_ready']} |"
        )
    add()

    # ---- Mac-Specific Projects ----
    mac_projects = [p for p in projects if p["mac_specific"]]
    if mac_projects:
        add("## Mac-Specific Projects\n")
        for p in mac_projects:
            add(f"### {p['name']}")
            add(f"- **Path**: `{p['path']}`")
            add(f"- **Migration**: {p['migration_ready']}")
            add("- **Reasons**:")
            for reason in p["mac_specific_reasons"]:
                add(f"  - {reason}")
            add()

    # ---- Frameworks Summary ----
    fw_counts: dict[str, int] = collections.Counter()
    for p in projects:
        for fw in p["frameworks"]:
            fw_counts[fw] += 1

    if fw_counts:
        add("## Framework Usage\n")
        add("| Framework | Projects |")
        add("|-----------|----------|")
        for fw, count in sorted(fw_counts.items(), key=lambda x: -x[1]):
            add(f"| {fw} | {count} |")
        add()

    # ---- Monorepos ----
    monorepos = [p for p in projects if p["is_monorepo"]]
    if monorepos:
        add("## Monorepos\n")
        for p in monorepos:
            add(f"### {p['name']}")
            add(f"- **Path**: `{p['path']}`")
            add(f"- **Nested projects**: {len(p['nested_projects'])}")
            for np_path in p["nested_projects"][:20]:
                add(f"  - `{np_path}`")
            if len(p["nested_projects"]) > 20:
                add(f"  - ... and {len(p['nested_projects']) - 20} more")
            add()

    # ---- GitHub Correlation ----
    add("## GitHub Correlation\n")
    if not correlation.get("github_file_loaded"):
        add("*No GitHub repos JSON provided. Provide `--github-json` to enable correlation.*\n")
    else:
        add(f"- **GitHub repos loaded**: {correlation['total_github_repos']}")
        add(f"- **Matched locally**: {len(correlation['matched'])}")
        add(f"- **Local only**: {len(correlation['local_only'])}")
        add(f"- **GitHub only**: {len(correlation['github_only'])}")
        add()

        if correlation["matched"]:
            add("### Matched Projects\n")
            add("| Local Project | GitHub Repo | Match Method | Sync Status |")
            add("|---------------|-------------|--------------|-------------|")
            for m in correlation["matched"]:
                add(f"| {m['name']} | {m['github_repo']} | {m['match_method']} | {m.get('sync_status', '-')} |")
            add()

        if correlation["local_only"]:
            add("### Local-Only Projects (not on GitHub)\n")
            add("| Project | Remote |")
            add("|---------|--------|")
            for lo in correlation["local_only"]:
                remote = lo.get("git_remote") or "-"
                add(f"| {lo['name']} | {remote} |")
            add()

        if correlation["github_only"]:
            add("### GitHub-Only Repos (not found locally)\n")
            add("| Repository | URL | Description |")
            add("|------------|-----|-------------|")
            for go in correlation["github_only"]:
                desc = (go.get("description") or "-")[:80]
                add(f"| {go.get('full_name', go['name'])} | {go.get('html_url', '-')} | {desc} |")
            add()

    # ---- Recommendations ----
    add("## Recommendations\n")

    dead_projects = [p for p in projects if p["activity"] == "dead"]
    if dead_projects:
        add(f"### Archive Candidates ({len(dead_projects)} dead projects)")
        add("These projects have not been committed to in over a year:\n")
        for p in sorted(dead_projects, key=lambda x: x.get("last_commit_age_days") or 9999, reverse=True):
            age = p["last_commit_age_days"] or "?"
            add(f"- **{p['name']}** ({age} days, {p['disk_size_mb']} MB) - `{p['path']}`")
        add()

    no_git = [p for p in projects if not p["has_git"]]
    if no_git:
        add(f"### Projects Without Git ({len(no_git)} projects)")
        add("Consider initializing version control:\n")
        for p in no_git:
            add(f"- **{p['name']}** ({p['disk_size_mb']} MB) - `{p['path']}`")
        add()

    no_tests_active = [p for p in projects if not p["has_tests"] and p["activity"] in ("active", "recent")]
    if no_tests_active:
        add(f"### Active Projects Without Tests ({len(no_tests_active)} projects)")
        add("These active projects would benefit from test coverage:\n")
        for p in no_tests_active:
            add(f"- **{p['name']}** ({p['primary_language'] or 'unknown'}) - `{p['path']}`")
        add()

    large_projects = sorted(projects, key=lambda p: p["disk_size_mb"], reverse=True)[:10]
    if large_projects and large_projects[0]["disk_size_mb"] > 100:
        add("### Largest Projects by Disk Usage")
        add("Consider cleanup (prune git history, remove build artifacts):\n")
        for p in large_projects:
            if p["disk_size_mb"] > 100:
                add(f"- **{p['name']}** - {p['disk_size_mb']:,.1f} MB - `{p['path']}`")
        add()

    if blocked > 0:
        add("### Migration-Blocked Projects")
        add("These projects are fully mac-dependent and cannot be migrated as-is:\n")
        for p in projects:
            if p["migration_ready"] == "no":
                add(f"- **{p['name']}** - {', '.join(p['mac_specific_reasons'][:3])}")
        add()

    add("---")
    add("*Report generated by PromptClaw Project Scanner v1.0*")

    # Write
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"Markdown report written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PromptClaw Project Scanner - Discover and analyze local projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python project_scanner.py --dirs ~/Programming
              python project_scanner.py --dirs ~/Programming ~/Work --output-dir ./reports
              python project_scanner.py --dirs ~/Programming --github-json repos.json --output-dir ./reports
        """),
    )
    parser.add_argument(
        "--dirs", nargs="+", required=True,
        help="Root directories to scan for projects",
    )
    parser.add_argument(
        "--github-json", default=None,
        help="Path to JSON file of GitHub repos (from `gh repo list --json ...`)",
    )
    parser.add_argument(
        "--output-dir", default="./reports",
        help="Directory for output reports (default: ./reports)",
    )
    parser.add_argument(
        "--skip-size", action="store_true",
        help="Skip disk size calculation (faster for large scans)",
    )
    parser.add_argument(
        "--max-depth", type=int, default=10,
        help="Maximum directory recursion depth (default: 10)",
    )

    args = parser.parse_args()

    log("PromptClaw Project Scanner v1.0")
    log(f"Scanning directories: {args.dirs}")

    now = datetime.datetime.now(datetime.timezone.utc)

    # Phase 1: Discovery
    log("--- Phase 1: Discovery ---")
    project_paths = discover_projects(args.dirs, max_depth=args.max_depth)

    if not project_paths:
        log("No projects found. Exiting.")
        sys.exit(0)

    # Phase 2: Analysis
    log("--- Phase 2: Analysis ---")
    projects: list[dict] = []
    for i, path in enumerate(project_paths, 1):
        if not os.path.isdir(path):
            log(f"  [{i}/{len(project_paths)}] SKIPPING (missing): {path}")
            continue
        log(f"  [{i}/{len(project_paths)}] Analyzing: {os.path.basename(path)}")
        try:
            info = analyze_project(path, now)
            if args.skip_size:
                info["disk_size_mb"] = 0.0
            projects.append(info)
        except Exception as exc:
            log(f"  ERROR analyzing {path}: {exc}")
            continue

    # Phase 3: GitHub Correlation
    log("--- Phase 3: GitHub Correlation ---")
    correlation = correlate_github(projects, args.github_json)

    # Phase 4: Reports
    log("--- Phase 4: Report Generation ---")
    output_dir = os.path.expanduser(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"project_scan_{timestamp}.json")
    md_path = os.path.join(output_dir, f"project_scan_{timestamp}.md")

    generate_json_report(projects, correlation, json_path)
    generate_markdown_report(projects, correlation, md_path)

    # Also write a "latest" symlink / copy
    latest_json = os.path.join(output_dir, "project_scan_latest.json")
    latest_md = os.path.join(output_dir, "project_scan_latest.md")
    for src, dst in [(json_path, latest_json), (md_path, latest_md)]:
        try:
            if os.path.exists(dst) or os.path.islink(dst):
                os.remove(dst)
            os.symlink(os.path.basename(src), dst)
        except OSError:
            # Fallback: just copy
            try:
                import shutil
                shutil.copy2(src, dst)
            except OSError:
                pass

    # Print summary to stdout
    print(f"\n{'='*60}")
    print(" PromptClaw Project Scanner - Summary")
    print(f"{'='*60}")
    print(f" Projects found:      {len(projects)}")
    print(f" Total disk usage:    {sum(p['disk_size_mb'] for p in projects):,.1f} MB")
    print(f" Git repos:           {sum(1 for p in projects if p['has_git'])}")
    print(f" With tests:          {sum(1 for p in projects if p['has_tests'])}")
    print(f" With CI/CD:          {sum(1 for p in projects if p['has_ci'])}")
    print(f" Mac-specific:        {sum(1 for p in projects if p['mac_specific'])}")
    print(f" Deployed:            {sum(1 for p in projects if p.get('deployment_status') == 'deployed')}")
    print(f" Deploy configured:   {sum(1 for p in projects if p.get('deployment_status') == 'configured')}")
    print(f" Local only:          {sum(1 for p in projects if p.get('deployment_status') == 'local_only')}")
    print(f" Migration ready:     {sum(1 for p in projects if p['migration_ready'] == 'yes')}")
    print(f" Migration partial:   {sum(1 for p in projects if p['migration_ready'] == 'partial')}")
    print(f" Migration blocked:   {sum(1 for p in projects if p['migration_ready'] == 'no')}")
    print(f"{'='*60}")
    print(f" JSON report:  {json_path}")
    print(f" MD report:    {md_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
