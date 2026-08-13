# Acceptance Criteria Guide

Reference for writing clear, testable acceptance criteria in Given/When/Then (Gherkin) format.

---

## Format

```
Given {precondition or context}
When {action the user takes or event that occurs}
Then {expected observable outcome}
```

Each criterion should be **independently verifiable** — a QA engineer or automated test should be able to confirm it passes or fails without ambiguity.

---

## Rules for Good Acceptance Criteria

1. **Be specific, not vague** — "The system responds quickly" is bad. "The API responds within 500ms for 95% of requests" is good.

2. **One behavior per criterion** — Don't chain multiple behaviors into a single Given/When/Then. Split them.

3. **Cover the boundaries** — Include both valid and invalid inputs, empty states, and limits.

4. **Use concrete examples** — "Given the user enters 'test@email.com'" is clearer than "Given the user enters a valid email."

5. **Include the negative cases** — What happens when things go wrong? Invalid input, missing permissions, network failure.

6. **Avoid implementation details** — "Then a 200 status code is returned" is too technical for a user story. "Then the user sees a success confirmation" is better.

7. **Make them testable** — If a human or script can't verify the criterion objectively, rewrite it.

---

## Examples by Category

### Form Input & Validation

```
Given the user is on the registration form
When they submit the form with an email that is already registered
Then they see an error message: "An account with this email already exists"
And the email field is highlighted in red
```

```
Given the user is filling in the phone number field
When they enter a value with fewer than 10 digits
Then the form displays an inline validation error: "Phone number must be at least 10 digits"
And the submit button remains disabled
```

### Authentication & Authorization

```
Given the user is not logged in
When they attempt to access the settings page
Then they are redirected to the login page
And after successful login, they are returned to the settings page
```

```
Given the user has a "viewer" role
When they attempt to delete a record
Then they see a message: "You don't have permission to perform this action"
And the record remains unchanged
```

### Data Display & Listing

```
Given there are more than 20 items in the list
When the user loads the page
Then only the first 20 items are displayed
And a "Load more" button appears at the bottom
```

```
Given there are no items matching the search query
When the user sees the results page
Then an empty state message is displayed: "No results found. Try different keywords."
And a "Clear search" button is available
```

### Async Operations & Loading States

```
Given the user clicks "Generate Report"
When the report generation begins
Then a loading indicator appears with the message "Generating report..."
And the user cannot click "Generate Report" again until it completes
```

```
Given a file upload is in progress
When the network connection is lost
Then the upload pauses and a message appears: "Connection lost. Upload will resume when reconnected."
And progress is preserved for retry
```

### Notifications & Feedback

```
Given the user successfully saves changes to their profile
When the save operation completes
Then a success toast appears: "Profile updated successfully"
And the toast auto-dismisses after 5 seconds
```

```
Given the user performs a destructive action (delete)
When they click the delete button
Then a confirmation dialog appears: "Are you sure? This action cannot be undone."
And the item is only deleted after the user confirms
```

### API / Integration Behavior

```
Given a third-party API call fails with a timeout
When the system handles the failure
Then the user sees a friendly error message (not raw error details)
And the system retries the call up to 3 times before failing
And the failure is logged for monitoring
```

---

## Criteria Count Guidelines

| Story Size | Recommended AC Count |
|-----------|---------------------|
| S | 2-3 criteria |
| M | 3-5 criteria |
| L | 5-8 criteria |
| XL | Split the story — it's too big |

If you find yourself writing more than 8 acceptance criteria, the story likely needs to be decomposed.

---

## Common Mistakes

| Mistake | Example | Fix |
|---------|---------|-----|
| Too vague | "The page loads correctly" | Specify what "correctly" means |
| Implementation detail | "A Redux action dispatches UPDATE_USER" | Describe the user-visible outcome |
| Restating the story | "The user can upload a file" | Add specifics: format, size, feedback |
| Missing the negative | Only happy path criteria | Add error and edge case criteria |
| Compound criterion | Given/When/Then with 5 "And"s | Split into separate criteria |
| Untestable | "The UX feels intuitive" | Define measurable proxy metrics |
