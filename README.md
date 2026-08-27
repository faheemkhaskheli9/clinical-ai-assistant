# Clinical AI Conversational Assistant

> LLM, RAG & Agentic AI portfolio project — independent open-source implementation.
> This is an original, from-scratch build. It is not affiliated with, and does not
> contain any code, prompts, data, or business logic from, any employer or client.

![status](https://img.shields.io/badge/status-in--progress-yellow)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

## 1. Problem

Clinicians and patients need a conversational system that can intake patient history, ask smart follow-up questions, extract structured clinical data, and produce a doctor-facing summary — without a human manually re-typing notes.

## 2. Architecture

```text
Patient Chat -> Structured Extraction -> Clinical Reasoning (RAG + LLM) -> Doctor Summary -> Review UI
```

## 3. Technology Stack

- Python
- FastAPI or Django
- React or Streamlit
- OpenAI / Azure OpenAI API
- PostgreSQL
- Docker

## 4. Feature List

- Patient conversational intake (chat-based)
- Medical history collection with guided prompts
- Dynamic, context-aware follow-up questions
- Structured patient-information extraction (symptoms, vitals, history)
- Automatic conversation summarization
- Doctor-facing clinical summary generation
- Treatment / lifestyle / diagnostic recommendation modules
- Tool calling for structured actions (e.g., schedule follow-up, flag urgency)
- RAG integration over medical reference material
- Separate patient and doctor interfaces

## 5. Implementation Plan

1. Phase 1: Define conversation schema and structured-extraction JSON contract
2. Phase 2: Build patient chat intake flow with dynamic follow-up question logic
3. Phase 3: Implement extraction pipeline (LLM function calling) into structured records
4. Phase 4: Add RAG layer over public medical reference datasets for recommendations
5. Phase 5: Build doctor-facing dashboard for summaries and review
6. Phase 6: Add evaluation harness for extraction accuracy and summary quality

## Task Tracking

Work is broken into phase-tagged user stories tracked as GitHub Issues, not in this file. To see what's open:

    gh issue list --repo faheemkhaskheli9/clinical-ai-assistant --state open --label type:user-story

Implement Phase 1 issues first (later phases depend on it). When you start one, add label `status:in-progress`. When you finish, close it referencing the commit (e.g. `git commit -m "... Closes #4"`) and push.

## 6. Repository Structure

```text
clinical-ai-assistant/
├── README.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── .env.example
├── docker/
├── docs/
│   ├── architecture.md
│   └── evaluation.md
├── src/
├── tests/
├── configs/
├── scripts/
├── notebooks/
├── examples/
├── assets/
└── .github/
    └── workflows/
```

## 7. Setup

```bash
git clone <this-repo-url>
cd clinical-ai-assistant
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # or: pip install -e .
cp .env.example .env              # fill in API keys / config
```

## 8. Dataset

The RAG reference corpus (Phase 4) is pulled live from three public/government
sources via `scripts/ingest.py` — nothing is committed to the repo, only
fetched and cached locally under `data/` (gitignored):

| Source | Content | License |
|---|---|---|
| [MedlinePlus](https://medlineplus.gov/) Health Topics (wsearch API) | Disease/condition overviews | Public domain (US NLM) |
| [openFDA](https://open.fda.gov/) Drug Label API | Indications, dosage, contraindications, warnings, interactions | Public domain (US FDA) |
| [MedQuAD](https://github.com/abachaa/MedQuAD) | ~47k medical Q&A pairs (excl. 3 copyright-stripped MedlinePlus subsets) | CC BY 4.0 |

Run `python scripts/ingest.py` (see §9) to (re)populate `data/processed/*.jsonl`.
Per-source options (seed terms, record limits, file caps) live in
`configs/ingest.yaml`. No proprietary, employer-owned, or client-identifiable
data is used in this project.

## 9. Training / Execution

Ingest the medical reference corpus (fetches online, caches locally):

```bash
python scripts/ingest.py                              # all sources, default config
python scripts/ingest.py --sources medlineplus,openfda # a subset
python scripts/ingest.py --config configs/ingest.yaml  # tune limits/seed terms
```

## 10. Evaluation

Document evaluation metrics and how to reproduce them here (see `docs/evaluation.md`).

## 11. Results

_To be filled in as the implementation progresses — screenshots, metrics tables, and
sample outputs go here._

## 12. API

_If this project exposes an API, document the main endpoints here (or link to
auto-generated OpenAPI docs, e.g. `/docs` for FastAPI)._

## 13. Docker

```bash
docker build -t clinical-ai-assistant .
docker run -p 8000:8000 clinical-ai-assistant
```

## 14. Tests

```bash
pytest tests/
```

## 15. Limitations

- This is a from-scratch, independent recreation built for portfolio purposes.
- Performance numbers, once added, are based on public datasets and are not
  representative of any production system's real-world results.

## 16. Future Work

- Expand evaluation coverage and add CI-based regression checks.
- Add more configuration presets and deployment targets.
- Track open items as GitHub Issues.

## 17. Disclosure

This repository is an **independent open-source recreation inspired by the kind of
production systems I have worked on professionally**. It contains no employer or
client source code, prompts, datasets, credentials, architecture diagrams, or
business logic. All code, data, and documentation here are original or built on
publicly available datasets and open-source tools.

---
_Last updated: 2026-08-18_
