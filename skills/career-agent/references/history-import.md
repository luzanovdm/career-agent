# Existing application history and mail reconciliation

Use [the interaction contract](interaction.md) for every intake choice, factual clarification or preference: native questionnaires are required when applicable in the current host/mode; keep conclusions in chat and avoid duplicate prose questions.
Offer this during setup and tracking, without requiring a complete profile. Accept a plain list, table, CSV or supplied file. With no file reader, ask for readable pasted rows; the ordinary user never writes JSON or runs a script. Preserve source, employer, exact role/project if known, URL, approximate/unknown date, channel and user-reported status. Keep missing values unknown; do not fabricate requisition IDs, dates, delivery proof or outcomes.

## Preview before applying

Show a compact mapping: original entry/source, normalized employer/role/URL, proposed exact opportunity ID or unresolved identity, date precision, status and what will change. Normalize known tracking query parameters while preserving job-ID parameters and potentially meaningful URL fragments. Exact-role IDs and URLs may confirm identity; similar company/title strings are only candidate matches for review. A company-level conversation remains unscoped and cannot mark all of its roles applied.

After user review, import append-only observations with stable fingerprints. Repeating the same import adds no duplicate observations. Link an unresolved observation to an exact role only through a reviewed mapping; retain its stable ID and original evidence. Source/date/status differences can represent chronology or a conflict: preserve them and explain unresolved differences. Do not replace stronger delivery evidence or later responses with a sparse historic list. Keep user-reported history distinct from provider-observed records and confirmed action events.

Before preparing any repeat application, check exact-role history. Prior sent, uncertain or bounced entries require reconciliation; an uncertain action must not be retried blindly. A receipt, follow-up, referral contact or email thread is not automatically a separate application. Imported observations do not change research authorization or pause, authorize sending, or inflate confirmed-sent denominators. Keep separate counts of historically reported applications, unmapped entries and confirmed-sent exact roles.

## Optional authorized mail connector

If Gmail or a compatible connector already exists and its read capability is authorized, offer a scoped read-only reconciliation of Sent and replies (date range, roles/companies and relevant folders). If absent or reconnect is required, explain the optional connection and continue with list/file import. Never make connecting Gmail mandatory or ask for credentials. Use host-neutral available tools; no connector implementation is bundled here.

Retain minimal provenance: provider message/thread IDs, source locator, event date/precision, exact-role mapping and classification. Do not retain full email bodies by default, mark messages read, change labels, send email or accept agreements. Distinguish initial application, follow-up, receipt, rejection and bounce from semantic evidence, not thread count. An observed Sent item establishes an observed send, not guaranteed employer delivery. Missing mail or incomplete folder coverage is unknown, not proof of no application or silence. Match replies to the exact role and action where evidence permits; preserve ambiguous threads for review.

The optional local helper previews/imports normalized observations and records reviewed mappings. The agent prepares those records from conversational/file/connector input. It does not parse arbitrary documents semantically or access Gmail itself. Exact dated evidence can be reconciled into separate action/response records after review; never invent a precise timestamp for approximate history. Show the updated readable view, private storage location, unresolved matches and coverage limits.
