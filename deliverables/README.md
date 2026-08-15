# Deliverables

| File | What it is |
| --- | --- |
| `system-prompt.pdf` | The full system message configuring the bot, including the pronunciation dictionary |
| `recordings/` | Recorded test calls, one folder per conversation flow |

## System prompt

`system-prompt.pdf` is generated from the same modules the running agent uses
(`server/app/prompts/`), so it is the live configuration rather than a
description of it. Regenerate after any prompt change:

```bash
cd server && uv run python -m scripts.export_prompt
```

It also writes the Markdown source to `docs/system-prompt.md`.

## Recordings

Each flow is a real outbound call placed through Plivo to a test number, with
the agent running the production pipeline. Every folder holds the call
recording, its transcript, and the qualification the extractor produced.

| Flow | What it demonstrates |
| --- | --- |
| `01-qualified-investor` | Happy path: permission, all four checkpoints, pitch, follow-up accepted |
| `02-self-use-buyer` | Weekend-home intent, budget fits, checkpoints answered out of order |
| `03-budget-mismatch` | Budget below entry price — graceful close without embarrassment |
| `04-location-objection` | Budget fits but Nandi Hills is too far: one gentle reframe, then acceptance |
| `05-irritated-caller` | Annoyed prospect: de-escalate once, then end the call politely |
| `06-hindi-speaker` | Caller switches to Hindi mid-call; agent continues in Hinglish |
| `07-busy-callback` | "Call me later" — agent takes a specific callback window and exits |

Recordings are produced once live provider credentials are in place; see
`docs/runbook.md` in `deploy/` for placing a test call.
