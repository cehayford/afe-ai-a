// Accessibility audit of the running Afe website (WCAG 2.1 AA checks that can be automated), per role, light and dark.
// Run it through the driver: `driver.sh a11y`. It needs the servers up (`driver.sh up`) and reads PW_DIR (the
// Playwright the driver installed), BACKEND_DIR, DEMO_DB and OUT (the JSON report) from the environment.
// Prints the findings by rule and exits 1 if there are any. It can't judge everything: screen-reader wording, reading
// order and whether a focus order makes sense still need a person (docs/accessibility.md).
const { chromium } = require(process.env.PW_DIR + '/node_modules/playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');

const BASE = 'http://localhost:5173';
const PASSWORD = 'afe-demo-password';
const BACKEND = process.env.BACKEND_DIR;
const DB = process.env.DEMO_DB;

const ROLES = {
  anon: { pages: ['/', '/homes', '/check', '/rent-index', '/privacy', '/terms', '/signin', '/signin?mode=password', '/signup'] },
  renter: { user: 'yaa', pages: ['/account', '/account/viewings', '/account/messages', '/account/saved', '/account/alerts',
    '/account/notifications', '/account/payments', '/account/appeals', '/account/home', '/tenancies'] },
  landlord: { user: 'ama', mfa: true, pages: ['/landlord', '/landlord/homes/new', '/landlord/listings', '/landlord/enquiries',
    '/landlord/verify', '/landlord/payouts', '/landlord/rentals'] },
  verifier: { user: 'verifier', mfa: true, pages: ['/field'], prepare: startVisit },
  reviewer: { user: 'reviewer', mfa: true, pages: ['/review', '/review/detection', '/review/rules', '/review/money',
    '/review/reports', '/review/appeals', '/review/areas', '/review/insights', '/review/label-checks', '/review/staff',
    '/review/verifiers', '/review/visit-plan', '/review/workload'] },
};
// Dynamic pages: the first link of each kind found while crawling a role's pages is added once.
const DYNAMIC = [/^\/homes\/AFE-[A-Z0-9]+$/, /^\/homes\/AFE-[A-Z0-9]+\/viewing$/, /^\/areas\/[a-z-]+$/, /^\/account\/messages\/\d+$/,
  /^\/landlord\/homes\/\d+$/, /^\/landlord\/listings\/\d+$/, /^\/landlord\/offer\/\d+$/, /^\/field\/assignments\/\d+$/,
  /^\/field\/visits\/\d+$/, /^\/review\/homes\/\d+$/, /^\/review\/people\/\d+$/, /^\/tenancies\/AFE-T-[A-Z0-9]+$/, /^\/rentals\/\d+$/];

function totp(user) {
  const out = execFileSync(`${BACKEND}/.venv/Scripts/python.exe`, ['-W', 'ignore', '-m', 'app.cli', 'totp', user], {
    cwd: BACKEND, env: { ...process.env, AFE_DEBUG: '1', AFE_DATABASE_URL: `sqlite:///${DB}` } }).toString().trim();
  return out.split(/\s+/).pop();
}

// The demo data has no visit in progress, so nothing links to the field visit page. Check in to the first open
// assignment, standing (by emulated GPS) at the home's pin; from then on /field links to the visit. It starts one
// visit in the throwaway demo database.
async function startVisit(page, context) {
  await page.goto(`${BASE}/field`, { waitUntil: 'networkidle' });
  if (await page.$('a[href^="/field/visits/"]')) return;
  for (const href of await page.$$eval('a[href^="/field/assignments/"]', (as) => as.map((a) => a.getAttribute('href')))) {
    await page.goto(BASE + href, { waitUntil: 'networkidle' });
    const directions = await page.$('a[href*="google.com/maps/dir"]');
    const checkIn = await page.$('button:has-text("Check in")');
    if (!directions || !checkIn) continue;
    const [latitude, longitude] = new URL(await directions.getAttribute('href')).searchParams.get('destination').split(',').map(Number);
    await context.grantPermissions(['geolocation'], { origin: BASE });
    await context.setGeolocation({ latitude, longitude, accuracy: 5 });
    await Promise.all([page.waitForURL(/\/field\/visits\/\d+/, { timeout: 15000 }), checkIn.click()]);
    return;
  }
  throw new Error('no field visit to audit: no visit in progress and no open assignment to check in to');
}

