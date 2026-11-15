# Language policy and coverage

English is the primary language for PrintLab's public documentation and maintained agent instructions. The default `README.md`, repository description and new release notes are in English. [简体中文](../README.zh-CN.md) remains available as a secondary introduction. When both video platforms are available, YouTube is the primary link and Bilibili is the alternative; the current walkthrough has Chinese audio.

## What is in English

The README, contribution and issue-reporting entry points, `AGENTS.md`, the repository Agent Skill, installation and onboarding guides, role prompts, upgrade guide and core design workflow use English. These give contributors and agents a shared starting point. Agents should communicate with users in the user's preferred language and retain the user's original statements as evidence.

There is no project-specific comparison showing that translating instructions alone improves an agent's reasoning. The reason for this choice is accessible onboarding and consistent maintenance for an international audience.

## What remains in Chinese

The workbench UI, some generated messages and role prompts, detailed device/integration guides, historical verification records and project templates are not fully translated. Agents can read these references and explain them in the user's language. This release does not claim a fully English or localized application.

Chinese Bambu Studio button names, accessibility/OCR match strings and fixtures represent the actual supported Chinese UI. Translating those literals would change device-control behavior. User projects, preferences, quotations, filenames and historical records also retain their original language. Unicode test cases continue to test non-English text and paths.

## How to continue the migration

- Write new or materially revised canonical technical documentation, identifiers and explanatory code comments in English. Keep the English and Chinese README aligned on capabilities, installation and limits.
- Translate detailed maintained references as they are revised, preserving commands, paths, schema keys, units, permissions and verification boundaries. Keep old public links working.
- Treat workbench localization as a separate feature: introduce localized resources, preserve stable machine-readable values, provide a language choice and verify the actual screens and workflows. Do not globally replace Chinese strings.
- Never rewrite a user's existing workspace or historical evidence merely to change its language.
