# Architecture Notes: Clinical AI Conversational Assistant

## Pipeline

```text
Patient Chat -> Structured Extraction -> Clinical Reasoning (RAG + LLM) -> Doctor Summary -> Review UI
```

## Components

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

## Design Notes

- Keep provider/model choices swappable behind interfaces (see `multi-llm-router`
  and similar projects in this portfolio for the general pattern).
- Prefer configuration-driven pipelines (YAML/JSON in `configs/`) over hardcoded
  parameters so experiments are reproducible.

## Data ingestion (`src/rag/`, Phase 4)

`scripts/ingest.py` fetches the RAG reference corpus from three public
sources (MedlinePlus, openFDA, MedQuAD — see README §8) and normalizes every
record into one common `SourceDocument` schema (`src/rag/schema.py`) before
writing it to `data/processed/<source>.jsonl`. Raw responses are cached
under `data/raw/` so re-running ingestion is cheap. Chunking, embedding, and
vector-store loading (turning these JSONL files into a queryable retriever)
are not built yet — that's the next slice of Phase 4, feeding into issue #13
(grounded recommendations with citations).