async function signIn(page, role) {
  await page.goto(`${BASE}/signin?mode=password`);
  await page.fill('input[name=login]', role.user);
  await page.fill('input[name=password]', PASSWORD);
  await Promise.all([page.waitForLoadState('networkidle'), page.click('form[action*="password"] button[type=submit]')]);
  if (role.mfa) {
    await page.waitForSelector('input[name=code]', { timeout: 10000 });
    await page.fill('input[name=code]', totp(role.user));
    await page.click('form[action*="mfa"] button[type=submit]');
    await page.waitForSelector('text=/signed in/i', { timeout: 10000 });  // the page confirms; it doesn't redirect
    return;
  }
  await page.waitForTimeout(500);
  if (page.url().includes('/signin')) throw new Error(`sign-in failed for ${role.user}: ${page.url()}`);
}

// Runs in the page: everything checkable from the DOM.
function inspect() {
  const issues = [];
  const add = (rule, el, detail) => issues.push({ rule, where: where(el), detail: (detail || '').slice(0, 160) });
  // The contents of a closed <details> still have boxes in Chrome, but nobody can see or reach them.
  const folded = (el) => { const d = el.closest('details:not([open])'); return !!d && !el.closest('summary'); };
  const visible = (el) => { if (folded(el)) return false; const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  function where(el) {
    if (!el || !el.tagName) return '';
    const bits = [el.tagName.toLowerCase()];
    if (el.id) bits.push('#' + el.id);
    if (el.classList.length) bits.push('.' + [...el.classList].slice(0, 2).join('.'));
    const name = el.getAttribute('name'); if (name) bits.push(`[name=${name}]`);
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    return bits.join('') + (text ? ` "${text}"` : '');
  }
  const byId = (id) => document.getElementById(id);
  function name(el) {
    const by = el.getAttribute('aria-labelledby');
    if (by) return by.split(/\s+/).map((i) => byId(i)?.innerText || '').join(' ').trim();
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) {
      if (el.type === 'submit' || el.type === 'button') return el.value;
      const lab = el.labels && el.labels.length ? [...el.labels].map((l) => l.innerText).join(' ').trim() : '';
      return lab || el.getAttribute('title') || '';
    }
    const t = (el.innerText || '').trim();
    if (t) return t;
    const img = el.querySelector('img[alt]'); if (img && img.alt.trim()) return img.alt.trim();
    const svgTitle = el.querySelector('svg title'); if (svgTitle) return svgTitle.textContent.trim();
    return el.getAttribute('title') || '';
  }

  if (!document.documentElement.lang) add('html-lang', document.documentElement, 'no lang on <html>');
  if (!document.title.trim()) add('page-title', document.documentElement, 'empty <title>');
  const mains = document.querySelectorAll('main, [role=main]');
  if (mains.length !== 1) add('main-landmark', document.body, `${mains.length} main landmarks`);
  const h1s = [...document.querySelectorAll('h1')].filter(visible);
  if (h1s.length !== 1) add('one-h1', document.body, `${h1s.length} visible h1`);
  let last = 0;
  for (const h of document.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
    if (!visible(h)) continue;
    const level = +h.tagName[1];
    if (last && level > last + 1) add('heading-skip', h, `h${last} then h${level}`);
    last = level;
  }
  const ids = {};
  for (const el of document.querySelectorAll('[id]')) ids[el.id] = (ids[el.id] || 0) + 1;
  for (const [id, n] of Object.entries(ids)) if (n > 1) add('duplicate-id', byId(id), `id "${id}" used ${n} times`);
  for (const el of document.querySelectorAll('[aria-labelledby],[aria-describedby],[aria-controls]')) {
    for (const attr of ['aria-labelledby', 'aria-describedby', 'aria-controls']) {
      for (const id of (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean)) {
        if (!byId(id)) add('aria-ref-missing', el, `${attr} -> #${id} not found`);
      }
    }
  }
  for (const img of document.querySelectorAll('img')) if (!img.hasAttribute('alt')) add('img-alt', img, img.src.split('/').pop());
  for (const svg of document.querySelectorAll('svg')) {
    if (!visible(svg) || svg.closest('[aria-hidden=true]')) continue;
    if (svg.getAttribute('role') === 'img' && !svg.getAttribute('aria-label') && !svg.querySelector('title')) add('svg-name', svg, 'role=img with no name');
  }
  const focusable = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[tabindex]:not([tabindex="-1"]),[role=button],[role=link],[role=radio],[role=checkbox],[role=tab],[role=switch]';
  for (const el of document.querySelectorAll(focusable)) {
    if (!visible(el) && !(el.tagName === 'INPUT' && el.closest('label'))) continue;
    if (!name(el).trim()) add('control-name', el, `${el.tagName.toLowerCase()} with no accessible name`);
    // tabindex=-1 takes it out of the tab order: a duplicate link hidden from screen readers is fine.
    if (el.tabIndex >= 0 && el.closest('[aria-hidden=true]')) add('focusable-hidden', el, 'focusable inside aria-hidden');
  }
  for (const el of document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea')) {
    // Not rendered at all (a hidden file input opened by a button): screen readers never meet it.
    if (folded(el) || el.hidden || getComputedStyle(el).display === 'none') continue;
    const labelled = (el.labels && el.labels.length) || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title');
    if (!labelled) add('form-label', el, el.getAttribute('placeholder') ? `only a placeholder: "${el.getAttribute('placeholder')}"` : 'no label');
  }
  for (const el of document.querySelectorAll('[role=radio]')) if (!el.closest('[role=radiogroup]')) add('radio-group', el, 'role=radio outside a radiogroup');
  for (const el of document.querySelectorAll('a[href]')) {
    const t = name(el).trim().toLowerCase();
    if (['click here', 'here', 'more', 'read more', 'link'].includes(t)) add('link-purpose', el, t);
  }
  for (const el of document.querySelectorAll('iframe')) if (!el.title) add('iframe-title', el, 'no title');
  for (const el of document.querySelectorAll('video[autoplay],audio[autoplay]')) if (!el.muted) add('autoplay', el, 'autoplays with sound');

  // Contrast of visible text against its effective background.
  const rgba = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const blend = (top, bottom) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1); };
  const lum = (c) => { const v = c.slice(0, 3).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  function background(el) {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null;
      const c = rgba(s.backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    let bg = [255, 255, 255, 1];
    for (const layer of layers.reverse()) bg = blend(layer, bg);
    return bg;
  }
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!node.textContent.trim()) continue;
    const el = node.parentElement;
    if (!el || !visible(el) || el.closest('[aria-hidden=true],.sr,.skip,script,style,noscript')) continue;
    const s = getComputedStyle(el);
    if (+s.opacity === 0) continue;
    const bg = background(el); if (!bg) continue;
    let fg = rgba(s.color); if (!fg) continue;
    fg = blend(fg, bg);
    const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
    const ratio = (a + 0.05) / (b + 0.05);
    const size = parseFloat(s.fontSize), bold = +s.fontWeight >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const need = large ? 3 : 4.5;
    const disabled = el.closest('button:disabled,[aria-disabled=true],input:disabled');
    if (ratio < need && !disabled) {
      const key = `${s.color}|${bg.join(',')}|${el.className}`;
      if (seen.has(key)) continue; seen.add(key);
      add('contrast', el, `${ratio.toFixed(2)}:1 (needs ${need}) "${node.textContent.trim().slice(0, 30)}" ${s.color} on rgb(${bg.slice(0, 3).map(Math.round)})`);
    }
  }
  return issues;
}

