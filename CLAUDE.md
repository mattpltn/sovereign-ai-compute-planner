# Maintenance rules for this repository

These rules apply to every change, by a person or an AI assistant.

1. **Methodology stays in sync.** Any change to formulas (`engine/`), defaults or application types (`data/catalogue/`), hardware, placement or sources must update `docs/methodology_text.md` where the text describes it, then regenerate:
   `python docs/build_methodology.py`
   Never edit `docs/METHODOLOGY.md` by hand. CI runs `python docs/build_methodology.py --check` and fails if it is stale.
2. **Changelog.** Add an entry under `[Unreleased]` in `CHANGELOG.md` for every user-visible change (Added / Changed / Fixed / Removed). When a version is released, move the entries under a new version heading with the date.
3. **Every default needs a source.** New values in `data/catalogue/*.yaml` carry a source ID from `sources.yaml` or are explicitly marked as an assumption with a confidence level.
4. **Excel parity.** `tests/fixtures/use_cases_v01.yaml` reproduces the Excel reference; do not change it. Run `python -m pytest -q` before pushing.
5. **Branches.** Work on a branch and open a pull request into `main`; `main` deploys to GitHub Pages.
6. **Clearance.** The repository is a private draft until World Bank clearance. Do not make it public or add a licence without that.
