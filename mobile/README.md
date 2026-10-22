# Afe mobile app (Android and iOS)

One Flutter app for everyone who uses Afe on a phone. It opens differently for each kind of user:

| Who | Tabs | What they can do |
|---|---|---|
| Visitors (not signed in) | Homes, Check, Account | Search verified homes (list or map), see a home's photos and what Afe checked, Check before you pay, sign in or sign up |
| Renters | Homes, Saved, Messages, Tenancy, Account | Save homes, message landlords, book and cancel viewings, say whether they're renting after a viewing, home alerts, accept an offer and pay at the partner's checkout, confirm move-in (with a photo), raise a problem, notifications |
| Landlords and agents | Homes, Viewings, Messages, Account | The Ghana Card check with a selfie, adding a home (GhanaPost address and a pin on the map, inside the area's outline), ownership documents (camera, photos or PDF), the verification fee, creating and submitting listings, taking them down, confirming viewings and marking attendance, messages, tenancies (withdraw, record the handover, raise a problem), the payout account (with an authenticator code) |
| Field verifiers | Visits, Account | Today's visits, directions and calling the landlord, check-in by GPS (within the visit radius), camera photos with captions, an offline upload queue, the checklist, travel time and fares, submit |
| Reviewers and admins | | A pointer to the website: review work needs a big screen |

**First run: Get started.** A new install opens on three welcome slides (landlords are checked, homes are
visited, rent is held until move-in), then "How will you use Afe?" (renter, landlord or agent, or a verifier
with an invite). Sign-up starts with that role picked, and a "ready" screen follows with the first three steps
for the role, WhatsApp reminders and a button into the first task. "I already have an account" and "Just
looking?" skip ahead. The phone remembers that the welcome was seen (`afe_onboarded` in secure storage).

**Documents open in the app.** Rent receipts, the invoice for the next rent, rental agreements, the tenancy
receipt and agreement, the move-in photo, and each fee's invoice or receipt. The app asks the API for a
five-minute link to the one file (`POST /documents/links`) and opens it in the phone's viewer. The download
checks the person's access again.

**On the website for now** (the app links there): writing a review, and downloading or closing an account.

**Not built yet: push notifications.** They need a Firebase project (Android) and an Apple Push key (iOS),
plus an API endpoint for device tokens. Until then, alerts go by SMS, WhatsApp and the in-app inbox.

## How it talks to Afe

The app calls the API directly (the website goes through its own server). Tokens are kept in the Keychain
(iOS) or encrypted storage (Android) and refreshed automatically. Each install sends a random device ID
(`X-Afe-Device-Id`), like the website's cookie, so the fraud graph can link accounts used on one phone.

The API needs a public address for the app:
- **On AWS:** set `api_domain` in `infra/terraform/staging` (e.g. `api.staging.afe.example`, on the same certificate).
- **On the free server:** `API_ADDRESS` in `deploy/free-server/.env`.

Rate limits see the phone's real address. The API trusts `X-Forwarded-For` only from our own proxies.

## Develop

Needs Flutter 3.47 or newer (`flutter doctor`). Android builds need Android Studio (SDK and an emulator);
iOS builds need a Mac with Xcode.

```bash
cd mobile
flutter pub get
flutter analyze
flutter test                                   # offline unit and widget tests

# Run against a local API (the Android emulator reaches your computer at 10.0.2.2):
flutter run --dart-define=AFE_API_URL=http://10.0.2.2:8000 --dart-define=AFE_WEB_URL=http://10.0.2.2:5173

# Or against the free development server:
flutter run --dart-define=AFE_API_URL=https://api.dev.afe.example --dart-define=AFE_WEB_URL=https://dev.afe.example
```

Demo accounts come from `python -m app.cli seed-demo` (see the root README). Renters sign in with an SMS code,
which the development API prints in its log. Staff, landlords and agents use the demo password and an
authenticator code.

**Contract test against a live API.** This test uses the app's own client and models to sign in as a renter,
a landlord and a verifier. It books a viewing, then adds a home and uploads its ownership document. It checks
that a first payout account works at once and a changed one waits 72 hours. Finally it starts a visit and
uploads a photo twice, which must be stored once.

It also runs the screens added from the "Afe Missing Features" design. As the landlord it covers settings and
devices, fees paid and appeals. It offers a tenancy on the demo's completed viewing, and an offer over the legal
cap is refused. It features and then edits a listing, adds a tenant, records rent, and handles the agreement
and a renewal. It opens each rent and fee document by its short-lived link, lists the landlord's listings and
chooses a plan. As the renter it covers My home (a repair, signing, accepting the renewal), a scam report, the
rent index and an area, and signing out everywhere.

Run it on fresh demo data, with protected payments on. The test reads authenticator codes through the backend
CLI, so give it the same database settings as the API:

```bash
cd backend && export AFE_DEBUG=1 AFE_PROTECTED_PAYMENTS_ENABLED=1 AFE_DATABASE_URL=sqlite:///live-test.db
python -m alembic upgrade head && python -m app.cli seed-demo && uvicorn app.main:app --port 8765
# in another terminal, with the same AFE_DATABASE_URL exported:
cd mobile && AFE_LIVE_API=http://127.0.0.1:8765 AFE_LIVE_BACKEND=../backend flutter test test/live_api_test.dart
```

## Release builds

```bash
flutter build appbundle --dart-define=AFE_API_URL=https://api.afe.example --dart-define=AFE_WEB_URL=https://afe.example
flutter build ipa       --dart-define=AFE_API_URL=https://api.afe.example --dart-define=AFE_WEB_URL=https://afe.example
```

Before the first store release:
- **App ID:** the app ID is `com.afe.afe`; change it to Afe's registered one (e.g. `gh.afe.app`).
- **Icon and splash screen:** Afe's icon is the lettermark tile from the design (an "a" under an amber roof,
  `assets/icon-1024.png`): rounded on Android, square on iOS (iOS rounds it). The Android launch screen is Afe green.
- **Android signing:** create the upload key and fill in `android/key.properties`. Never commit either.
- **iOS signing:** set the team and signing in Xcode.
- **Store listings:** Google Play (a one-off $25) and the Apple Developer Program ($99 a year).
- **Privacy answers:** both stores ask about location (verifiers only, during a visit), camera, the phone
  number and the device ID. Answer from `/privacy`.

## Design

The app follows the "Afe App Screen" and "Afe Mobile App" canvases of the Claude Design project, with the
same tokens as the website (`frontend/src/app.css`):
- **Type:** Bricolage Grotesque for headings and figures, IBM Plex Sans for text, IBM Plex Mono for references
  and small labels. All three are bundled in `assets/fonts` (SIL Open Font License, licences beside the files).
- **Colours:** light and dark palettes in `lib/theme.dart` (`Afe` theme extension, read with `context.afe`).
- **Platform touches:** iOS gets a centred title, "‹ Back", 12 px buttons and pill chips; Android gets Material 3
  pill buttons, 8 px chips and 4 px fields. The numbers are the canvas's, in one place (`Afe.buttonRadius` etc.).
- **Navigation:** a start screen with numbered places for each role (renters and visitors, landlords and agents,
  field verifiers) and the same places in the ☰ drawer; the initials avatar goes back to it. Screens that end in
  one action (book, pay, release, send a report) keep it in a bar at the bottom.

Motion is kept to what tells you something:
- Buttons and cards press down to 0.97 in 160 ms with a strong ease-out.
- Photos fade in when they arrive.
- Switching places is instant, because you do that often.

Nothing runs longer than 300 ms, and all motion is off when the phone's "reduce motion" setting is on.