// Tab through the page: each focused element must show a visible change from its unfocused look.
async function focusCheck(page) {
  const issues = [];
  await page.evaluate(() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); });
  await page.mouse.click(1, 1).catch(() => {});
  const seen = new Set();
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press('Tab');
    const r = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const props = ['outlineStyle', 'outlineWidth', 'outlineColor', 'boxShadow', 'backgroundColor', 'borderTopColor', 'borderBottomColor', 'textDecorationLine', 'color'];
      // A wrapper can draw the ring instead (:focus-within), as the phone number field does.
      const ring = ['outlineStyle', 'outlineWidth', 'boxShadow'];
      const wrappers = [el.parentElement, el.parentElement?.parentElement, el.parentElement?.parentElement?.parentElement].filter(Boolean);
      // A focusable box with no size whose child is what you see (a map pin): judge the child.
      const own = el.getBoundingClientRect();
      const shown = !own.width && !own.height && el.firstElementChild ? el.firstElementChild : el;
      const look = () => props.map((p) => getComputedStyle(el)[p]).concat(shown === el ? [] : props.map((p) => getComputedStyle(shown)[p]),
        wrappers.flatMap((w) => ring.map((p) => getComputedStyle(w)[p]))).join('|');
      const focused = look();
      const r = shown.getBoundingClientRect();
      const tag = el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').slice(0, 2).join('.') : '') +
        ' "' + ((el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 30)) + '"';
      el.blur();
      const plain = look();
      el.focus({ preventScroll: true });
      const offscreen = r.bottom < 0 || r.right < 0 || r.width === 0 || r.height === 0;
      return { tag, changed: focused !== plain, offscreen, key: tag + r.x + r.y };
    });
    if (!r) continue;
    if (seen.has(r.key)) break;
    seen.add(r.key);
    if (!r.changed && !r.offscreen) issues.push({ rule: 'focus-visible', where: r.tag, detail: 'no visible change on keyboard focus' });
    if (r.offscreen && !r.tag.includes('skip')) issues.push({ rule: 'focus-offscreen', where: r.tag, detail: 'focused element not on screen' });
  }
  return issues;
}

