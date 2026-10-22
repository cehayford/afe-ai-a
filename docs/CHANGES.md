## SURVEY-001 (20 September 2026) — validation survey
- `afe_survey_form.gs` — Apps Script that builds the Google Form (branching: tenant / landlord / agent, 38 questions total).
- `AFE_SURVEY_GUIDE.md` — Forms settings, distribution, sample sizes, and which answer tests which assumption in Statement 12.3.

# Afe document set — change log

## SURVEY-001 (21 September 2026) — validation surveys
- **Afe_Validation_Surveys.docx** (new) — question banks for two Google Forms (renters and buyers; landlords and agents), how each question maps to an assumption in Statement §12.3 or a model input, feature-question design, distribution plan for Ghana, and how to read results back into the model.
- **afe_survey_forms.gs** (new) — Apps Script that builds both forms in Google Drive automatically.

Run before the private beta. Results settle decisions D6, D7, D13, D15 and D22.

## MODEL-001 (20 September 2026) — business model and viability
- **Statement v3.3** — new Section 12 (revenue streams, unit economics, assumptions to test in beta, targets). Team/Risks/Decisions renumbered to 13/14/15. New decisions D22–D23, amendments A42–A44. Replaces v3.2.
- **Afe_Unit_Economics_Model.xlsx** (new) — Inputs, Unit economics and a 24-month Projection with break-even and runway. Every input is a placeholder awaiting the viability and monetization analysis; only the 3.5% fee and the USD 50 subscription come from the existing documents.
- **page-structure.md** — pricing tiers flagged: fee rate pending D6, subscription price pending D22.
- **architecture.md, architecture-country.md, generate_architecture_doc.py** — commission line flagged, with a note that the gateway fee applies to the full escrowed amount.
- **ROADMAP.md** — revenue projection table marked withdrawn.
- **README.md, SKILL.md** — monetization lines.

**Conflict found:** the platform fee is 3.5% in architecture.md and the pricing page but 2.5% in RFC-002. Working figure is 3.5% until D6 settles it.

## STORAGE-001 (later on 15 September 2026) — file storage and backup
Added to the documents:
- **Statement v3.3** — new Sections 8.6 (file storage: five S3 buckets by sensitivity, upload and quarantine pipeline, lifecycle) and 8.7 (backup, retention, restore drills). Also new metrics, risks, decisions D18–D21 and amendments A36–A41. Replaces v3.1.
- **architecture.md, architecture-country.md, generate_architecture_doc.py** — new "Storage & Backup" section under Deployment Architecture; KYC bucket uses a customer-managed KMS key; primary region flagged as pending decision D2.
- **database-schema.md, init_database.py** — new `stored_files` table; `property_images` stores S3 keys (`bucket`, `storage_key`, `original_key`) instead of a URL; EXIF noted as read-then-stripped.
- **docker-compose.yml** — MinIO plus a bucket-creation container for local S3; S3 environment variables for the API and Celery worker.
- **SKILL.md, README.md, QUICKSTART.md** — storage and backup lines; local MinIO setup.

**Bug fixed:** `init_database.py` ended with a stray ``` ``` ``` line left over from a markdown export, so the file could not run. Removed.

## STACK-001 (15 September 2026) — Python + Rust backend, native Kotlin + Swift mobile

### Documents
- `Afe_Project_Statement_v3.3.docx` — consolidated project statement (v3.0 consolidated the set, v3.1 added the stack change, v3.2 adds storage and backup).
- `Afe_Stack_Amendment_STACK-001.docx` — Rust boundaries and workspace, Android/iOS architecture, replacement component prompts (CL-062 mobile, CL-080–082, CL-090–094), testing, CI/CD, change register.

### Edited directly
| File | Change |
|---|---|
| README.md | Stack line, mobile section, admin section, next steps |
| SKILL.md | Backend (Rust module), frontend (Kotlin/Swift, SvelteKit admin), file tree |
| PACKAGE-INDEX.md | Stack note; build phases |
| QUICKSTART.md | Flutter setup replaced with Android (Gradle), iOS (Xcode) and Rust (maturin) setup |
| ROADMAP.md | Native apps, team roles; marked superseded by Statement §11 |
| framework-comparison.md | Stack diagram; Rust replaces the "move to Go" plan; new addendum |
| architecture.md, architecture-country.md, generate_architecture_doc.py | Mobile and Rust lines in stack and diagram |
| fraud-detection.md | Notes: Rust is production, Python is the reference implementation |
| page-structure.md | Note: mobile screens built natively |
| requirements.txt | maturin added; afe_native note |
| Dockerfile | Multi-stage build with Rust wheel; Python 3.12; stdlib health check |
| HomeConnect_API_InfraPrompt_extracted.txt | Duplicate notice |

### Amendment banner added (replacement text lives in STACK-001)
HomeConnect_Africa_Engineering_Docs_v2.docx · HomeConnect_ComponentLibrary.docx · HomeConnect_QuickFixes.docx · HomeConnect_Dashboard_Prompts.docx · HomeConnect_OtherPages_Prompts.docx · HomeConnect_Africa_Implementation_Plan.docx · HomeConnect_API_InfraPrompt.docx

### Unchanged (no stack impact)
api-design.md · kubernetes.yaml · implementation_plan.md · naming-options.md · Gray CSM UI Design System#2.md

## Still open
Decisions D1–D21 in Statement §14, including D1 (rename House Agent / HomeConnect / Hca to Afe in code and file names), D2 (hosting region), D18 (retention periods, with counsel).
