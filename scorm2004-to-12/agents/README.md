# Agent Compatibility

This skill is packaged as a plain directory with `SKILL.md`, `scripts/`, `references/`, and optional `agents/` metadata. The core workflow is not tied to one runtime.

## Supported Usage

- Codex can load `SKILL.md` directly as a local skill.
- Hermes/OpenClaw-style agents can read the same `SKILL.md` and execute the Python script from the repository root.
- Generic agents can use the README and run `python3 scorm2004-to-12/scripts/scorm_asset_doctor.py ...`.
- `hermes.yaml` and `openclaw.yaml` provide lightweight routing metadata only; they do not replace `SKILL.md`.

## Compatibility Boundary

The repository does not claim a separate Hermes or OpenClaw plugin runtime. It provides a portable AgentSkills-style folder plus plain CLI scripts. If an agent requires a platform-specific registry file, keep that file as metadata only and route the actual work through `SKILL.md` and `scripts/scorm_asset_doctor.py`.

## Command Root

Public documentation uses repo-relative paths:

```bash
python3 scorm2004-to-12/scripts/scorm_asset_doctor.py inspect course.zip
```

If the skill is installed into an agent-specific skills directory, replace `scorm2004-to-12/` with that installed directory path.

## Runtime Debugging Contract

For custom vendor packages, agents should load `references/runtime-debugging-notes.md` before changing course-layer JavaScript. The default acceptance gates are launch, bookmark/resume, completion/pass, score when applicable, and learning-time reporting.

For learning-time fixes, agents should check whether multiple exit events call the same save path (`pagehide`, `beforeunload`, `unload`, or manual termination). If so, use a per-launch guard such as `sessionTimeSaved` so the same `cmi.core.session_time` value is not submitted more than once. Keep this as inspected runtime code, not an automatic script patch.

When `cmi.core.exit` behavior is in question, prefer conditional final-state behavior if LMS testing proves both variants work:

- unfinished attempt: `suspend`
- final status (`completed`, `passed`, or `failed`): empty exit value

Use always-`suspend` only as a documented LMS-specific fallback.
