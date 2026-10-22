#!/usr/bin/env bash
# Drive Afe (FastAPI backend + SvelteKit website) for agents. See SKILL.md next to this file.
#
#   driver.sh up                      seeded demo API on :8000 + website dev server on :5173
#   driver.sh landing                 drive the landing page: animations, scroll, phone, reduced motion,
#                                     hero search -> /homes view transition; screenshots + PASS/FAIL lines
#   driver.sh shot <path> [w] [h]     screenshot any page (animations finished), e.g. shot /homes 390 844
#   driver.sh pages                   sweep every page the landing page links to, at 1280 and 390 px: status,
#                                     broken images, overflow, one <h1>, console errors, global class clashes
#   driver.sh a11y                    accessibility audit: every page of every role (signed in), light and dark;
#                                     names, labels, contrast, keyboard focus, 320 px reflow; exits 1 on findings
#   driver.sh down                    close the browser and stop both servers
#
# State (demo database, media, logs, screenshots) lives in $AFE_RUN_DIR (default: <temp>/afe-run).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RUN="${AFE_RUN_DIR:-${TMPDIR:-/tmp}/afe-run}"
mkdir -p "$RUN/shots"
API_PORT=8000
WEB_PORT=5173
API="http://127.0.0.1:$API_PORT"
WEB="http://localhost:$WEB_PORT"
PWBIN="$RUN/pw/node_modules/.bin/playwright-cli"

# Native Windows programs (python, the browser) can't see Git Bash paths like /tmp: hand them C:/... paths.
win() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
py() {
	if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then printf '%s' "$ROOT/backend/.venv/Scripts/python.exe"
	else printf '%s' "$ROOT/backend/.venv/bin/python"; fi
}
up_already() { curl -sf -o /dev/null "$1"; }
wait_for() { curl -sf -o /dev/null --retry 90 --retry-delay 1 --retry-connrefused --retry-all-errors "$1" || { echo "timed out waiting for $1 (see $RUN/*.log)" >&2; exit 1; }; }
# playwright-cli, installed once into the state dir: "npx -y @playwright/cli@latest" re-resolves the
# package on every call (about 10 s each, 6 minutes for one landing run).
pw_install() {
	[ -x "$PWBIN" ] && return 0
	echo "installing @playwright/cli into $RUN/pw (once)"
	npm install --silent --prefix "$(win "$RUN/pw")" @playwright/cli@latest >/dev/null 2>&1 || { echo "npm install @playwright/cli failed" >&2; exit 1; }
}
# Run from the repo root so its page snapshots and console logs land in one place: .playwright-cli/ (ignored).
pw() { (cd "$ROOT" && "$PWBIN" -s=afe "$@") 2>&1; }
# Run JavaScript in the page and print only its result (playwright-cli wraps it in markdown).
js() { pw eval "$1" | sed -n '/^### Result/,/^### Ran/p' | sed '1d;$d'; }
ref() { pw find "$1" | grep -oE "$2 \[ref=[a-z0-9]+\]" | head -1 | grep -oE 'ref=[a-z0-9]+' | cut -d= -f2; }
# Freeze clock-driven animations at a moment, or jump them to their end (scroll-driven ones are left alone).
freeze_at() { js "() => { document.getAnimations().forEach(a => { if (a.timeline instanceof DocumentTimeline) { a.pause(); a.currentTime = $1; } }); return 'frozen at $1 ms'; }" >/dev/null; }
settle() { js "() => { document.getAnimations().forEach(a => { if (a.timeline instanceof DocumentTimeline) a.finish(); }); return 'settled'; }" >/dev/null; }
snap() { pw screenshot --filename="$(win "$RUN/shots/$1")" >/dev/null; echo "screenshot: $RUN/shots/$1"; }
check() { printf '%s %s\n' "$([ "$2" = true ] && echo PASS || echo FAIL)" "$1"; [ "$2" = true ] || FAILED=1; }

