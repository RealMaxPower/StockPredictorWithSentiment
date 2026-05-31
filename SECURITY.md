# Security Policy

`stockpredictor` is an **educational** project that forecasts historical prices and
contextualizes them with news sentiment. It is **not financial advice**, and it is
designed to run **locally** (CLI or the Streamlit dashboard) against public data
sources. It does not host a server, store user accounts, or process payments. Please
keep that threat model in mind when assessing impact.

We still take security seriously and welcome reports.

## Supported Versions

Security fixes are applied to the latest release and the `main` branch. Older
tagged versions do not receive backported fixes.

| Version        | Supported |
| -------------- | --------- |
| `main` (latest) | ✅        |
| `0.2.x`        | ✅        |
| `< 0.2`        | ❌        |

## Reporting a Vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's coordinated-disclosure channel:

1. Go to the repository's **Security** tab →
   **[Report a vulnerability](https://github.com/RealMaxPower/StockPredictorWithSentiment/security/advisories/new)**.
2. This opens a private advisory visible only to you and the maintainers.

If you cannot use GitHub Security Advisories, email the maintainer privately at
**<contactme@marshallcahill.com>** with the details. As a last resort, open a regular
issue that contains **only** "I would like to report a security issue, please advise
on a private channel" — with no technical detail — and a maintainer will follow up.

When reporting, please include where practical:

- A description of the issue and its impact.
- Steps to reproduce (a ticker string, input, config, or command line).
- The affected file/function and version or commit SHA.
- Any suggested remediation.

### What to expect

- **Acknowledgement:** within 5 business days.
- **Assessment & triage:** we aim to confirm or dismiss within 10 business days.
- **Fix & disclosure:** coordinated with you. We prefer to publish a fix before
  public disclosure and will credit you in the advisory unless you ask otherwise.

## Scope

**In scope** — the code in this repository:

- The `stockpredictor` package (`data`, `forecast`, `sentiment`, `news`,
  `pipeline`, `store`, `plotting`, `cli`, `sanitize`).
- The Streamlit dashboard ([`app.py`](app.py)).
- The CLI entry points and the SQLite store ([`store.py`](stockpredictor/store.py)).

**Out of scope:**

- Vulnerabilities in third-party data providers (NewsAPI, Yahoo Finance / `yfinance`)
  or any external service this project merely calls.
- Advisories in transitive dependencies that have no project-level remedy on our
  supported Python versions. The CI `audit` job in
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs `pip-audit` and reports
  these on every build. If you find a transitive advisory that *is* fixable for us, a
  report or PR bumping the floor is welcome.
- Misuse of your own credentials (see **Secrets** below).
- The forecasts themselves. Outputs are illustrative and explicitly **not financial
  advice**; inaccurate predictions are not security issues.

## Secrets

- The only secret this project uses is an optional `NEWSAPI_KEY`. It is read from the
  environment (or `.streamlit/secrets.toml` for the dashboard) — never hard-coded.
- `.env` and `.env.local` are git-ignored; copy [`.env.example`](.env.example) to
  `.env` and keep it out of version control. **Never commit an API key.**
- If you accidentally commit a key, rotate it at <https://newsapi.org> immediately;
  removing it from history alone is not sufficient once it has been pushed.

## Security posture

The project applies defense-in-depth appropriate to a local tool:

- **Input validation** — user-supplied ticker symbols are validated against a strict
  allow-list before they reach the filesystem, news queries, or the database
  ([`sanitize.py`](stockpredictor/sanitize.py)), preventing path traversal.
- **Output safety** — untrusted news titles and URLs rendered in the dashboard are
  markdown-escaped and restricted to `http(s)` links, blocking link/script injection.
- **Parameterized SQL** — every query in the SQLite store uses bound parameters; no
  string interpolation into SQL.
- **Dependency auditing** — `pip-audit` runs in CI on every push and pull request,
  surfacing known advisories in the dependency tree.

If you are running the dashboard somewhere other than your own machine, treat it as
an unauthenticated, internet-facing app: put it behind authentication and a reverse
proxy, since it issues outbound API calls on behalf of whoever can reach it.

## A note for security researchers

Because this is a local, single-user educational tool, please weigh real-world
impact before reporting. Findings that require an attacker to already control the
machine, the command line, or the database path are generally low severity — but if
you are unsure, report it and let us assess. We would rather hear about it.
