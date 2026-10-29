# End-user clients

ShopLens has a Next.js/TypeScript web client, a NestJS/TypeScript gateway, a SwiftUI iOS app and a Kotlin/Jetpack Compose Android app. These are end-user deal/search/chat clients, separate from the Dagster control plane.

All clients support product search, deal hunting, an optional target price, voucher/payment/membership/new-user eligibility, exact variant keys, checkout breakdowns, conditional offers, device-local saved deals, data-mode chat and a configured compatible model. Synthetic data is opt-in and labeled. Cashback is separate from today's payment; saved results are snapshots that need rechecking. No account, order placement, payment processing or personal recommendation profile is implemented.

## Design

Web uses an event-ticket/afterparty language: ink-dark poster hero, locally bundled Barlow Condensed display type, vermilion tickets, acid-lime print accents, perforated receipt cards and flat SVG graphics. Light paper surfaces keep financial details legible. There is no purple, Bootstrap, faux glass, luminous gradient or glossy card styling. Artwork is illustrative, not a product photo or live advertisement.

Native clients share only the brand accent and product concepts. iOS uses NavigationStack, TabView, List/Form, SF Symbols, native sheets and Dynamic Type. Android uses Material 3 navigation, Compose search/forms, bottom sheets, segmented choices and the system light/dark setting. They are native apps, not WebViews.

## Architecture and configuration

```
Next.js (3001) ── /api rewrites ── NestJS gateway (4100) ── platform API (8000)
iOS / Android ─────────────────── NestJS gateway (4100)
```

The gateway validates incoming requests with shared Zod contracts, exposes only known client operations, applies upstream timeouts and returns readable errors. Model keys remain on the platform server. Web calls are same-origin through Next's rewrite; native apps call the gateway directly. The service defaults are loopback-only development services, not an authenticated public deployment.

| Setting | Default | Where |
|---|---|---|
| `PLATFORM_API_URL` | `http://127.0.0.1:8000` | Nest gateway process; platform origin |
| `GATEWAY_PORT` | `4100` | Nest gateway process |
| `GATEWAY_HOST` | `127.0.0.1` | Set to an appropriate interface only for intentional device/LAN testing |
| `CLIENT_GATEWAY_URL` | `http://127.0.0.1:4100` | Next.js build-time rewrite configuration; rebuild after changing |
| iOS Connection setting | `http://127.0.0.1:4100` | Simulator; use a reachable server on a physical device |
| Android Connection setting | `http://10.0.2.2:4100` | Android emulator host alias; use a reachable server on a physical device |

The native Release configurations require HTTPS. Debug-only HTTP allowances support local development. No API keys should be embedded in native clients or public web environment variables. Add deployment authentication, rate limiting and TLS before exposing these services publicly.

## Web development

Requires Node 24/npm and the existing Python platform environment. From the repository root:

```bash
npm ci
npm run build
# Separate terminal / live process:
.venv/bin/vnecom ai serve --host 127.0.0.1 --port 8000
# Separate terminal / live process; starts gateway + Next dev server:
npm run dev
```

Root `predev` builds the shared contracts. Production commands are `npm run start -w @shoplens/gateway` and `npm run start -w @shoplens/web` after `npm run build`. The model remains optional; data-mode chat and deal arithmetic work without one. For an intentional synthetic demonstration, `.venv/bin/vnecom deals-demo` refreshes the demo catalog and refuses to replace non-synthetic offers.

Saved deals use browser local storage, iOS UserDefaults or Android private preferences. They are not synchronized across devices. Native connections can be changed from the settings button. Search eligibility is kept in view state rather than stored as a personal profile. Chat history lasts for the page/app session; it is not a durable server conversation service.

## Android

Open `apps/android` in Android Studio, use JDK 21 and install Android SDK platform 36/build-tools 36.0.0. Set your local SDK path in ignored `local.properties` or `ANDROID_HOME`.

```bash
cd apps/android
./gradlew :app:compileDebugKotlin
# Optional unsigned release package:
./gradlew :app:assembleRelease
```

The wrapper pins Gradle 8.13 and verifies the distribution checksum. Kotlin/Compose compilation and an unsigned release APK build were exercised on this cloud machine. Emulator/device interaction has not been exercised here. No app signing configuration or credentials are included.

## iOS

Open `apps/ios/ShopLens.xcodeproj` in Xcode 16 or newer. The shared ShopLens scheme targets iOS 17+ and includes iPhone/iPad. No signing identity or team is configured.

```bash
xcodebuild -project apps/ios/ShopLens.xcodeproj -scheme ShopLens \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO build
```

This Linux environment cannot compile SwiftUI or run an iOS simulator. Project/plist/scheme structure was checked, but that is not an Apple SDK build. The macOS job in `.github/workflows/clients.yml` performs the unsigned simulator build when CI runs; it has not been run from this environment.

## Verification

```bash
npm run build
npm run typecheck
# Once, install a Playwright browser (or use your installed Chromium):
npx playwright install chromium
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:clients
```

The smoke test needs the Python AI extra and unoccupied ports 8000, 4100 and 3001. It starts all three real services, uses isolated synthetic catalog/DuckDB/index fixtures, checks gateway validation, actual checkout totals, eligibility, saved persistence/removal, product discovery, chat, disabled model mode and desktop/mobile overflow, then stops only its owned processes. Screenshots/logs are written to ignored `artifacts/clients`. Omit `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to use Playwright's installed browser. These are client/contract checks, not live marketplace or live model validation.
