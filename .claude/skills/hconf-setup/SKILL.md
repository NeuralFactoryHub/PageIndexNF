---
name: hconf-setup
description: Use when setting up h-conf (hierarchical configuration) in a project. Covers installation, environment setup, wrapper creation, and usage patterns for NextJS applications.
---

# H-Conf Setup and Usage

## Overview

Guide for integrating `@neuralfactoryhub/h-conf-client` into a project. H-conf provides hierarchical configuration management with ROOT → COMPANY → USER levels.

**Announce at start:** "I'm using the hconf-setup skill."

## When to Use

- Setting up h-conf in a new project
- Creating h-conf wrapper/helper functions
- Implementing hierarchical config patterns
- Troubleshooting h-conf issues

## Related Skills

- **@backend-nextjs** - Use for API route patterns, Zod validation, error handling when building h-conf endpoints

## Key Concepts

### Hierarchical Structure

```
ROOT    → Default config (no companyId)
COMPANY → Override per company (companyId)
USER    → Override per user (companyId + userId)
```

### Cascade Behavior (Critical)

`getConfig` returns **cascaded** values: user overrides company overrides root.

- `getConfig(key)` → returns root value
- `getConfig(key, companyId)` → returns company value if exists, else root
- `getConfig(key, companyId, userId)` → returns user value if exists, else company, else root
- **If ROOT doesn't exist, returns undefined/404 even if company/user docs exist**

### API Signatures

```typescript
createConfig(config, companyId?, userId?)     // Always inserts new doc at specified level
getConfig(key, companyId?, userId?)            // Cascading read (user > company > root)
updateConfig(key, config, companyId?, userId?) // Targets specific level (findOneAndUpdate)
deleteConfig(key, companyId?, userId?)         // Deletes at specific level
```

**Key differences:**
- `getConfig` **cascades** — returns parent data even if target level doc doesn't exist
- `updateConfig` targets **exact level** — 404 if that level's doc doesn't exist
- `createConfig` **doesn't require parents** — but getConfig won't find orphaned docs without root

### Server-Side Only

H-conf calls must happen server-side (API routes). Client components must use API proxy to avoid CORS issues.

## Setup Steps

### Step 1: Install Package

Requires GitHub Packages authentication:

```bash
# Create .npmrc in project root
echo "@neuralfactoryhub:registry=https://npm.pkg.github.com" >> .npmrc
echo "//npm.pkg.github.com/:_authToken=YOUR_GITHUB_TOKEN" >> .npmrc

# Add to .gitignore
echo ".npmrc" >> .gitignore

# Install
npm install @neuralfactoryhub/h-conf-client
```

### Step 2: Environment Variables

**IMPORTANT:** Do NOT use `NEXT_PUBLIC_` prefix - API key must stay server-side.

```bash
# .env.local
HCONF_API_KEY=your-api-key
HCONF_URL=https://3oce6d6ufvig63lbv45xylpci40cqupn.lambda-url.eu-west-1.on.aws  # or dev URL
```

For serverless deployment (e.g., AWS Lambda), add to `serverless.yml`:

```yaml
functions:
  api:
    environment:
      HCONF_API_KEY: ${ssm:/path/to/HCONF_API_KEY}
      HCONF_URL: ${ssm:/path/to/HCONF_URL}
```

### Step 3: Create Wrapper (lib/hconf.ts)

