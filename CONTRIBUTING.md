# Contributing and reporting problems

Read the README's supported environment and `docs/VERIFICATION.md`. Identify the release tag or commit you are using. Use the installation or usage issue form and remove access codes, API keys, serial numbers, private network addresses and private information in your models.

Use English for maintained technical documentation and new explanatory comments; users may report problems in their preferred language. Keep the Chinese README consistent with the default English README. See [language coverage](docs/LANGUAGE.md) before translating UI or device-control strings.

Make changes on a separate branch. Run setup, onboarding verification, Python and Node tests, and browser verification. Changes to printing routes must preserve file fingerprints, task-specific approval, current device checks, single-send reservations and reconciliation of unknown outcomes. Synthetic-device tests do not prove that a real printer works.

New printer adapters need evidence for model-specific profiles, file inspection, material/feeding mappings and verification. Adding a model name alone does not establish support. Do not commit third-party source, weights, real user models, personal device settings or credentials; install third-party tools independently from their original projects.

Original contributions retain `LICENSE.md` and `NOTICE.txt`. Dependency changes must include lockfiles and cross-platform verification. Release notes must distinguish verified behavior from remaining work.
