# Private materials and attempt organization

Use [the interaction contract](interaction.md) for every intake choice, factual clarification or preference: native questionnaires are required when applicable in the current host/mode; keep conclusions in chat and avoid duplicate prose questions.
The agent manages files when authorized and capable; the user chooses a friendly workspace and works through chat. Keep all private files outside the distributed source/installed skill. Without filesystem/symlink support, use explicit file/text references and export/import; do not pretend links or files were created.

Keep originals or authorized immutable copies in Originals. Keep general reusable resume/material versions once in Materials, identified by stable version ID and content hash. A tailored resume is a distinct immutable version. Do not create another PDF for every application using the same resume; defer conversion until the selected form or reviewed deliverable needs that format.

Use this hierarchy within Applications: readable company name plus stable company ID → readable vacancy name plus stable opportunity ID → Attempts → readable attempt label plus stable attempt ID. Exact stable identities, not company/title/date strings, prevent collisions. A later application gets a new attempt; do not overwrite the previous timeline. Vacancy-level Research can hold shared dossier/interview context. Letters, Forms, Evidence and Correspondence stay under the relevant attempt.

Each attempt pins a material version/hash. Use a relative symlink to the central immutable file when supported, plus a readable portable reference record. If the filesystem denies symlinks, retain the relative-path/version/hash reference and explain it; never silently create another binary copy. Do not point to “latest”. Changing a resume later cannot change what a prior sent attempt used. Moving the whole workspace should preserve relative links/references; verify them before resuming.

Source helpers, when available, use safe readable slugs plus stable-ID digests and directory identity markers. Reject traversal, conflicting directories, escaping symlinks and changed hashes. File work can leave an unregistered immutable file or partially prepared folder after failure; preserve it, validate against state and reconcile rather than deleting user files or pretending it committed.

For export/upload preparation, resolve only the user-selected material slots for the exact attempt, verify hashes and disclosure, and package only those files plus a minimal manifest. Do not recursively export the library/workspace, follow escaping links, include private assessments or send the package. Recheck current credential wording/disclosure when reusing old materials. No file deduplication or deletion of the user's existing originals is implicit.

The material commands own file integrity, references and disclosure, not whole-packet readiness. Normal application work uses [packets](packets.md#prepare-refresh-and-deliver); a successful register/prepare-attempt/verify-attempt is not evidence that all content was adapted or semantically reviewed.