```typescript
import { HConfClient } from '@neuralfactoryhub/h-conf-client';

const apiKey = process.env.HCONF_API_KEY;
const baseUrl = process.env.HCONF_URL;

if (!apiKey) {
  console.warn('HCONF_API_KEY not set');
}

export const hconfClient = new HConfClient(apiKey || '', baseUrl);

// --- 404 detection (hconf client throws AxiosError with status) ---

function isHconf404(error: unknown): boolean {
  return error instanceof Error && 'status' in error && (error as { status: number }).status === 404;
}

// --- Hierarchy helpers ---

async function tryCreateLevel(
  key: string,
  defaultValue: unknown,
  companyId?: string,
  userId?: string
): Promise<void> {
  const payload = { key, value: defaultValue, description: `Auto-initialized ${key}` };
  try {
    if (userId) {
      await hconfClient.createConfig(payload, companyId!, userId);
    } else if (companyId) {
      await hconfClient.createConfig(payload, companyId);
    } else {
      await hconfClient.createConfig(payload);
    }
  } catch {
    // Already exists or concurrent creation — swallow
  }
}

/**
 * Ensures all hierarchy levels exist for a given key.
 * Uses one getConfig at target level to check root existence,
 * then always tries createConfig at each needed level.
 *
 * DO NOT use getConfig per-level to check existence —
 * getConfig cascades and returns parent data even when
 * the target level doc doesn't exist.
 */
export async function ensureHconfHierarchy(
  key: string,
  defaultValue: unknown,
  companyId?: string,
  userId?: string
): Promise<void> {
  let needsRoot = false;
  try {
    if (userId) {
      await hconfClient.getConfig(key, companyId!, userId);
    } else if (companyId) {
      await hconfClient.getConfig(key, companyId);
    } else {
      await hconfClient.getConfig(key);
    }
  } catch (error: unknown) {
    if (isHconf404(error)) {
      needsRoot = true;
    } else {
      throw error;
    }
  }

  if (needsRoot) {
    await tryCreateLevel(key, defaultValue);
  }

  // Always try target levels (can't distinguish cascade from actual existence)
  if (companyId) {
    await tryCreateLevel(key, defaultValue, companyId);
  }
  if (companyId && userId) {
    await tryCreateLevel(key, defaultValue, companyId, userId);
  }
}

// --- CRUD helpers ---

// Define your config types
export interface MyConfigData {
  // your fields here
  createdAt: string;
  lastModified: string;
}

// Helper for consistent keys
export function getConfigKey(id: string): string {
  return `my-config-${id}`;
}

// GET config
export async function getMyConfig(
  id: string,
  companyId: string
): Promise<MyConfigData | null> {
  try {
    const config = await hconfClient.getConfig(getConfigKey(id), companyId);
    return config?.value as MyConfigData | null;
  } catch (error) {
    if (isHconf404(error)) {
      // Initialize hierarchy so future reads work
      await ensureHconfHierarchy(getConfigKey(id), {}, companyId);
      return null;
    }
    console.error('Error fetching config:', error);
    return null;
  }
}

// UPDATE config (with auto-create on 404)
export async function updateMyConfig(
  id: string,
  companyId: string,
  data: MyConfigData
): Promise<void> {
  const key = getConfigKey(id);
  const payload = { key, value: data, description: `Config for ${id}` };

  try {
    await hconfClient.updateConfig(key, payload, companyId);
  } catch (error: unknown) {
    if (isHconf404(error)) {
      // Ensure hierarchy, then create with actual data
      await ensureHconfHierarchy(key, {}, companyId);
      await hconfClient.createConfig(payload, companyId);
    } else {
      throw error;
    }
  }
}

// DELETE config
export async function deleteMyConfig(id: string, companyId: string): Promise<void> {
  await hconfClient.deleteConfig(getConfigKey(id), companyId);
}

// BATCH fetch (avoid N+1)
export async function getConfigBatch(
  ids: string[],
  companyId: string
): Promise<Map<string, MyConfigData | null>> {
  const results = new Map<string, MyConfigData | null>();

  const promises = ids.map(async (id) => {
    const config = await getMyConfig(id, companyId);
    return { id, config };
  });

  const resolved = await Promise.all(promises);
  for (const { id, config } of resolved) {
    results.set(id, config);
  }

  return results;
}
```

### Step 4: Create API Proxy (for client access)

> **Tip:** For advanced API patterns (Zod validation, error handling), see **@backend-nextjs**

