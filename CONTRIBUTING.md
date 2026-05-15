# Contributing to llive

Thank you for your interest in contributing to llive. This document describes
how to submit changes and the legal terms governing your contributions.

## License

llive is dual-licensed:

  * Open source: Apache License, Version 2.0 (`LICENSE`)
  * Commercial: separate agreement (`LICENSE-COMMERCIAL`)

By submitting any contribution to this project, **you agree that your
contribution is licensed under Apache-2.0** and may also be relicensed
under the commercial license at the project owner's discretion.

## Developer Certificate of Origin (DCO)

llive uses the **Developer Certificate of Origin 1.1** instead of a CLA.
By signing off your commits, you certify that:

> 1. The contribution was created in whole or in part by you and you have
>    the right to submit it under the open source license indicated in the
>    file; or
>
> 2. The contribution is based upon previous work that, to the best of your
>    knowledge, is covered under an appropriate open source license and you
>    have the right under that license to submit that work with modifications,
>    whether created in whole or in part by you, under the same open source
>    license (unless you are permitted to submit under a different license),
>    as indicated in the file; or
>
> 3. The contribution was provided directly to you by some other person who
>    certified (1), (2) or (3) and you have not modified it.
>
> 4. You understand and agree that this project and the contribution are
>    public and that a record of the contribution (including all personal
>    information you submit with it, including your sign-off) is maintained
>    indefinitely and may be redistributed consistent with this project or
>    the open source license(s) involved.

The full text is at <https://developercertificate.org/>.

### How to sign off

Add the `Signed-off-by` trailer to every commit:

```
git commit -s -m "feat(foo): add bar"
```

This appends:

```
Signed-off-by: Your Name <you@example.com>
```

Configure your name and email if you have not already:

```
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## Pull request checklist

  * `py -3.11 -m pytest` passes (full suite)
  * `py -3.11 -m ruff check` passes
  * Each commit is signed off (`git commit -s`)
  * Commit message follows the project style:
    `<type>(<scope>): <short summary>` (e.g. `feat(approval): add policy gate`)
  * Update `docs/PROGRESS.md` and `CHANGELOG.md` for user-visible changes
  * Add tests for new functionality (we aim for >90% line coverage)

## Style

  * Python 3.11+, target `>=3.11,<3.12`
  * Type hints required for public API
  * Standard library preferred; external dependencies live in extras
  * Japanese is welcome in comments, docstrings, and documentation —
    the project is bilingual (ja / en)

## Security

Please **do not** open public issues for security vulnerabilities. See
`SECURITY.md` for the private disclosure process.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Be kind, be specific, assume good faith.

## Trademarks

"llive", "llmesh", and "llove" are trademarks of Kazufumi Furuse. See
`TRADEMARK.md` for usage guidelines. Contributors do not gain trademark
rights by contributing code.
