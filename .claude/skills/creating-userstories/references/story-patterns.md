# Story Decomposition Patterns

Reference guide for splitting features into well-sized user stories.

---

## Pattern 1: Workflow Steps

Split a multi-step process into one story per meaningful step.

**Example — User Registration:**

| Story | Step |
|-------|------|
| US-001 | User fills in registration form |
| US-002 | System validates email uniqueness |
| US-003 | User receives verification email |
| US-004 | User confirms email and activates account |
| US-005 | User completes profile setup |

**When to use:** Multi-step processes, wizards, onboarding flows.

---

## Pattern 2: CRUD Operations

Split data management features by operation type.

**Example — Product Catalog Management:**

| Story | Operation |
|-------|-----------|
| US-001 | Admin creates a new product listing |
| US-002 | Admin views product listing details |
| US-003 | Admin edits an existing product listing |
| US-004 | Admin archives/deletes a product listing |
| US-005 | Admin searches and filters product listings |

**When to use:** Any feature centered on managing a data entity.

---

## Pattern 3: User Role Variation

Same feature, different stories per role.

**Example — Dashboard Access:**

| Story | Role |
|-------|------|
| US-001 | Sales rep views their own pipeline dashboard |
| US-002 | Sales manager views team-wide pipeline dashboard |
| US-003 | Executive views company-wide summary dashboard |

**When to use:** Features where different roles have meaningfully different views or permissions.

---

## Pattern 4: Happy Path vs. Edge Cases

Core flow first, then error handling and edge cases.

**Example — File Upload:**

| Story | Path |
|-------|------|
| US-001 | User uploads a valid file and sees confirmation |
| US-002 | System rejects files exceeding size limit with clear error |
| US-003 | System rejects unsupported file formats with guidance |
| US-004 | User retries after a failed upload (network error) |
| US-005 | User cancels an in-progress upload |

**When to use:** Any feature with significant error/edge case handling.

---

## Pattern 5: Data Variation

Split by input type, format, or source.

**Example — Report Export:**

| Story | Variation |
|-------|-----------|
| US-001 | User exports report as PDF |
| US-002 | User exports report as CSV |
| US-003 | User exports report as Excel with formatting |
| US-004 | User schedules automatic report delivery via email |

**When to use:** Features handling multiple data formats, sources, or types.

---

## Pattern 6: Business Rules

Each distinct business rule becomes its own story.

**Example — Discount Engine:**

| Story | Rule |
|-------|------|
| US-001 | System applies percentage-based discount codes |
| US-002 | System applies fixed-amount discount codes |
| US-003 | System enforces minimum order value for discount eligibility |
| US-004 | System prevents stacking of multiple discount codes |
| US-005 | System auto-expires discount codes past their end date |

**When to use:** Features with complex or multiple business rules.

---

## Pattern 7: Platform / Interface

Split by where the interaction happens.

**Example — Notification Preferences:**

| Story | Interface |
|-------|-----------|
| US-001 | User manages notification preferences on web |
| US-002 | User manages notification preferences on mobile |
| US-003 | System sends push notifications per user preferences |
| US-004 | System sends email notifications per user preferences |
| US-005 | External systems configure notification rules via API |

**When to use:** Cross-platform features, API + UI combinations.

---

## Pattern 8: Performance / Non-Functional

Separate functional stories from performance and operational concerns.

**Example — Search Feature:**

| Story | Type |
|-------|------|
| US-001 | User searches products by keyword (functional) |
| US-002 | Search results return within 200ms for up to 10k products (performance) |
| US-003 | Search supports typo tolerance and fuzzy matching (quality) |
| US-004 | Search queries are logged for analytics (operational) |

**When to use:** When non-functional requirements are significant enough to warrant their own stories.

---

## Sizing Guide

| Size | Sprint Effort | Characteristics |
|------|--------------|-----------------|
| **S** | < 1 day | Single component, clear implementation, minimal unknowns |
| **M** | 1-3 days | Multiple components, well-understood domain |
| **L** | 3-5 days | Cross-cutting, some unknowns, needs design discussion |
| **XL** | > 5 days | **Should be split further** — too large for a single story |

---

## Anti-Patterns to Avoid

1. **Technical stories disguised as user stories** — "As a developer, I want to refactor the database..." → This is a task, not a user story. Reframe around user value.

2. **Stories that are really epics** — "As a user, I want a complete reporting dashboard..." → Too broad. Split by report type, role, or interaction.

3. **Implementation-prescriptive stories** — "As a user, I want a React modal with a POST to /api/orders..." → Describe *what*, not *how*.

4. **Stories without acceptance criteria** — If you can't write Given/When/Then, the story isn't well-defined yet.

5. **"So that" value is vague** — "So that I can use the feature" → Always tie to real business value.

6. **Acceptance criteria that are just the story restated** — Criteria must be more specific and testable than the story itself.
