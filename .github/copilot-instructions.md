# Copilot instructions — azure-openai-sora-2-webserver

> Canonical standards live in the `dev-standards` repo on SOUNDWAVE/Gitea.
> Read by Copilot chat **and** inline suggestions.

## What this repo is

A standalone **Dockerised Python web server** fronting Azure OpenAI's Sora 2
(video generation). Not a Home Assistant component.

## Repo shape

- `app/` — the web application.
- `static/` — front-end assets.
- `tests/` — test suite.
- `Dockerfile`, `entrypoint.sh`, `pyproject.toml`, `requirements.txt`.

## Conventions

- Python web service: no `manifest.json`/`hassfest`/HACS.
- Config via env / Azure credentials — **never commit Azure OpenAI keys or
  endpoints**; use env vars / a gitignored config.
- Ship changes as a rebuilt Docker image.

## Never

- Don't commit Azure API keys, endpoints, or secrets.