up() {
	export AFE_DEBUG=1 AFE_FRONTEND_URL="$WEB"
	export AFE_DATABASE_URL="sqlite:///$(win "$RUN")/demo.db"
	export AFE_MEDIA_ROOT="$(win "$RUN")/media" AFE_PRIVATE_MEDIA_ROOT="$(win "$RUN")/private"
	if [ ! -f "$RUN/demo.db" ]; then
		(cd "$ROOT/backend" && "$(py)" -m alembic upgrade head >/dev/null 2>&1 && "$(py)" -m app.cli seed-demo)
	fi
	if up_already "$API/healthz"; then echo "API already running on :$API_PORT (not restarted)"; else
		(cd "$ROOT/backend" && nohup "$(py)" -m uvicorn app.main:app --port "$API_PORT" >"$RUN/api.log" 2>&1 &)
	fi
	if up_already "$WEB/"; then echo "website already running on :$WEB_PORT (not restarted)"; else
		(cd "$ROOT/frontend" && AFE_API_URL="$API" nohup npx vite dev --port "$WEB_PORT" --strictPort >"$RUN/web.log" 2>&1 &)
	fi
	wait_for "$API/healthz"
	wait_for "$WEB/"
	echo "API $API (demo data, logs $RUN/api.log) | website $WEB (logs $RUN/web.log)"
}

landing() {
	FAILED=0
	pw_install
	pw open >/dev/null
	pw resize 1280 800 >/dev/null
	pw set-reduced-motion no-preference >/dev/null
	pw goto "$WEB/" >/dev/null

	# 1. The hero: the listing ticket slides in, then its two checks pop. Frozen at 400 ms: ticket
	#    mid-entrance, checks not yet shown.
	freeze_at 400
	snap hero-400ms.png
	settle
	snap hero-settled.png
	local r
	r=$(js "() => document.getAnimations().map(a => a.animationName).filter(Boolean).join(',')")
	echo "animations: $r"
	check "every photo loads (Homes ready to view included)" "$(js "() => new Promise(done => { document.querySelectorAll('img[loading=lazy]').forEach(i => i.loading = 'eager'); setTimeout(() => done(document.images.length > 0 && [...document.images].every(i => i.naturalWidth > 0)), 1500); })")"
	check "hero ticket and check animations are attached" "$(js "() => { const n = document.getAnimations().map(a => a.animationName || ''); return n.some(x => x.endsWith('ticket-in')) && n.filter(x => x.endsWith('pop')).length === 2; }")"

	# 2. Scam check answers in place, and typing again clears the answer (as in the prototype).
	pw fill "#scam-check input[name=q]" "024 000 1111" >/dev/null
	pw click "#scam-check button[type=submit]" >/dev/null
	r=$(js "() => new Promise(done => setTimeout(() => done(document.querySelector('#scam-check .answer')?.textContent.trim().slice(0, 60) ?? 'none'), 1500))")
	echo "scam check: $r"
	check "scam check shows its answer on the landing page" "$(js "() => location.pathname === '/' && Boolean(document.querySelector('#scam-check .answer .tag, #scam-check .answer .badge'))")"
	pw fill "#scam-check input[name=q]" "024 000 2222" >/dev/null
	check "typing again clears the answer" "$(js "() => !document.querySelector('#scam-check .answer')")"
	js "() => { const s = document.querySelector('#scam-check'); scrollTo(0, s.getBoundingClientRect().top + scrollY - 120); return scrollY; }" >/dev/null
	snap scam-check.png

	# 3. Phone width: nothing wider than the screen; the menu opens and Escape closes it.
	pw resize 390 844 >/dev/null
	pw goto "$WEB/" >/dev/null
	settle
	check "no horizontal overflow at 390 px" "$(js "() => document.documentElement.scrollWidth <= innerWidth")"
	pw click ".burger" >/dev/null
	check "phone menu opens" "$(js "() => document.querySelector('.burger').getAttribute('aria-expanded') === 'true' && document.querySelector('#site-menu').offsetHeight > 0")"
	snap phone-menu.png
	pw press Escape >/dev/null
	check "Escape closes the phone menu" "$(js "() => document.querySelector('#site-menu').hidden && document.querySelector('#site-menu').offsetHeight === 0")"
	pw resize 1280 800 >/dev/null

	# 4. Reduced motion: nothing moves.
	pw set-reduced-motion reduce >/dev/null
	pw goto "$WEB/" >/dev/null
	check "reduced motion: no entrance animations" "$(js "() => document.getAnimations().filter(a => a.animationName).length === 0")"
	pw set-reduced-motion no-preference >/dev/null

	# 5. Search from the hero: lands on /homes with the same filters, with exactly one view transition.
	pw goto "$WEB/" >/dev/null
	js "() => { window.__vt = []; const o = document.startViewTransition.bind(document); document.startViewTransition = (cb) => { const t = o(cb); window.__vt.push('started'); t.finished.then(() => window.__vt.push('finished'), () => window.__vt.push('skipped')); return t; }; return 'hooked'; }" >/dev/null
	pw select ".hero-search select[name=area]" "madina-adenta" >/dev/null
	pw select ".hero-search select[name=bedrooms]" "1" >/dev/null
	pw click ".hero-search button[type=submit]" >/dev/null
	r=$(js "() => new Promise(done => setTimeout(() => done(location.pathname + location.search + ' | transition ' + window.__vt.join('>') + ' | homes ' + document.querySelectorAll('.res-card').length), 800))")
	echo "search: $r"
	check "hero search opens /homes with one finished view transition" "$(js "() => location.pathname === '/homes' && JSON.stringify(window.__vt) === JSON.stringify(['started','finished'])")"
	check "the results page keeps the chosen filters" "$(js "() => document.querySelector('.filters select[name=area]').value === 'madina-adenta' && document.querySelector('.filters input[name=bedrooms][value=\"1\"]').checked")"
	snap homes-after-search.png

	# 6. Section links (How it works, For landlords, Report a scam) scroll to their section with no "#" in the link
	#    or the address bar. Only the skip link keeps "#main", for browsers without JavaScript; it doesn't change the
	#    address either. An old "/#how" link lands on the section and the "#how" is dropped.
	local at_section="(id) => { const t = document.getElementById(id).getBoundingClientRect().top; return t >= 0 && t < 160; }"
	local click_text="(sel, text) => [...document.querySelectorAll(sel)].find(a => a.textContent.trim() === text).click()"
	pw goto "$WEB/" >/dev/null
	check "no link on the landing page has a # (skip link aside)" "$(js "() => [...document.querySelectorAll('a[href*=\"#\"]')].every(a => a.classList.contains('skip'))")"
	check "How it works scrolls to its section, address stays /" "$(js "() => new Promise(done => { ($click_text)('.site-head .links a', 'How it works'); setTimeout(() => done(location.href === '$WEB/' && ($at_section)('how')), 1500); })")"
	check "For landlords scrolls to its section, address stays /" "$(js "() => new Promise(done => { ($click_text)('.site-head .links a', 'For landlords'); setTimeout(() => done(location.href === '$WEB/' && ($at_section)('landlords')), 1500); })")"
	check "Report a scam opens /check at the report form, no #" "$(js "() => new Promise(done => { ($click_text)('footer a', 'Report a scam'); setTimeout(() => done(location.href === '$WEB/check' && ($at_section)('report')), 2500); })")"
	check "How it works from another page lands on the section, no #" "$(js "() => new Promise(done => { ($click_text)('footer a', 'How it works'); setTimeout(() => done(location.href === '$WEB/' && ($at_section)('how')), 2500); })")"
	pw goto "$WEB/" >/dev/null
	pw press Tab >/dev/null
	pw press Enter >/dev/null
	check "the skip link moves focus to the content, address unchanged" "$(js "() => document.activeElement.id === 'main' && location.href === '$WEB/'")"
	pw goto "$WEB/check" >/dev/null
	pw goto "$WEB/#how" >/dev/null
	check "an old /#how link lands on the section and drops the #" "$(js "() => new Promise(done => setTimeout(() => done(location.href === '$WEB/' && ($at_section)('how')), 1500))")"
	pw goto "$WEB/#landlords" >/dev/null
	check "a # typed on the open page lands on the section and is dropped" "$(js "() => new Promise(done => setTimeout(() => done(location.href === '$WEB/' && ($at_section)('landlords')), 1500))")"

	[ "$FAILED" = 0 ] && echo "landing: all checks passed" || { echo "landing: some checks FAILED" >&2; exit 1; }
}

