# Project Instructions for Codex

## 1. Project Source of Truth

- `goal.md` defines what the project must achieve and every required feature.
- `architecture.md` defines the architecture, technologies, components, integrations, and technical constraints.
- For full-project implementation tasks, read both documents completely before coding.
- Treat every explicitly required feature, workflow, integration, and acceptance criterion in both documents as mandatory.
- Do not silently omit, simplify away, or postpone documented requirements.
- If requirements conflict or are materially ambiguous, explain the conflict and ask for clarification rather than guessing.
- Preserve existing working functionality unless a requirement explicitly demands changing it.

## 2. Karpathy Principle: Think Before Coding

- Understand the task, relevant code, dependencies, and constraints before making changes.
- State important assumptions and identify genuine uncertainties.
- Consider simpler solutions before introducing complexity.
- Do not invent requirements or silently change the intended architecture.
- Ask questions only when ambiguity materially affects correctness; otherwise proceed with reasonable, stated assumptions.

## 3. Karpathy Principle: Simplicity First

- Write the simplest maintainable implementation that fully satisfies the requirements.
- Avoid unnecessary abstractions, premature optimization, duplicate logic, and speculative features.
- Reuse existing project patterns, utilities, and components where appropriate.
- Prefer clear, readable code over clever or complicated solutions.
- Simplicity means simpler implementation, never reduced functionality.
- Do not remove a required feature merely to make implementation easier.

## 4. Karpathy Principle: Surgical Changes

- Modify only the files and code necessary to accomplish the task.
- Preserve unrelated functionality, APIs, styling, comments, and existing conventions.
- Avoid unrelated refactoring and unnecessary dependency changes.
- Remove unused code or imports introduced by your own changes.
- Do not rewrite working components when a focused modification is sufficient.
- Make larger structural changes only when necessary to satisfy documented architecture.

## 5. Karpathy Principle: Goal-Driven Execution

- Define concrete, verifiable success criteria before implementation.
- For full-project tasks, compare the existing implementation against every requirement in `goal.md` and `architecture.md`.
- Create a feature checklist identifying completed, incomplete, and missing functionality.
- Work through missing requirements systematically, verifying each completed feature.
- Implement real, end-to-end functionality, including relevant frontend, backend, data persistence, APIs, validation, and integrations.
- Do not substitute placeholders, fake data, no-op handlers, or TODO comments for required production behavior unless explicitly requested.
- Test functionality and check relevant integration points.
- Continue through the requirements rather than stopping after an initial scaffold or partial implementation.

## 6. Implementation and Verification

- Inspect the existing codebase before adding or replacing anything.
- Follow the documented architecture and established coding conventions.
- Keep existing features working while implementing missing ones.
- Run relevant tests, type checks, linting, and build commands when available.
- Fix failures caused by your changes.
- Verify critical workflows end-to-end where practical.
- Never claim that a feature works without appropriate verification.
- If tests cannot run or a requirement is blocked, clearly report why.

## 7. Definition of Done

For full-project implementation tasks, completion requires:

- All requirements from `goal.md` and `architecture.md` are accounted for.
- All required features and workflows are implemented, not merely scaffolded.
- Required components and integrations work together.
- Relevant tests and build checks pass, or limitations are explicitly documented.
- No known requirement is silently left incomplete.

At the end, report:

1. Features implemented.
2. Verification performed and results.
3. Remaining incomplete requirements or blockers, if any.
4. Important technical decisions or assumptions.

Never report the project as fully complete when required functionality remains missing.

## 8. Priority Rule

Follow all four Karpathy principles while delivering the full documented scope.

When simplicity and completeness appear to conflict, preserve all required functionality and simplify the implementation instead.

When a task is narrowly scoped, make only the requested changes. When explicitly asked to build or complete the project, implement and verify all requirements from `goal.md` and `architecture.md`.
