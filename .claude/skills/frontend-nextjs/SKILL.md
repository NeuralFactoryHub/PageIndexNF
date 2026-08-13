---
name: frontend-nextjs
description: Use when implementing frontend features with Next.js 14 (App Router), React 18, Tailwind CSS, and shadcn/ui.
---

# Frontend Next.js Development

## Overview

This skill provides guidance for frontend development with Next.js 14
(App Router), React 18, Tailwind CSS, and shadcn/ui (Radix primitives).

The skill is intentionally stack-only — it does NOT assume a specific
domain or application architecture. Project-specific conventions
(component organization, state management approach, naming patterns)
should live in the project's own `CLAUDE.md` or in `.claude/project.yml`.

**Announce at start:** "I'm using the frontend-nextjs skill for this implementation."

## When to Use

- Creating or modifying React components or pages in a Next.js 14 app
- Adding or customizing shadcn/ui components
- Styling with Tailwind CSS
- Working in the App Router (`app/` directory)

## Core Workflow

### Step 1: Understand Project Context

Before implementing, read:

1. `CLAUDE.md` at the project root for project-specific conventions
2. `.claude/project.yml` for declared services and dependencies
3. Existing components in the project to identify the prevailing patterns (state management, file organization, naming)
4. The reference files in this skill for stack-level patterns

### Step 2: Follow Existing Patterns

Reference files:

- `references/tailwind-shadcn-patterns.md` — Styling conventions, shadcn/ui usage

### Step 3: Implement

Follow the project's established order. A common pattern (verify against the project):

1. **Domain or business logic** — pure functions in `lib/`
2. **Components** — UI components with Tailwind + shadcn/ui
3. **State wiring** — hook components into the project's state management approach
4. **Routes / pages** — wire components into the App Router

### Step 4: Verify

```bash
npm run lint
npm run build
```

## Stack-Level Conventions

These apply to any Next.js 14 + Tailwind + shadcn/ui project:

- **App Router** — pages live in `app/`, server components are the default, mark client components with `'use client'`
- **Tailwind only** — no CSS modules, no styled-components, no inline styles unless dynamic
- **shadcn/ui** — Radix primitives, copied into the project (not installed as a package), customizable per project
- **lucide-react** — standard icon library
- **`@/*` path alias** — maps to the project root (configured in `tsconfig.json`)
- **TypeScript or JSX** — depends on the project; check existing files before deciding

## Project-Specific Information

This skill does NOT hardcode project-specific information (file tree, domain
entities, naming conventions). For those, the engineer must consult:

- The target project's `CLAUDE.md`
- `.claude/project.yml` → `services[]` for the relevant frontend service
- Existing components and conventions in the codebase
