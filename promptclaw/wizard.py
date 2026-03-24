from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import load_config, save_config
from .models import AgentConfig
from .ui import banner, files_written_card, follow_up_card, question_card, status_line, summary_card
from .utils import ensure_dir, slugify, truncate, write_text


DEFAULT_AGENT_STRENGTHS: dict[str, str] = {
    "codex": "implementation, coding, refactoring, bug fixes, tests, and concrete execution",
    "claude": "architecture, specifications, reviews, verification, and high-level orchestration",
    "gemini": "research, synthesis, documentation, comparisons, and polished write-ups",
}

VAGUE_MARKERS = {
    "anything",
    "everything",
    "whatever",
    "something",
    "general",
    "various",
    "many things",
    "all kinds",
    "not sure",
    "tbd",
}

CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "coding": ("code", "coding", "developer", "implementation", "implement", "ship", "script"),
    "implementation": ("implementation", "implement", "execute", "build", "ship", "develop"),
    "testing": ("test", "tests", "pytest", "qa", "quality", "verification testing"),
    "refactoring": ("refactor", "cleanup", "rewrite", "modernize"),
    "architecture": ("architecture", "design", "system", "orchestrator", "workflow", "topology"),
    "specification": ("spec", "specification", "requirements", "acceptance criteria", "plan"),
    "verification": ("verify", "verification", "review", "audit", "critique", "validator"),
    "analysis": ("analysis", "analyze", "reason", "assessment", "evaluate"),
    "research": ("research", "study", "compare", "investigate", "findings"),
    "writing": ("write", "writing", "copy", "narrative", "content"),
    "docs": ("docs", "documentation", "manual", "guide", "readme"),
    "synthesis": ("synthesis", "summarize", "summary", "distill", "combine"),
}

DEFAULT_ROSTER = ["codex", "claude", "gemini"]


@dataclass
class WizardQuestion:
    key: str
    prompt: str
    hint: str = ""
    required: bool = True
    is_follow_up: bool = False
    default: str = ""


@dataclass
class TranscriptEntry:
    key: str
    prompt: str
    answer: str
    is_follow_up: bool = False


@dataclass
class StartupProfile:
    project_name: str
    answers: dict[str, str] = field(default_factory=dict)
    transcript: list[TranscriptEntry] = field(default_factory=list)
    agent_roster: list[str] = field(default_factory=lambda: list(DEFAULT_ROSTER))
    agent_strengths: dict[str, str] = field(default_factory=dict)
    files_written: list[Path] = field(default_factory=list)

    def answer(self, key: str, default: str = "") -> str:
        return self.answers.get(key, default).strip()