shot() {
	local path="${1:-/}" w="${2:-1280}" h="${3:-800}"
	pw_install
	pw open >/dev/null
	pw resize "$w" "$h" >/dev/null
	pw goto "$WEB$path" >/dev/null
	settle
	snap "page$(printf '%s' "$path" | tr '/?&=' '____')-${w}.png"
}

pages() {
	FAILED=0
	pw_install
	pw open >/dev/null
	pw set-reduced-motion no-preference >/dev/null
	local paths p w code r logs before
	paths=$(curl -s "$WEB/" | grep -oE 'href="/[^"#]*"' | sed 's/href="//;s/"$//' | sort -u)
	mkdir -p "$RUN/shots/pages"
	# Where each console log ends now: only lines added during the sweep are reported.
	before="$RUN/console-before.txt"
	(cd "$ROOT" && for f in .playwright-cli/console-*.log; do [ -f "$f" ] && echo "$f $(wc -l <"$f")"; done) >"$before" 2>/dev/null || true
	for w in 1280 390; do
		pw resize "$w" "$([ "$w" = 390 ] && echo 844 || echo 800)" >/dev/null
		for p in $paths; do
			code=$(curl -s -o /dev/null -w '%{http_code}' "$WEB$p")
			pw goto "$WEB$p" >/dev/null
			# Load lazy images too, so photos below the fold are checked.
			r=$(js "() => new Promise(done => { document.querySelectorAll('img[loading=lazy]').forEach(i => i.loading = 'eager'); setTimeout(() => { const broken = [...document.images].filter(i => i.complete && i.naturalWidth === 0).length; done([broken, document.documentElement.scrollWidth > innerWidth, document.querySelectorAll('h1').length].join(' ')); }, 1500); })")
			r=$(printf '%s' "$r" | tr -d '"\\')
			set -- $r
			if [ "$code" = 200 ] && [ "$1" = 0 ] && [ "$2" = false ] && [ "$3" = 1 ]; then echo "PASS ${w}px $p"; else
				echo "FAIL ${w}px $p (status $code, broken images $1, overflow $2, h1 count $3)"; FAILED=1; fi
			settle
			snap "pages/$(printf '%s' "$p" | tr '/?&=' '____')-${w}.png" >/dev/null
		done
	done
	# Console errors logged during the sweep, with the page they came from.
	r=$(cd "$ROOT" && for f in .playwright-cli/console-*.log; do [ -f "$f" ] || continue
		n=$(grep -F "$f " "$before" | awk '{print $2}'); tail -n +"$(( ${n:-0} + 1 ))" "$f"; done | grep "\[ERROR\]" || true)
	if [ -n "$r" ]; then echo "FAIL console errors:"; printf '%s\n' "$r" | head -20; FAILED=1; else echo "PASS no console errors"; fi
	# Page-scoped class names that the global stylesheet already styles (see SKILL.md, Gotchas).
	r=$(cd "$ROOT/frontend" && for f in $(find src/routes -name '+page.svelte'); do
		grep -q '<style' "$f" || continue
		for c in $(sed -n '/<style/,/<\/style>/p' "$f" | grep -oE '^\s*\.[a-z][a-z0-9-]*' | tr -d ' .	' | sort -u); do
			grep -qE "(^|[ ,}])\.$c([ ,:.{\[]|$)" src/app.css && echo "  $f: .$c"; done; done)
	if [ -n "$r" ]; then echo "FAIL page styles reuse global class names:"; echo "$r"; FAILED=1; else echo "PASS no page style reuses a global class name"; fi
	echo "screenshots: $RUN/shots/pages/"
	[ "$FAILED" = 0 ] && echo "pages: all checks passed" || { echo "pages: some checks FAILED" >&2; exit 1; }
}

