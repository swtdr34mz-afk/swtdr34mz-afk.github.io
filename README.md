# swtdr34mz — website

The homepage for the synth plugins and FM-1 mods by **swtdr34mz**.

- `index.html` — the whole page (styles and scripts inside)
- `img/` — logo and screenshots
- `tools/update_releases.py` — writes `releases.json` with the newest release of every project on the page
- `.github/workflows/pages.yml` — builds and publishes the site on every change and once an hour, so new releases show up by themselves

A new project needs a new card in `index.html` with `data-repo="REPO-NAME"`; its version is then filled in automatically.