class StartupWizard:
    def __init__(
        self,
        project_root: Path,
        project_name: str,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ) -> None:
        self.project_root = project_root
        self.project_name = project_name
        self.input_func = input_func
        self.output_func = output_func
        self.profile = StartupProfile(project_name=project_name)
        self._asked_keys: set[str] = set()

    def run(self) -> StartupProfile:
        self.output_func(banner(self.project_name, "Startup Wizard"))
        self.output_func(status_line("We will build your starter prompts one question at a time. 🎈", "🪄"))

        queue = list(self._base_questions())
        index = 0
        while index < len(queue):
            question = queue[index]
            if question.key in self._asked_keys:
                index += 1
                continue
            answer = self._ask_question(index=index + 1, question=question)
            self._record_answer(question, answer)

            if question.key == "agent_roster":
                self.profile.agent_roster = parse_agent_roster(answer)
                agent_questions = self._agent_strength_questions()
                queue[index + 1:index + 1] = agent_questions

            follow_ups = self._follow_up_questions(question.key, answer)
            if follow_ups:
                queue[index + 1:index + 1] = follow_ups
            index += 1

        self._apply_profile_to_project()
        self.output_func(summary_card(
            [
                f"Project: {self.project_name}",
                f"Agents: {', '.join(self.profile.agent_roster)}",
                f"Routing style: {truncate(self.profile.answer('routing_examples') or 'content-based routing', 70)}",
                "Your startup prompts are ready for bootstrap. 🦀✨",
            ],
            title=" Ready ",
        ))
        self.output_func(files_written_card(self.profile.files_written, self.project_root))
        self.output_func(status_line("Next move: run `promptclaw bootstrap .` from inside the project. 🚀", "🎉"))
        return self.profile

    def _base_questions(self) -> list[WizardQuestion]:
        return [
            WizardQuestion(
                key="project_pitch",
                prompt="What kind of PromptClaw are we building?",
                hint="Name the domain, mission, and what makes this claw useful.",
            ),
            WizardQuestion(
                key="task_families",
                prompt="What are the top task families it should handle?",
                hint="Examples: code changes, architecture, research, docs, planning, operations.",
            ),
            WizardQuestion(
                key="success_outputs",
                prompt="What should it usually produce for the user?",
                hint="Examples: code + tests, implementation plans, docs, reports, checklists.",
            ),
            WizardQuestion(
                key="agent_roster",
                prompt="Who is on the claw team?",
                hint="Comma-separated agent names. Press Enter for codex, claude, gemini.",
                required=False,
                default=", ".join(DEFAULT_ROSTER),
            ),
            WizardQuestion(
                key="routing_examples",
                prompt="How should the orchestrator choose a lead agent?",
                hint="Describe routing by content need, not fixed sequence. One concrete example helps.",
            ),
            WizardQuestion(
                key="verification_policy",
                prompt="What is the verification style?",
                hint="Examples: always verify, verify risky work only, lightweight notes for docs.",
            ),
            WizardQuestion(
                key="autonomy",
                prompt="How autonomous should the claw be once it starts?",
                hint="Examples: fully autonomous except ambiguity, mostly autonomous, human-in-the-loop.",
            ),
            WizardQuestion(
                key="ambiguity",
                prompt="When should it stop and ask the user a question?",
                hint="Mention what details matter most: goal, format, constraints, deadline, sources, permissions.",
            ),
            WizardQuestion(
                key="boundaries",
                prompt="What should it never do?",
                hint="Name hard red lines, risky actions, or quality boundaries.",
            ),
        ]

    def _agent_strength_questions(self) -> list[WizardQuestion]:
        questions: list[WizardQuestion] = []
        for agent_name in self.profile.agent_roster:
            default = DEFAULT_AGENT_STRENGTHS.get(agent_name, "general problem-solving, execution, and coordination")
            questions.append(
                WizardQuestion(
                    key=f"agent_{agent_name}_strengths",
                    prompt=f"What is {agent_name} best at in this claw?",
                    hint="Name the jobs it should lead on or verify.",
                    required=False,
                    default=default,
                )
            )
        return questions

    def _ask_question(self, index: int, question: WizardQuestion) -> str:
        card = follow_up_card(question.prompt, question.hint) if question.is_follow_up else question_card(index, question.prompt, question.hint)
        self.output_func(card)
        attempts = 0
        while True:
            raw = self.input_func("👉 ").strip()
            attempts += 1
            if raw:
                return raw
            if question.default.strip():
                self.output_func(status_line(f"Using default: {question.default}", "🍀"))
                return question.default
            if not question.required:
                return ""
            if attempts >= 2:
                self.output_func(status_line("I still need a little signal here. A short phrase is enough. ✨", "🧩"))
            else:
                self.output_func(status_line("Give me a tiny bit more detail and I’ll keep going. 🐾", "💬"))

    def _record_answer(self, question: WizardQuestion, answer: str) -> None:
        self._asked_keys.add(question.key)
        self.profile.answers[question.key] = answer.strip()
        self.profile.transcript.append(
            TranscriptEntry(
                key=question.key,
                prompt=question.prompt,
                answer=answer.strip(),
                is_follow_up=question.is_follow_up,
            )
        )
        if question.key.startswith("agent_") and question.key.endswith("_strengths"):
            agent_name = question.key.removeprefix("agent_").removesuffix("_strengths")
            self.profile.agent_strengths[agent_name] = answer.strip()

    def _follow_up_questions(self, question_key: str, answer: str) -> list[WizardQuestion]:
        follow_ups: list[WizardQuestion] = []
        lowered = answer.lower().strip()
        roster = self.profile.agent_roster

        if question_key == "project_pitch" and looks_vague(answer):
            follow_ups.append(
                WizardQuestion(
                    key="project_pitch_focus",
                    prompt="What domain or arena is this claw for first?",
                    hint="Examples: software teams, creative projects, operations, research, personal productivity.",
                    is_follow_up=True,
                )
            )

        if question_key == "task_families" and looks_vague(answer):
            follow_ups.append(
                WizardQuestion(
                    key="task_families_priority",
                    prompt="Name the top 3 task families that matter most on day one.",
                    hint="A short comma-separated answer is perfect.",
                    is_follow_up=True,
                )
            )

        if question_key == "success_outputs":
            if mentions_any(lowered, ["code", "implement", "build", "script", "module"]) and not mentions_any(lowered, ["test", "tests", "diff", "notes"]):
                follow_ups.append(
                    WizardQuestion(
                        key="coding_artifacts",
                        prompt="For code tasks, should the claw return code only, code + tests, or code + tests + notes?",
                        hint="This helps the wizard shape the starter prompts.",
                        is_follow_up=True,
                    )
                )
            if mentions_any(lowered, ["research", "docs", "documentation", "writing", "analysis"]) and not mentions_any(lowered, ["cite", "citation", "source", "sources", "reference"]):
                follow_ups.append(
                    WizardQuestion(
                        key="research_style",
                        prompt="For research and writing tasks, should it cite sources, summarize cleanly, or do both depending on the task?",
                        hint="A short preference is enough.",
                        is_follow_up=True,
                    )
                )

        if question_key == "routing_examples":
            agent_mentions = any(agent.lower() in lowered for agent in roster)
            if not agent_mentions and not mentions_any(lowered, ["code", "architecture", "docs", "research", "verify", "content"]):
                follow_ups.append(
                    WizardQuestion(
                        key="routing_examples_detail",
                        prompt="Give one concrete routing example, like 'code bug -> codex' or 'architecture review -> claude'.",
                        hint="One or two examples is enough.",
                        is_follow_up=True,
                    )
                )

        if question_key == "autonomy" and mentions_any(lowered, ["fully", "automatic", "automated", "autonomous", "just do it"]):
            follow_ups.append(
                WizardQuestion(
                    key="permission_boundaries",
                    prompt="Name any actions that should still require explicit user approval.",
                    hint="Examples: production deploys, destructive file changes, external publishing.",
                    required=False,
                    is_follow_up=True,
                )
            )

        if question_key == "ambiguity" and (looks_vague(answer) or not mentions_any(lowered, ["goal", "format", "constraint", "deadline", "source", "permission", "scope"])):
            follow_ups.append(
                WizardQuestion(
                    key="ambiguity_focus",
                    prompt="When the task is fuzzy, what should the first follow-up question try to pin down?",
                    hint="Examples: goal, format, constraints, deadline, sources, permissions.",
                    is_follow_up=True,
                )
            )

        if question_key == "boundaries" and looks_vague(answer):
            follow_ups.append(
                WizardQuestion(
                    key="hard_boundaries",
                    prompt="Give two hard red lines for this claw.",
                    hint="Examples: no destructive edits without permission; no invented sources.",
                    is_follow_up=True,
                )
            )

        if question_key.startswith("agent_") and question_key.endswith("_strengths"):
            agent_name = question_key.removeprefix("agent_").removesuffix("_strengths")
            if agent_name not in DEFAULT_AGENT_STRENGTHS and looks_vague(answer):
                follow_ups.append(
                    WizardQuestion(
                        key=f"agent_{agent_name}_detail",
                        prompt=f"What kinds of tasks should {agent_name} own most often?",
                        hint="List a few task types or artifacts.",
                        is_follow_up=True,
                    )
                )

        return [item for item in follow_ups if item.key not in self._asked_keys]

    def _apply_profile_to_project(self) -> None:
        files_written: list[Path] = []

        vision_path = self.project_root / "prompts/00-project-vision.md"
        write_text(vision_path, render_project_vision(self.profile))
        files_written.append(vision_path)

        roles_path = self.project_root / "prompts/01-agent-roles.md"
        write_text(roles_path, render_agent_roles(self.profile))
        files_written.append(roles_path)

        routing_path = self.project_root / "prompts/02-routing-rules.md"
        write_text(routing_path, render_routing_rules(self.profile))
        files_written.append(routing_path)

        startup_profile_path = self.project_root / "docs/STARTUP_PROFILE.md"
        write_text(startup_profile_path, render_startup_profile(self.profile))
        files_written.append(startup_profile_path)

        startup_transcript_path = self.project_root / "docs/STARTUP_TRANSCRIPT.md"
        write_text(startup_transcript_path, render_transcript(self.profile))
        files_written.append(startup_transcript_path)

        config = load_config(self.project_root)
        config.project.description = truncate(self.profile.answer("project_pitch"), 160)

        chosen_agents = set(self.profile.agent_roster)
        if config.control_plane.agent and config.control_plane.agent not in chosen_agents:
            config.control_plane.agent = next(iter(chosen_agents), config.control_plane.agent)

        for existing_name, existing_agent in list(config.agents.items()):
            if existing_name not in chosen_agents:
                existing_agent.enabled = False

        for agent_name in self.profile.agent_roster:
            strengths = self.profile.agent_strengths.get(agent_name) or DEFAULT_AGENT_STRENGTHS.get(agent_name, "general problem-solving")
            instruction_rel = Path("prompts/agents") / f"{slugify(agent_name)}.md"
            instruction_path = self.project_root / instruction_rel
            write_text(instruction_path, render_agent_instruction(self.profile, agent_name, strengths))
            files_written.append(instruction_path)

            capabilities = infer_capabilities(strengths, agent_name)
            if agent_name in config.agents:
                agent = config.agents[agent_name]
                agent.enabled = True
                agent.capabilities = capabilities
                agent.instruction_file = str(instruction_rel).replace("\\", "/")
            else:
                config.agents[agent_name] = AgentConfig(
                    name=agent_name,
                    enabled=True,
                    kind="mock",
                    capabilities=capabilities,
                    instruction_file=str(instruction_rel).replace("\\", "/"),
                )

        verification_text = (self.profile.answer("verification_policy") + " " + self.profile.answer("routing_examples")).lower()
        if mentions_any(verification_text, ["no verify", "skip verify", "without verify", "no verifier"]):
            config.routing.verification_enabled = False
        else:
            config.routing.verification_enabled = True

        ambiguity_text = self.profile.answer("ambiguity").lower()
        config.routing.ask_user_on_ambiguity = not mentions_any(ambiguity_text, ["never ask", "do not ask", "dont ask", "don't ask"])

        save_config(self.project_root, config)
        files_written.append(self.project_root / "promptclaw.json")

        onboarding_dir = self.project_root / ".promptclaw/onboarding"
        ensure_dir(onboarding_dir)
        onboarding_session = onboarding_dir / "startup-session.md"
        write_text(onboarding_session, render_transcript(self.profile, title="# Startup Session"))
        files_written.append(onboarding_session)

        self.profile.files_written = files_written


