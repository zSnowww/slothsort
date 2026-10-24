# DEV Challenge — SlothSort for Telegram

The [published DEV entry](https://dev.to/zsnowww/slothsort-gemma-proposes-telegram-folders-i-approve-the-changes-229k) is the final version. This file preserves an earlier draft of the project story.

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19).*

## What I Built

SlothSort is a local-first assistant for organizing Telegram chats into Telegram's own chat folders. It reads a limited amount of context, asks an open-weight model to propose groupings, and shows every chat and its estimated confidence before anything changes. Uncertain chats start unassigned. I can rename folders, move chats, or leave them out; only an explicit approval creates folders through MTProto. The latest creation can be undone if the folders have not changed since.

The lazy payoff is avoiding the repetitive job of sorting chats one by one while keeping the final decision in the user's hands. I have not measured a reliable time-saved figure yet.

## Demo

Video: https://raw.githubusercontent.com/zSnowww/slothsort/051f9b9901c896f05d8d672224cd61dbdae9cec5/docs/demo.mp4

This 16-second recording uses invented chats, a proposal previously computed by Gemma 3 4B running locally, and a simulated Telegram adapter. The CPU inference wait was omitted, but the manual corrections, simulated folder creation, and undo were recorded live. No real Telegram account is shown or modified.

## Code

Repository: https://github.com/zSnowww/slothsort

The README includes setup, a synthetic-data demo, privacy notes, tests, and an architecture overview. Telegram API credentials and session files are excluded from Git.

## How I Built It

Gemma 3 4B runs locally through Ollama and is the default classification engine. Python, FastAPI and Telethon connect to Telegram through MTProto; the browser provides the review and approval flow. Users can analyze metadata alone, add group/channel descriptions, or sample 5, 10 or 20 recent text messages per chat. Private messages are not sampled by the initial UI selection. Optional Agy, Codex and OpenCode CLI adapters are available with explicit consent because they may use remote providers; these adapters are experimental and have been tested with simulated subprocesses.

```text
Telegram --MTProto--> FastAPI --bounded context--> Gemma 3 via Ollama
                         |                          |
                         +<------ folder proposal --+
                         |
                         +--> review in browser --> explicit approval --> Telegram folders
                                                           |
                                                           +--> guarded undo
```

The model never sends Telegram API requests. The server validates chat identifiers against the fetched snapshot, prevents duplicate assignments, and does not automatically select low-confidence suggestions. Automated tests run without connecting to a real account.

## Why Does Open Innovation Matter?

Gemma and Ollama let the default classification flow run on my own machine instead of sending chat contents to a closed hosted API. I can swap the model, inspect the prompt, and change the decision thresholds. The important tradeoff is transparency: local inference can be slower on CPU, and a short message sample can miss the usual topic of a chat. SlothSort exposes those choices rather than pretending every prediction is certain.

## Prize Categories

**Best Use of Gemma** — Gemma 3 4B powers the default folder classification.
