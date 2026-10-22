# Project instructions

This is source development for a portable career skill, not a personal skill installation or hosted service. Read README.md and the relevant phase reference before changing behavior.

- Author all distributed source, comments, documentation, examples, CLI messages and tests in English. Runtime conversations and intake use the user's language; output-document/interview language is chosen separately for the role.
- Use synthetic people/companies and reserved example domains only. Never read or copy real applicant resumes, correspondence, salary, identity, private job-search material or secrets into this project. Keep candidate workspaces outside this checkout.
- Keep the core skill self-contained inside skills/career-agent, with phase references. Optional helpers remain standard-library-only. Career data/material/search helpers have no network/sending behavior; the explicitly approved release updater may read only fixed public GitHub release metadata/assets, without uploading candidate data or running research.
- Do not add an operator backend, hosted database, telemetry, author API service, required remote MCP, account system or mandatory paid service. Do not imply every host has files, browsing, tools, installation or memory.
- Never invent achievements, metrics, qualifications, company facts or relationships. Keep hypotheses, confirmed facts, private assessments and public claims distinct. Do not belittle applicants or self-reject over nonessential wish-list items.
- Preserve exact opportunity identity and provenance. Prepared is not sent; receipt is not progress; bounce is not rejection; unknown coverage is not silence; uncertain sends block blind retries. Employer-specific consents are never automatically reusable.
- Research requires an explicit start choice. Pause means stop new research immediately across authorized workers. The current project has no automated submission or messaging path.
- Validate changes with `python3 -m unittest discover -s tests -v` and exercise affected CLI commands. Add tests only for meaningful changed invariants. Keep fixture records fictional.
- Do not push, upload code, create remote commits, publish a plugin, install personal skills, deploy or start a real job search without explicit user authorization. An empty public repository does not authorize any upload.