# The audit is a Node script (a11y.cjs) using the Playwright library that comes with playwright-cli. The MFA roles
# sign in with a code from the demo database, so it must be the database the API is serving.
a11y() {
	pw_install
	up_already "$API/healthz" && up_already "$WEB/" || { echo "the servers aren't up: run driver.sh up first" >&2; exit 1; }
	PW_DIR="$(win "$RUN/pw")" BACKEND_DIR="$(win "$ROOT/backend")" DEMO_DB="$(win "$RUN/demo.db")" OUT="$(win "$RUN/a11y.json")" \
		node "$(win "$ROOT/.claude/skills/run-afe/a11y.cjs")"
}

stop_port() {
	local port=$1 pid
	if command -v taskkill >/dev/null 2>&1; then
		pid=$(netstat -ano | grep -E "[:.]$port .*LISTENING" | awk '{print $NF}' | head -1)
		[ -n "$pid" ] && taskkill //F //T //PID "$pid" >/dev/null && echo "stopped :$port (pid $pid)"
	else
		pid=$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null | head -1)
		[ -n "$pid" ] && kill "$pid" && echo "stopped :$port (pid $pid)"
	fi
	return 0
}

down() {
	[ -x "$PWBIN" ] && { pw close >/dev/null || true; }
	stop_port "$WEB_PORT"
	stop_port "$API_PORT"
}

case "${1:-}" in
	up) up ;;
	landing) landing ;;
	shot) shift; shot "$@" ;;
	pages) pages ;;
	a11y) a11y ;;
	down) down ;;
	*) sed -n '2,14p' "$0"; exit 2 ;;
esac
