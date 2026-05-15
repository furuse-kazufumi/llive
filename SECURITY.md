# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report privately via one of:

  * **GitHub Security Advisories** — preferred. Open the repository's
    "Security" tab and click "Report a vulnerability". This creates a
    private channel between you and the maintainer.
  * **Email** — `kazufumi@furuse.work` with the subject line prefix
    `[llive security]`.

Include in your report:

  * A description of the vulnerability and its impact
  * Steps to reproduce (proof-of-concept code is welcome)
  * The version(s) of llive affected
  * Any suggested mitigation, if you have one

## Disclosure timeline

  * **Acknowledgement**: within 5 business days
  * **Triage**: within 15 business days (we will share severity assessment)
  * **Fix**: target 30 days from acknowledgement for High/Critical findings;
    Medium/Low findings are batched into the next minor release
  * **Public disclosure**: coordinated with the reporter; default 90 days
    from acknowledgement or upon fix release, whichever is sooner

We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure):
please give us reasonable time to ship a fix before public disclosure.

## Supported versions

llive is pre-1.0 software. Only the latest **minor** version receives
security fixes. Older versions should be upgraded:

| Version | Supported |
|--------:|:---------:|
| 0.5.x   | ✅        |
| 0.6.x   | ✅ (current) |
| < 0.5   | ❌        |

## Scope

The following are in scope:

  * The `llive` Python package and CLIs
  * The MCP server (`src/llive/mcp/server.py`)
  * The OpenAI-compatible HTTP server (`src/llive/server/openai_api.py`)
  * The Approval Bus and persistent ledger (`src/llive/approval/`)
  * The FullSense Sandbox and Production output buses

The following are **out of scope** (file an upstream issue instead):

  * Vulnerabilities in third-party dependencies (`pip-audit` is your friend)
  * Issues in user-supplied corpora under `data/rad/` (these are not
    distributed by us)
  * Issues that require physical access to the host machine

## Bounty

llive does not currently offer a paid bug bounty. Reporters of valid
security findings are credited in the release notes (with their consent)
and in `THANKS.md`.

## See also

  * `LICENSE` — Apache-2.0 disclaimer of warranty (Section 7)
  * `NOTICE` — copyright and attribution
  * `CONTRIBUTING.md` — pull-request workflow
