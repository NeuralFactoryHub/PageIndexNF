---
name: backend-python
description: Use when implementing backend features in Python FastAPI services. Covers FastAPI routes, Pydantic Settings, AWS Bedrock via litellm, LangFuse observability, async MongoDB with motor, and optional CrewAI Flow patterns.
---

# Backend Python Development

## Overview

This skill provides guidance for backend development.

> **On agent orchestration:** this skill includes patterns for CrewAI Flow
> in `references/crewai-flow-patterns.md`. CrewAI is an **optional**
> framework — apply those patterns only if the current project uses CrewAI.
> If the project uses a different framework (e.g. Claude Agent SDK),
> follow the project's CLAUDE.md and ignore the CrewAI references.

**Announce at start:** "I'm using the backend-python skill for this implementation."

## When to Use

- Creating/modifying FastAPI route handlers
- Working with CrewAI Flow phases (when the project uses CrewAI)
- Modifying Pydantic models or settings
- Integrating with AWS Bedrock (LLM or embeddings)
- Adding LangFuse observability
- Working with MongoDB via motor

## Core Workflow

### Step 1: Understand the Service

Before implementing, ALWAYS read:
1. The service's CLAUDE.md (if exists)
2. `app/config/settings.py` for available configuration
3. `app/models/schemas.py` (or `api_schemas.py`) for existing models
4. `app/utils/exceptions.py` for the exception hierarchy

### Step 2: Follow Existing Patterns

Reference files for detailed patterns:
- `references/fastapi-patterns.md` — Routes, DI, middleware, error handling
- `references/crewai-flow-patterns.md` — Flow phases, state, routers, events
- `references/pydantic-settings-patterns.md` — Settings, models, validation
- `references/bedrock-langfuse-patterns.md` — LLM calls, embeddings, tracing

### Step 3: Implement

Follow this order:
1. **Models first** — Pydantic schemas for request/response
2. **Service layer** — Business logic in `app/services/`
3. **Routes** — HTTP handlers in `app/api/routes.py`
4. **Configuration** — Add settings if needed
5. **Error handling** — Use existing exception hierarchy

### Step 4: Verify

```bash
python3 -m py_compile app/<modified_file>.py
```

## Key Conventions

- **Async everywhere**: All I/O operations must be async
- **Pydantic v2**: Use `model_config`, not `class Config`
- **Settings singleton**: `get_settings()` with `@lru_cache`
- **DI via Depends()**: Services injected from `app.state` set in lifespan
- **LangFuse `@observe`**: Decorate all service methods for tracing
- **Exception hierarchy**: Extend from service base exception
- **Motor for MongoDB**: Use `AsyncIOMotorClient`, not `MongoClient`

## Related Skills

| Skill | When to Use |
|-------|-------------|
| `@backend-nextjs` | When the service is built on Node/TypeScript instead of Python |
