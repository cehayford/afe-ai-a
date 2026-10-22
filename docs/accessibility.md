# Accessibility (WCAG 2.1 AA)

The build plan requires a WCAG 2.1 AA pass before the beta gate. It has two parts. An automated audit covers
everything a script can measure, and it runs on demand. A person with a screen reader checks the rest, once before
the gate and again after a large change to a flow.

## The automated audit

```bash
bash .claude/skills/run-afe/driver.sh up      # seeded demo API + website
bash .claude/skills/run-afe/driver.sh a11y    # about 3 minutes; exits 1 on any finding
```

It signs in as each demo role and visits every page that role uses, in light and dark mode. The roles are a visitor,
a renter (yaa), a landlord (ama), a verifier and a reviewer. It also opens one page of each kind of detail page it
finds: a home, an area, a conversation, a tenancy, a review case and so on. The demo data has no field visit in
progress, so as the verifier it checks in to an open assignment first, at the home's own position (emulated GPS).
That starts one visit in the throwaway demo database. On 2 Oct 2026 this came to 55 pages, or 110 page visits. It
checks:

- **Names and labels.** Every button, link and form field has an accessible name; fields have labels, not just
  placeholders; images have alt text; `aria-labelledby`, `aria-describedby` and `aria-controls` point at elements
  that exist; nothing reachable by Tab is hidden from screen readers.
- **Structure.** The page language, a title, one `<main>`, one visible `<h1>`, no skipped heading levels, no
  duplicate ids.
- **Contrast.** All visible text against the background it actually sits on: 4.5:1, or 3:1 for large text. This
  runs in both themes.
- **Keyboard focus.** It tabs through the first 30 stops on each page. Every stop must look different when focused
  and be on screen.
- **Reflow.** No sideways scrolling at 320 px wide (WCAG 1.4.10).

The report is written to `<temp>/afe-run/a11y.json`. The script is `.claude/skills/run-afe/a11y.cjs`.

### Fixed in the first pass (2 Oct 2026)

- **Dark-mode contrast.**
  - Avatars, the landing page's step numbers, review tags and visit-plan numbers were dark green on dark green
    (1.1:1).
  - White text on the red and green fills was unreadable: Approve, Reject, Suspend, Uphold, "Money lost", the
    verification ticks (1.7:1 to 2.8:1).
  - Two new colour tokens, `--on-ok` and `--on-crit`, set the text colour on those fills: white in light mode, near
    black in dark mode.
- **Hover colours in dark mode.** A listing title, a landlord's listing title and the text-style buttons turned dark
  green on hover. They now use the dark theme's hover green.
- **Map pins.** A screen reader read a pin as "✓ 4.0k". It now hears "3-bedroom house near Adenta Barrier, verified,
  GH₵4,000 a month". A focused pin now shows a ring and turns amber, and its card in the list is highlighted, as on
  hover. Leaflet's attribution link was too faint.
- **The phone menu.** The menu button's `aria-controls` pointed at a menu that wasn't in the page while closed. The
  menu is now always in the page and hidden while closed.
- **320 px.** Three things ran off the screen: the "Second check" tag in the field app, the "use my location" button
  when adding a home, and the review decision form's evidence chips. They wrap now.

### Fixed in the second pass: what a screen reader hears (2 Oct 2026)

- **Messages after an action were silent.** Most forms save without loading a new page, then show a confirmation
  such as "Decision saved." Nothing told a screen reader. There are now two kinds of message:
  - **Confirmations** use the `Done` component (`$lib/components/Done.svelte`). It shows the message and reads it
    out through one site-wide announcer (`$lib/announce.svelte.ts`, in the root layout). The announcer is always in
    the page, because a status box added together with its message is often read by no screen reader. It reads the
    same message again after a second action.
  - **Errors** keep `FormError` (`role="alert"`). Screen readers announce those when they appear.
  The scam check's verdict and the field app's check-in and upload messages also go through the announcer.
- **The field visit page** was never audited: nothing links to it until a visit starts.
  - Each checklist question is now a group named by its question, so "Yes" and "No" are heard with it. The same
    goes for Pass and Fail under "Result".
  - "Take a photo" was a label for a hidden file input. Keyboards couldn't reach it, and screen readers didn't
    present it as a control. It is now a button.
  - The photo count reads "2 saved, at least 4 needed" instead of "2 / 4 min".
  - The notes box has a label.
  - The saved ✓ on a photo was white on the photo itself, and vanished on a light one. The marks now sit on a solid
    badge. Each photo's description also says whether it is saved ("Living room, saved").
  - After each upload the status line says "Photo saved: Living room. 2 of at least 4." Before, it stayed on
    "Uploading…". A failed upload now says so.
