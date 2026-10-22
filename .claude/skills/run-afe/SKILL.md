---
name: run-afe
description: Run, start, screenshot and drive the Afe website and API (SvelteKit + FastAPI) with demo data. Use when asked to run Afe, start the landing page, take a screenshot of a page, check the landing page animations, test the hero search, run the accessibility audit, or confirm a frontend/backend change works in the real app.
---

Afe is a FastAPI API (`backend/`) and a SvelteKit website (`frontend/`) that calls it. Agents drive it with
`.claude/skills/run-afe/driver.sh`. It seeds a throwaway demo database, starts both servers, and runs the browser
through `playwright-cli`: screenshots, JavaScript checks in the page, clicks, and emulation (phone width, reduced motion).
All paths are relative to the repo root.

Verified on Windows 10 in Git Bash (Claude Code's Bash tool), with Python 3.12, Node 24, and Microsoft Edge
already installed. The Linux branches in the driver (`lsof`, `.venv/bin/python`) have not been run.

## Prerequisites

`backend/.venv` (with `requirements-dev.txt`) and `frontend/node_modules` must exist. This skill was verified on a
machine where they already did; the install commands are in `backend/README.md` and `frontend/README.md`.
The driver installs `@playwright/cli` itself, once, into its state folder. No global install is needed.

## Run (agent path)

```bash
bash .claude/skills/run-afe/driver.sh up          # seeded API on :8000 + website on :5173 (~35 s from nothing)
bash .claude/skills/run-afe/driver.sh landing     # drive the landing page: PASS/FAIL lines + screenshots (~2 min)
bash .claude/skills/run-afe/driver.sh shot "/homes?area=east-legon" 390 844   # any page, any size
bash .claude/skills/run-afe/driver.sh pages       # sweep every page the landing page links to (~3.5 min)
bash .claude/skills/run-afe/driver.sh a11y        # accessibility audit of every page, every role, light and dark (~3 min)
bash .claude/skills/run-afe/driver.sh down        # close the browser, stop both servers
```

| command | what it does |
|---|---|
| `up` | Creates `demo.db` (migrations + `seed-demo`) if missing, then starts the API and the website dev server. If a server is already listening, it says so and leaves it alone. |
| `landing` | Checks that every photo loads, the hero ticket and check animations (frozen at 400 ms, then settled), the scam check answering in place and clearing when you type again, phone width (390 px, no overflow) and the phone menu (opens, Escape closes), reduced motion (no entrance animations), and the hero search (lands on `/homes` with the same filters and one view transition that finishes). Then the section links: How it works, For landlords and Report a scam scroll to their section with no `#` in a link or the address bar, the skip link moves focus without changing the address, and an old `/#how` link lands on its section and drops the `#`. Exits 1 if any check fails. |
| `pages` | Visits every page the landing page links to, at 1280 and 390 px. Checks status 200, that no image fails to load (lazy images are forced to load), no horizontal overflow, and exactly one `<h1>`. Then reports console errors logged during the sweep, and page styles that reuse a global class name. Screenshots go to `shots/pages/`. |
| `a11y` | Runs `a11y.cjs`: signs in as each demo role (MFA codes come from the demo database) and visits its pages plus one of each kind of detail page, in light and dark mode. As the verifier it first checks in to an open assignment at the home's pin (emulated GPS), so the field visit page is covered; that starts a visit in the demo database. Checks names and labels, landmarks and headings, contrast against the real background, a visible focus change for the first 30 Tab stops, and no sideways scroll at 320 px. Prints the findings by rule, writes `a11y.json`, and exits 1 if anything is found. What it covers and the manual screen-reader checks it can't do: `docs/accessibility.md`. |
| `shot <path> [w] [h]` | Opens the page, finishes clock-driven animations, and saves a screenshot. |
| `down` | Stops whatever listens on :5173 and :8000 (Windows: `taskkill /T`). |

State lives in `$AFE_RUN_DIR` (default `<temp>/afe-run`; in Git Bash `/tmp/afe-run` = `C:/Users/<you>/AppData/Local/Temp/afe-run`):
`demo.db`, `media/`, `api.log`, `web.log`, `shots/*.png`. To start again with fresh demo data:

```bash
bash .claude/skills/run-afe/driver.sh down; rm -rf "/tmp/afe-run"
```

Look at the screenshots in `shots/`, not just the PASS lines: a class-name clash (see Gotchas) passes every check and still looks broken.

To drive something the driver doesn't cover, use the same tools by hand. `-s=afe` reuses the driver's browser session:

```bash
/tmp/afe-run/pw/node_modules/.bin/playwright-cli -s=afe eval "() => location.href"
```

## Run (human path)

`driver.sh up` is also the human path: open http://localhost:5173 in a browser, and `driver.sh down` when finished.
Demo sign-ins are in the root README.

## Test

```bash
cd backend && .venv/Scripts/python -m pytest -p no:warnings     # 246 passed (~1.5 min)
cd frontend && npx svelte-check --threshold error && npx vitest run && npm run build   # 0 errors, 9 tests
```

## Gotchas

- **The site's global stylesheet already uses short class names.** `frontend/src/app.css` holds the whole UI system
  (from the Claude Design project): `.card` is the listing ticket (it lifts on hover), `.result` is an answer card,
  `.facts` is the mono-label strip, `.doc` underlines links, `.steps` is the numbered stepper, `.count`, `.check`,
  `.thumb`, `.panel-head`, `.line` and more are taken. A Svelte component's scoped styles don't stop those global
  rules applying, so reusing a name mixes both: a review card lifted on hover, a result card stacked its photo
  above its text, links in a document list turned underlined. Check a page's classes against `app.css` before styling:
  ```bash
  cd frontend; for c in $(grep -oE 'class="[^"{]+"' src/routes/+page.svelte | sed 's/class="//;s/"//' | tr ' ' '\n' | sort -u); do grep -qE "(^|[ ,}])\.$c([ ,:.{\[]|$)" src/app.css && echo "CLASH: .$c"; done
  ```
  Shared on purpose: `.btn` (and `.accent`, `.secondary`, `.quiet`, `.ghost`, `.danger`, `.md`, `.sm`, `.big`), `.chip`,
  `.chips`, `.seg`, `.tabs`, `.pills`, `.tag`, `.pill`, `.badge`, `.notice`, `.box`, `.lines`, `.tear`, `.kicker`,
  `.label-mono`, `.grid`, `.row`, `.stack`, `.small`, `.muted`, `.sr`, `.vt-search`. `pages` fails if a page's own
  `<style>` restyles one of them; tweak spacing with a wrapper class or an inline style instead.
- **Headless Edge (`msedge --headless --screenshot`) misleads:** it captures the first frame, so entrance animations look like missing content. It won't go narrower than its minimum window width, so a 390 px phone screenshot is a wider layout cropped. And `--force-prefers-reduced-motion` with a reused `--user-data-dir` hung until it was killed. Use the driver (`playwright-cli resize` / `set-reduced-motion`).
- **Scroll-driven sections are invisible until scrolled to.** `.reveal` uses `animation-timeline: view()`, so in a full-page screenshot the sections below the fold are at opacity 0. Scroll to them first (the driver does), or emulate reduced motion.
- **Hot reload doubles the view transition.** After editing `+layout.svelte`, the dev server keeps the old `onNavigate` alongside the new one, so `startViewTransition` runs twice and the second skips the first. Load the page fresh before judging transitions; the driver does a fresh `goto`.
- **`playwright-cli` element refs gain a frame prefix after navigation** (`e31` becomes `f3e31`). Match `ref=[a-z0-9]+`, as the driver's `ref()` does.
- **`npx -y @playwright/cli@latest` costs about 10 s per call** (a landing run took 6 minutes). The driver installs it once into `$AFE_RUN_DIR/pw`.
- **The API doesn't hot-reload; the website does.** After a backend change, run `down` then `up`.
- **Native Windows Python can't read Git Bash paths** like `/tmp/...` in `sqlite:///` URLs. The driver converts them with `cygpath -m`.
- **A dev-only setting in `vite.config.ts` gets baked out.** SvelteKit writes the security policy into
  `.svelte-kit/generated/server/internal.js` whenever `svelte-kit sync` (inside `svelte-check`) or `npm run build`
  runs, and the running dev server serves whatever that file says. A `command === 'serve'` switch in the config
  worked until the next check or build, then every local photo was blocked (`/homes` and the landing page's
  "Just verified" cards). The local API's address is now added per request in `src/hooks.server.ts` when `dev` is
  true. Production (`node build`) sends `img-src 'self' data: blob: https:` only.
- **Local photos are cross-origin:** the website is `localhost:5173` and photos come from `127.0.0.1:8000/media`. They show only because `/media` sends `Cross-Origin-Resource-Policy: cross-origin` and the hook allows that address. If photos show as alt text, check the header:
  ```bash
  curl -sI "$(curl -s http://localhost:5173/ | grep -oE 'http://127.0.0.1:8000/media/[^"]+' | head -1)" | grep -i cross-origin
  ```

## Troubleshooting

- **Background `uvicorn` exits with code 3, or `vite --strictPort` exits with code 1:** the port is already taken, usually by a server from an earlier session that is still serving (maybe on a different database). Run `driver.sh down`, then `up`.
- **`svelte-check`: "Type 'string' is not assignable to type 'Source'" in `vite.config.ts`:** a security-policy source built as a plain string array. Add `as const` to the array.
- **Photos show as alt text; the console says "Loading the image 'http://127.0.0.1:8000/media/…' violates the following Content Security Policy directive":** the dev allowance is missing from the policy header. Check that `src/hooks.server.ts` still calls `allowLocalApi` (see Gotchas); don't put it back in `vite.config.ts`.
- **Counts, steps or panels look wrong but every check passes:** a global class clash. Run the check under Gotchas.
