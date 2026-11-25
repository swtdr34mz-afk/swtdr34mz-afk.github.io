# swtdr34mz — website

The homepage for the synth plugins and FM-1 mods by **swtdr34mz**.

- `index.html` — the whole page (styles and scripts inside)
- `img/` — logo and screenshots
- `tools/update_releases.py` — writes `releases.json` with the newest release of every project on the page
- `.github/workflows/pages.yml` — builds and publishes the site on every change and once an hour, so new releases show up by themselves

A new project needs a new card in `index.html` with `data-repo="REPO-NAME"`; its version is then filled in automatically.

## Discord announcements

After every deploy, `tools/announce.py` compares the releases the site showed before with the new ones and posts each
new release in the **#announcements** channel of its area (the card's section: VST, MPC, FM-1 mods). A project that
was not on the page before is announced as a new instrument. The channels are Discord webhooks in the repository
secrets `DISCORD_WEBHOOK_VST`, `DISCORD_WEBHOOK_MPC`, `DISCORD_WEBHOOK_FM1`. To post a release again by hand:
Actions → "Update website" → Run workflow, and type the repo name (e.g. `RAND`).