- **The landlord's verification steps.**
  - Each step in the list says its number and whether it is done ("Step 1, done: Ghana Card").
  - Choosing a step, or Back and Continue, moves focus to that step's heading. Before, the card changed with no
    sign.
  - The document type choices are a named group.

To use from now on: show a confirmation with `<Done message={form?.done} key={form} />`, not a hand-made notice.
For any other message that appears without a new page, call `announce(text)`.

## Manual checks (before the beta gate)

The script can't hear what a screen reader says, judge whether the reading order makes sense, or use a phone.
Plan about half a day, and use the demo sign-ins from the root README.

- **Renters:** Android with TalkBack and Chrome, because most renters will use an Android phone.
- **Reviewers:** Windows with NVDA and Chrome or Edge.

Write down anything that is confusing, silent or wrong, with the page and the step.

Steps marked **(seen in a browser)** were checked on 2 Oct 2026 by reading the browser's accessibility tree and
what the site's announcer said, not with a real screen reader. They should pass; the person's job is to confirm
them with real speech.

### Everyone: the basics on any three pages

1. Turn on the screen reader and load the page. The page title is read first.
2. Press Tab once. "Skip to content" is the first stop, and activating it moves to the main content.
3. Move through the page by headings (NVDA: H; TalkBack: the headings reading control). The headings outline the
   page.
4. Zoom the browser to 200%, then 400%. Nothing is cut off, and you only scroll up and down.
5. Turn on reduced motion in the system settings. Nothing slides or fades in.

### Renter (TalkBack, phone)

1. **Search.** From the landing page, search for homes in East Legon. On the results page, each result card reads
   its title, area, bedrooms, rent and both "verified" labels. The bedroom filter says which choice is selected.
2. **The map.** Swipe to the map pins. Each pin reads the home, "verified", and the monthly rent, and a double tap
   opens the home **(seen in a browser)**. The map is extra: the list has the same homes and facts.
3. **A home.** Open a home. The photos have descriptions, and the verification facts read in order. Request a
   viewing: the day and time choices read as groups, with the selected one marked.
4. **Scam check.** Enter a phone number on the scam check page. You hear the answer, such as "Not verified by Afe.
   This number is not verified by Afe.", without moving to it **(seen in a browser)**.
5. **Sign in with a phone code.** The phone number field and the code field are labelled. A wrong code is announced.

### Landlord (TalkBack, phone)

1. **Get verified.** The step list reads "Step 1, done: Ghana Card", and so on **(seen in a browser)**. Choosing a
   step, or Back and Continue, moves you to that step's heading **(seen in a browser)**.
2. **Add a home.** The map reads as "Map: tap where the home is", which a blind landlord can't use. Check that
   "I'm at the home: use my location" works on its own and that the pin's status is announced afterwards.
3. **Upload a document.** The document type choices read as a group named "Document type" **(seen in a browser)**.
   The file field is labelled. After the upload you hear "Document uploaded." This is new and hasn't been tried.

### Verifier (TalkBack, phone, outdoors if possible)

1. **A visit.** Open today's visit.
   - Each "Yes" and "No" is read with its question and says whether it is pressed **(seen in a browser)**.
   - "Take a photo" is a button **(seen in a browser)**.
   - After each upload you hear "Photo saved: Living room. 2 of at least 4." **(seen in a browser)**.
   - A photo that can't be saved is announced, with what to do.
2. **Send it.** Submit the visit. A failure, such as no signal, is announced, as well as shown.

### Reviewer (NVDA, keyboard only)

1. **The queue.** Work the review queue without a mouse. Tab order follows the screen. Every control shows a visible
   focus ring.
2. **Decide a home.**
   - Open a case. The evidence checkboxes are announced with their group name, "Evidence you checked (to approve)".
   - The reason code and note fields are labelled.
   - Reject stays unavailable until you choose a reason code. The reason list's first option says it is "required to
     reject". Check that this is clear when you meet Reject first.
   - Deciding takes you back to the queue, and the queue's page title is read. Check that this is enough to know
     the decision was saved.
3. **Scam reports.** Uphold one and leave one not upheld. Each time you hear "Decision saved." **(seen in a
   browser)**.

## Keeping it passing

Run `driver.sh a11y` after changing colours, shared components or a page's layout, and before a release. A new page
is covered once it is added to `ROLES` (for a fixed path) or `DYNAMIC` (for a detail page) at the top of `a11y.cjs`.