def run_startup_wizard(
    project_root: Path,
    project_name: str,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> StartupProfile:
    wizard = StartupWizard(
        project_root=project_root,
        project_name=project_name,
        input_func=input_func,
        output_func=output_func,
    )
    return wizard.run()


def parse_agent_roster(raw: str) -> list[str]:
    if not raw.strip():
        return list(DEFAULT_ROSTER)
    parts = [normalize_agent_name(part) for part in raw.replace("/", ",").split(",")]
    deduped: list[str] = []
    for name in parts:
        if name and name not in deduped:
            deduped.append(name)
    return deduped or list(DEFAULT_ROSTER)


def normalize_agent_name(name: str) -> str:
    cleaned = name.strip().lower().replace(" ", "-")
    aliases = {
        "gpt-codex": "codex",
        "openai-codex": "codex",
        "anthropic-claude": "claude",
        "google-gemini": "gemini",
    }
    return aliases.get(cleaned, cleaned)


def infer_capabilities(text: str, agent_name: str) -> list[str]:
    lowered = text.lower()
    capabilities: list[str] = []
    for capability, keywords in CAPABILITY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            capabilities.append(capability)
    if capabilities:
        return sorted(dict.fromkeys(capabilities))
    if agent_name in DEFAULT_AGENT_STRENGTHS:
        default_text = DEFAULT_AGENT_STRENGTHS[agent_name]
        return infer_capabilities(default_text, "fallback")
    return ["analysis", "writing"]


def looks_vague(text: str) -> bool:
    lowered = text.strip().lower()
    if len(lowered) < 14:
        return True
    return any(marker in lowered for marker in VAGUE_MARKERS)


def mentions_any(text: str, tokens: list[str]) -> bool:
    return any(token in text for token in tokens)


def as_bullets(text: str) -> list[str]:
    normalized = text.replace(";", "\n").replace("•", "\n").replace("|", "\n")
    if "," in normalized and "\n" not in normalized:
        normalized = normalized.replace(",", "\n")
    items = [item.strip(" -") for item in normalized.splitlines() if item.strip()]
    return items or [text.strip()]


def sentence_or_list(text: str) -> str:
    items = as_bullets(text)
    if len(items) == 1:
        return items[0]
    return "\n".join(f"- {item}" for item in items)


def render_project_vision(profile: StartupProfile) -> str:
    sections = [
        "# Project Vision",
        "",
        "## Mission",
        profile.answer("project_pitch"),
    ]
    if profile.answer("project_pitch_focus"):
        sections.extend(["", "## Initial domain focus", profile.answer("project_pitch_focus")])
    sections.extend([
        "",
        "## Primary task families",
        sentence_or_list(profile.answer("task_families_priority") or profile.answer("task_families")),
        "",
        "## Typical outputs",
        sentence_or_list(profile.answer("success_outputs")),
    ])
    if profile.answer("coding_artifacts"):
        sections.extend(["", "## Coding default", profile.answer("coding_artifacts")])
    if profile.answer("research_style"):
        sections.extend(["", "## Research and writing default", profile.answer("research_style")])
    sections.extend([
        "",
        "## Autonomy posture",
        profile.answer("autonomy"),
    ])
    if profile.answer("permission_boundaries"):
        sections.extend(["", "## Approval gates", sentence_or_list(profile.answer("permission_boundaries"))])
    sections.extend([
        "",
        "## When to ask the user",
        profile.answer("ambiguity"),
    ])
    if profile.answer("ambiguity_focus"):
        sections.extend(["", "## First clarification target", profile.answer("ambiguity_focus")])
    sections.extend([
        "",
        "## Hard boundaries",
        sentence_or_list(profile.answer("hard_boundaries") or profile.answer("boundaries")),
        "",
        "## Verification posture",
        profile.answer("verification_policy"),
        "",
    ])
    return "\n".join(sections).strip() + "\n"


def render_agent_roles(profile: StartupProfile) -> str:
    lines = [
        "# Agent Roles",
        "",
        "These are the current lanes for this PromptClaw.",
        "",
    ]
    for agent_name in profile.agent_roster:
        strengths = profile.agent_strengths.get(agent_name) or DEFAULT_AGENT_STRENGTHS.get(agent_name, "general problem-solving")
        capabilities = ", ".join(infer_capabilities(strengths, agent_name))
        lines.extend([
            f"## {agent_name}",
            f"- Best at: {strengths}",
            f"- Capability tags: {capabilities}",
            f"- Suggested lead lane: {lead_lane_text(capabilities)}",
            f"- Verification fit: {verification_fit_text(capabilities)}",
            "",
        ])
    return "\n".join(lines).strip() + "\n"


def render_routing_rules(profile: StartupProfile) -> str:
    lines = [
        "# Routing Rules",
        "",
        "## Core routing posture",
        "- Route by content need, not fixed sequence.",
        f"- Prioritize these task families first: {profile.answer('task_families_priority') or profile.answer('task_families')}",
        f"- Typical output shape: {profile.answer('success_outputs')}",
        f"- Verification style: {profile.answer('verification_policy')}",
        "",
        "## Agent lanes",
    ]
    for agent_name in profile.agent_roster:
        strengths = profile.agent_strengths.get(agent_name) or DEFAULT_AGENT_STRENGTHS.get(agent_name, "general problem-solving")
        lines.append(f"- {agent_name}: {strengths}")
    lines.extend([
        "",
        "## Lead selection",
        profile.answer("routing_examples"),
    ])
    if profile.answer("routing_examples_detail"):
        lines.extend(["", "## Concrete routing example", profile.answer("routing_examples_detail")])
    lines.extend([
        "",
        "## Ambiguity handling",
        profile.answer("ambiguity"),
    ])
    if profile.answer("ambiguity_focus"):
        lines.extend(["", "## First clarification question should target", profile.answer("ambiguity_focus")])
    lines.extend([
        "",
        "## Autonomy",
        profile.answer("autonomy"),
    ])
    if profile.answer("permission_boundaries"):
        lines.extend(["", "## Approval gates", sentence_or_list(profile.answer("permission_boundaries"))])
    lines.extend([
        "",
        "## Red lines",
        sentence_or_list(profile.answer("hard_boundaries") or profile.answer("boundaries")),
        "",
    ])
    return "\n".join(lines).strip() + "\n"


def render_agent_instruction(profile: StartupProfile, agent_name: str, strengths: str) -> str:
    boundaries = profile.answer("hard_boundaries") or profile.answer("boundaries")
    lines = [
        f"# {agent_name.title()} Lane",
        "",
        f"You are {agent_name} inside {profile.project_name}. 🛠️",
        "",
        "## Primary strengths",
        sentence_or_list(strengths),
        "",
        "## Project style",
        "Produce markdown that is explicit, structured, and action-oriented.",
        "Respect the orchestrator's handoff brief and the current task type.",
        "",
        "## Autonomy posture",
        profile.answer("autonomy"),
        "",
        "## When to pause",
        profile.answer("ambiguity"),
        "",
        "## Hard boundaries",
        sentence_or_list(boundaries),
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def render_startup_profile(profile: StartupProfile) -> str:
    lines = [
        "# Startup Profile",
        "",
        "```text",
        r" /\_/\\",
        r"( o.o )  PromptClaw startup snapshot 🦀✨",
        r" > ^ <",
        "```",
        "",
        f"- Project: {profile.project_name}",
        f"- Agents: {', '.join(profile.agent_roster)}",
        f"- Mission: {profile.answer('project_pitch')}",
        "",
        "## Task families",
        sentence_or_list(profile.answer("task_families_priority") or profile.answer("task_families")),
        "",
        "## Typical outputs",
        sentence_or_list(profile.answer("success_outputs")),
        "",
        "## Verification",
        profile.answer("verification_policy"),
        "",
        "## Autonomy",
        profile.answer("autonomy"),
        "",
        "## Ambiguity policy",
        profile.answer("ambiguity"),
        "",
        "## Boundaries",
        sentence_or_list(profile.answer("hard_boundaries") or profile.answer("boundaries")),
        "",
        "## Agent roster",
    ]
    for agent_name in profile.agent_roster:
        lines.extend([
            f"### {agent_name}",
            profile.agent_strengths.get(agent_name) or DEFAULT_AGENT_STRENGTHS.get(agent_name, "general problem-solving"),
            "",
        ])
    return "\n".join(lines).strip() + "\n"


def render_transcript(profile: StartupProfile, title: str = "# Startup Transcript") -> str:
    lines = [title, ""]
    for idx, entry in enumerate(profile.transcript, start=1):
        marker = "Follow-up" if entry.is_follow_up else "Question"
        lines.extend([
            f"## {marker} {idx}",
            f"**Prompt:** {entry.prompt}",
            "",
            f"**Answer:** {entry.answer}",
            "",
        ])
    return "\n".join(lines).strip() + "\n"


def lead_lane_text(capabilities_csv: str) -> str:
    lowered = capabilities_csv.lower()
    if "coding" in lowered or "implementation" in lowered:
        return "code-heavy execution and implementation"
    if "architecture" in lowered or "specification" in lowered:
        return "architecture, planning, and design"
    if "research" in lowered or "docs" in lowered:
        return "research, docs, and synthesis"
    return "general problem-solving"


def verification_fit_text(capabilities_csv: str) -> str:
    lowered = capabilities_csv.lower()
    if "verification" in lowered or "analysis" in lowered:
        return "strong verifier candidate"
    if "testing" in lowered:
        return "good for execution checks and test validation"
    return "can verify lightweight work when needed"
