# v0.4.1 Windows feedback fixes

Reports: [#4](https://github.com/AFangTeam/PrintLab/issues/4) and [#5](https://github.com/AFangTeam/PrintLab/issues/5), submitted by squallda against v0.3.0. Both affected code paths remained in v0.4.0.

- Private-directory initialization now replaces only the DACL (access rules). The previous one-argument `SetSecurityDescriptorSddlForm` also marked the audit section for persistence, requiring `SeSecurityPrivilege`. Ordinary users should not need administrator rights to initialize an owned workspace. The replacement still removes extra explicit ACEs and allows only the current user and SYSTEM, with inheritance disabled. It does not reset to a broader inherited ACL or swallow permission errors.
- Windows service sockets now use `SO_EXCLUSIVEADDRUSE` before binding. A second workspace cannot silently listen on the same address/port. Startup exits with an occupied-address diagnostic; `--port` remains available for an intentionally separate service. macOS keeps `SO_REUSEADDR`.
- The two reported tests now explicitly read UTF-8 workspace documents, independently of the Windows default text encoding.

Regression coverage includes actual cross-process socket contention, CLI refusal, restart after close, clean and extra-ACE directories, repeat initialization, and preservation of an existing private file. On Windows a disposable subprocess permanently removes `SeSecurityPrivilege`, demonstrates the old call failing, and runs the real initializer twice with the corrected implementation. CI also runs the focused tests with `PYTHONUTF8=0`.

The restricted-privilege test reproduces the reported privilege constraint; it is not a complete Windows 11 standard-account desktop acceptance test. No printer operation is part of this fix.

References: [Microsoft socket exclusivity](https://learn.microsoft.com/en-us/windows/win32/winsock/so-exclusiveaddruse), [SDDL section selection](https://learn.microsoft.com/en-us/dotnet/api/system.security.accesscontrol.objectsecurity.setsecuritydescriptorsddlform).
