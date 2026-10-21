# Annotated routing demonstration

![Historical native check reconstructed as a readable evidence card: root Opus 5.5/high unchanged, unpinned worker Sonnet 5.5/medium, explicit Sonnet/high pin unchanged.](../assets/public/demo.png)

## What you are looking at

An **annotated reconstruction**, not a fresh recording, fake terminal, or a new
provider run. It visualizes the retained sanitized native Claude Code CLI report
from **2026-10-19**, host **2.1.303**, at repository revision `db7707c`.
The original internal report is privately preserved; its SHA256 and a deliberately
minimal public extraction are in [demo-evidence.json](../assets/public/demo-evidence.json).
Raw transcripts, machine paths, session/worker identifiers and private key/state
locations are not included. This extraction is a provenance receipt, not an
independently rerunnable replacement for the raw native observation.

## Text equivalent

| Case | Original request | Model argument after routing | Observed native child |
| --- | --- | --- | --- |
| Automatic | Generic assignment, no model/effort pin | `sonnet` | `claude-sonnet-5-5`, `medium` |
| Explicit pin | Sonnet / high | `sonnet`, preserved | `claude-sonnet-5-5`, `high` |

The observed root stayed `claude-opus-5-5` / `high` before and after both workers.
Nonrouting arguments and permission mode were preserved. A selected argument
alone would not establish effective execution; the historical report also
recorded native child observations. The explicit high-effort pin is **not** proof
of an automatically supported high-effort route.

## Limits

This is historical, narrowly scoped CLI evidence. It does not prove support for
the current installed binary, all models/efforts, desktop, managed environments,
implementation quality, lower costs or faster completion. There was no fresh
runtime activation, provider call or access to real-project transcripts for this
public artifact. The [configuration guide](configuration.md) explains why updates
can deliberately cause abstention.

## Editable source and reproduction

The [HTML source](../assets/public/demo.html) is the editable original of the card.
A browser screenshot of that HTML at **1120 × 720 CSS pixels**, scale factor 1,
produces `assets/public/demo.png`. For example, use an installed Chromium browser
with a disposable profile and no network dependencies:

```sh
chromium --headless --disable-gpu --hide-scrollbars --no-pdf-header-footer \
  --user-data-dir="$DISPOSABLE_PROFILE" --window-size=1120,720 \
  --force-device-scale-factor=1 --screenshot="$PWD/assets/public/demo.png" \
  "file://$PWD/assets/public/demo.html"
```

Set `DISPOSABLE_PROFILE` to a new temporary directory; do not point it at your
normal browser profile. The editable source contains the same labels as the
public evidence summary. Browser chrome/terminal content is not being simulated.
