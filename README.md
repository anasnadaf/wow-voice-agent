# WOW Voice Agent

Outbound AI voice agent that qualifies leads for Divyasree's **Whispers of the Wind** villa-plot
project (Nandi Valley, North Bengaluru) over a real phone call — permission-first intro, four
qualification checkpoints (intent, geography, budget, timeline), an aspirational pitch, and a
follow-up CTA, in English or Hindi, inside 2–3 minutes.

## How it works

A visitor requests a call from the web page (or an agent triggers one from the dashboard). The
server originates the call through Plivo and bridges the phone audio over a websocket into a
Pipecat pipeline — Sarvam STT → a LangGraph conversation graph driven by a fast LLM (Groq) →
Sarvam TTS — while recording audio and streaming metrics. After hangup, a DSPy extractor turns the
transcript into a structured qualification record, and the whole call (latency metrics, transcript,
audio, extraction) lands in MLflow. The dashboard shows leads, live call status, transcripts,
recordings, and the four-checkpoint qualification card.

Every vendor sits behind an adapter selected by env config: STT/TTS Sarvam ⇄ Gnani, LLM Groq ⇄
Cerebras, telephony Plivo ⇄ (Exotel/Twilio serializers ship with Pipecat).

The conversation follows a fixed architecture — permission-first introduction,
four qualification checkpoints (intent, geography, budget, timeline), an
aspirational pitch, and a Property Expert follow-up — while handling the calls
that don't go to plan: irritated prospects, busy ones, wrong numbers, budget
mismatches, location objections, and do-not-call requests. Checkpoints answered
early are never asked again.

## Layout

```
server/   FastAPI + Pipecat + LangGraph + DSPy (Python 3.12, uv)
web/      Next.js dashboard + public request-a-call page
deploy/   production compose stack, nginx, EC2 provisioning, runbook
docs/     architecture, system prompt (Markdown source of the PDF)
deliverables/  recorded demo call flows + system-prompt.pdf
```

[`docs/architecture.md`](docs/architecture.md) has the call diagram and the
reasoning behind the structure.

## Development

```bash
docker compose -f compose.dev.yml up -d   # postgres + mlflow
cd server && uv sync && uv run uvicorn app.main:app --reload --port 8080
cd web && npm install && npm run dev
```

Copy `server/.env.example` to `server/.env` and fill in provider keys. See `docs/` for
architecture and `deploy/` for production.