async function reflow(page) {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.waitForTimeout(300);
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  await page.setViewportSize({ width: 1280, height: 900 });
  return over > 1 ? [{ rule: 'reflow-320', where: 'page', detail: `${over}px horizontal scroll at 320px wide` }] : [];
}

(async () => {
  const out = process.env.OUT || 'a11y.json';
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const report = [];
  for (const [roleName, role] of Object.entries(ROLES)) {
    for (const scheme of ['light', 'dark']) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: scheme, reducedMotion: 'reduce' });
      const page = await context.newPage();
      try {
        if (role.user) await signIn(page, role);
        if (role.prepare) await role.prepare(page, context);
      } catch (e) { report.push({ role: roleName, scheme, path: '(sign-in)', error: String(e) }); await context.close(); continue; }
      const queue = [...role.pages], done = new Set(), found = new Set();
      while (queue.length) {
        const path = queue.shift();
        if (done.has(path)) continue;
        done.add(path);
        const entry = { role: roleName, scheme, path, issues: [] };
        try {
          const res = await page.goto(BASE + path, { waitUntil: 'networkidle' });
          entry.status = res ? res.status() : null;
          entry.final = new URL(page.url()).pathname;
          await page.waitForTimeout(300);
          entry.issues.push(...await page.evaluate(inspect));
          if (scheme === 'light') {
            entry.issues.push(...await focusCheck(page));
            entry.issues.push(...await reflow(page));
          }
          if (scheme === 'light') {
            const links = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map((a) => new URL(a.href, location.href))
              .filter((u) => u.origin === location.origin).map((u) => u.pathname));
            for (const link of links) {
              const kind = DYNAMIC.find((re) => re.test(link));
              if (kind && !found.has(kind.source)) { found.add(kind.source); queue.push(link); }
            }
          }
        } catch (e) { entry.error = String(e).slice(0, 200); }
        report.push(entry);
        if (process.env.VERBOSE) process.stdout.write(`${roleName}/${scheme} ${path} ${entry.status || ''} ${entry.issues.length} issues\n`);
      }
      role.pages = [...done]; // dark mode visits the same pages, dynamic ones included
      await context.close();
    }
  }
  await browser.close();
  fs.writeFileSync(out, JSON.stringify(report, null, 1));

  // Summary: each rule once, with its distinct findings and where they show up.
  const broken = report.filter((e) => e.error || (e.status && e.status !== 200));
  const byRule = {};
  for (const e of report) {
    for (const i of e.issues || []) {
      const key = `${i.where} | ${i.detail}`;
      const rule = (byRule[i.rule] ||= {});
      (rule[key] ||= new Set()).add(`${e.path} (${e.role}, ${e.scheme})`);
    }
  }
  console.log(`\n${report.length} page visits, ${broken.length} broken, ${Object.keys(byRule).length} rules with findings`);
  for (const e of broken) console.log(`BROKEN ${e.role}/${e.scheme} ${e.path}: ${e.error || 'status ' + e.status}`);
  for (const [rule, findings] of Object.entries(byRule)) {
    console.log(`\n${rule} (${Object.keys(findings).length})`);
    for (const [finding, places] of Object.entries(findings)) {
      const list = [...places];
      console.log(`  ${finding}\n    on ${list.slice(0, 3).join(', ')}${list.length > 3 ? ` and ${list.length - 3} more` : ''}`);
    }
  }
  console.log(`\nReport: ${out}`);
  const ok = !broken.length && !Object.keys(byRule).length;
  console.log(ok ? 'PASS: no findings' : 'FAIL');
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
