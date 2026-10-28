# Merge notes

This repository merges three archives:

| Source | What it was | What happened to it |
| :-- | :-- | :-- |
| `mastermind-library-bot` | Cleaned, restructured bot (no hardcoded IDs/keys, tests, Dockerfile, `/convert`) | **Base of this repo**, taken as-is, then extended |
| `mastermind-main` | Older version of the same bot | Fully diffed against the base (51 shared files). Every difference is already improved in the base (secrets removed, owner/IDs from env, quota bonuses from config, masked config output, patches moved to `modules/utility/telegram_patches.py`, dead Audible/Goodreads helpers removed). Nothing needed to be carried over |
| `ebook_converter_module` | Standalone Calibre/Pandoc/KFX/PDF converter + a Telethon handler | Engine **merged into `modules/converter`**; Telethon handler kept as an optional adapter |

## What changed in `modules/converter`
* `formats.py`: 61 input / 31 output formats, Pandoc maps, routing (`backend_for`, `output_choices`).
* `engine.py`: one pipeline with Calibre + Pandoc + KFX plugins + PDF text extraction (PyMuPDF) +
  legacy Office via Anydoc + RTL EPUB patching. Keeps the base engine's hardening (process-group kill,
  output validation, concurrency limiter, safe names).
* `handlers.py`: buttons are filtered by what the host can actually do; new **Force RTL** toggle.
* `telethon_adapter.py` + `examples/`: the standalone Telethon handler, adapted to the new engine
  (private temp dirs instead of a shared `/tmp` folder, random hex request ids).
* Config: `convert_kfx_enabled`. Dockerfile now installs Pandoc and `requirements-converter.txt`.

## Deliberately left out
* `mastermind-main/env.txt` - it contained **real credentials** (Telegram bot token, Render API key).
  Rotate them (BotFather `/revoke`, Render dashboard) and make sure they are not in git history.
* `mastermind-main/mastermind_all_commits.zip` and `FETCH_HEAD` - git history artefacts. The zip holds a
  `.git` folder that likely contains the same secrets in old commits.
* Termux-specific `push_sync.sh` (force-push + hardcoded upstream) - the base's `scripts/push_sync.sh` is used.
* Shamela `.bok` input: the standalone module imported `bok_helper`, which was not in the archive.
* `--pdf-no-cover` Calibre flag from the standalone module: could not be confirmed to exist, so PDF output
  uses Calibre defaults (`--filter-css float` for DOCX is kept).

## Verified / not verified
* Verified: 32 tests pass (1 skipped: PDF extraction needs PyMuPDF); all 55 modules import; Pandoc route run
  end-to-end with a real Pandoc binary.
* Not verifiable in the build sandbox (PyPI and Calibre unavailable): the live Telegram bot with
  python-telegram-bot installed (Telegram/aiohttp were stubbed for import checks), Calibre routes
  (tested with a fake `ebook-convert`), PyMuPDF, Anydoc, KFX plugins, the Telethon adapter at runtime.