```typescript
// app/api/config/me/route.ts
import { NextResponse } from 'next/server';
import { getMyConfig } from '@/lib/hconf';
import { getCurrentUser } from '@/lib/auth'; // your auth helper

export async function GET() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 });
    }

    const config = await getMyConfig(user.id, user.companyId);
    return NextResponse.json({ success: true, data: config });
  } catch (error) {
    return NextResponse.json({ success: false, error: 'Failed to fetch' }, { status: 500 });
  }
}
```

## Common Patterns

### Pattern: Lazy hierarchy init (recommended)

Use `ensureHconfHierarchy` instead of eagerly creating at all levels. This handles the case where parent levels may or may not exist:

```typescript
// On read: if 404, init hierarchy and return default
try {
  const config = await hconfClient.getConfig(key, companyId);
  return config?.value;
} catch (error) {
  if (isHconf404(error)) {
    await ensureHconfHierarchy(key, defaultValue, companyId);
    return defaultValue;
  }
  throw error;
}

// On write: if 404, init hierarchy then createConfig with actual data
try {
  await hconfClient.updateConfig(key, payload, companyId);
} catch (error) {
  if (isHconf404(error)) {
    await ensureHconfHierarchy(key, emptyDefault, companyId);
    await hconfClient.createConfig(payload, companyId);
  } else {
    throw error;
  }
}
```

### Pattern: Batch fetch in list endpoints

```typescript
// Instead of N+1:
// for (const item of items) { await getMyConfig(item.id) }

// Use batch:
const configMap = await getConfigBatch(items.map(i => i.id), companyId);
const enrichedItems = items.map(item => ({
  ...item,
  config: configMap.get(item.id),
}));
```

## Gotchas

1. **getConfig cascades**: `getConfig(key, companyId)` returns root data even if company doc doesn't exist. **Never use getConfig per-level to check if a specific level's doc exists.**
2. **updateConfig does NOT cascade**: It targets the exact level. 404 if that level's doc is missing.
3. **createConfig doesn't require parents**: You can create company without root — but getConfig won't find it without root.
4. **On 404 from updateConfig, use createConfig**: Don't retry updateConfig after hierarchy init — use createConfig with actual data at the target level.
5. **AxiosError shape**: hconf client throws AxiosError with `error.status` (not `error.response.status`). Check with `isHconf404`.
6. **No unique indexes**: MongoDB models don't enforce uniqueness. Duplicate docs possible but harmless (findOne/findOneAndUpdate return first match).
7. **Server-side only**: Never call h-conf from client components. Use API proxy routes.
8. **No NEXT_PUBLIC_**: API key must not be exposed to browser.
9. **SSM for deploy**: Add env vars to serverless.yml/deployment config.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| 404 on getConfig | No ROOT level config | Use `ensureHconfHierarchy` |
| 404 on updateConfig | Target level doc missing | `ensureHconfHierarchy` then `createConfig` with actual data |
| getConfig returns wrong data | Cascade returning parent level | This is expected — getConfig always cascades |
| Company config not created | Used getConfig to check existence (cascade hides missing doc) | Use create-first pattern via `tryCreateLevel` |
| CORS error | Client-side call | Create API proxy route |
| 401 Unauthorized | Bad API key | Check HCONF_API_KEY env var |
| Undefined in client | NEXT_PUBLIC_ missing | Don't use NEXT_PUBLIC_, use API proxy |

## H-Conf Service Reference

- Models: `src/models/configModel.ts` (Mongoose discriminators, single collection `h_conf_configs`)
- Service: `src/services/configService.ts`
- Routes: `src/routes/configRoutes.ts`

## Next Steps

After h-conf setup is complete:

- Use **@backend-nextjs** for building production API routes with Zod validation, proper error handling, and authentication
- Add input validation schemas in `lib/validation/`
- Create permission helpers in `lib/permissions.ts` for role-based access
