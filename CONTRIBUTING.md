# Contributing

Thanks for helping make diagrams prettier.

## Ground rules
- Scripts stay **standard library only** (Python 3.10+). The skill must run on a
  machine with nothing installed but Python.
- Every rule in `lint.py` needs a matching entry in
  `skills/prettier-excalidraw/references/style-guide.md` with the reason it exists.
- Keep `SKILL.md` under ~150 lines. Long material goes in `references/`.
- Example diagrams must be synthetic: no real hostnames, CIDRs, customer or
  project names.

## Labels
`size: S / M / L` says how big a change is (an afternoon, a few days, a week or
more); `area: *` says which part it touches (build, lint, fix, export, convert,
layout, skill, docs, ci, scripts). "good first issue" items have everything written
out: what, expected, where, how to test.

## Before you start on an issue
Comment on the issue (or assign yourself) before writing code, and check the
latest `main` first. Several of the first pull requests arrived on the same day the
issue was fixed on `main`, which wasted good work. Rebase on `main` before opening
the PR.

## Running the tests
```bash
python3 -m unittest discover -s tests -v
```
The tests build every spec in `assets/examples`, lint the result, and check that
`lint.py` catches deliberately broken files and `fix.py` repairs them.

When an intentional build change alters an example diagram, run
`python3 tests/test_golden.py --update` (use `python` on Windows) and review
the snapshot diffs before committing. Run it when adding an example spec too.

## Proposing a style change
Open an issue with a before/after PNG. Style rules were derived by measuring a
set of real diagrams, so a change should come with the same kind of evidence:
"this looks better" plus a picture, or "these N diagrams already do it this way".

## Adding an example
1. Write the spec, build it, lint it clean, render a preview.
2. Put `name.spec.json`, `name.excalidraw` and `name.png` in `assets/examples/`,
   icons in `assets/examples/icons/` (SVG from Simple Icons is fine, it is CC0).
3. Add it to the README table.

## Commit messages
Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.

## How to release
1. Move the `Unreleased` entries in `CHANGELOG.md` under a new `## [X.Y.Z] - YYYY-MM-DD`
   heading and set `"version"` to `X.Y.Z` in `.claude-plugin/plugin.json` and
   `.claude-plugin/marketplace.json` (both places in the latter).
2. `python3 tools/release_notes.py vX.Y.Z` must print the section and `release check ok`.
3. Commit, then `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin main vX.Y.Z`.
4. The `release` workflow runs the checks and tests again, zips the skill, and creates
   the GitHub release with that changelog section as its notes. To rehearse without
   releasing: Actions → release → Run workflow with the tag and `dry_run` on.
