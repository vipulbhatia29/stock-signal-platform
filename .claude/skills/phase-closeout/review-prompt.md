# Phase-End Review Prompt

You are reviewing the complete output of a multi-sprint implementation phase. Your review covers both standard code quality AND phase-specific integration concerns.

## Review Dimensions

### 1. Code Quality (standard)
- Clean code, proper error handling, no dead code
- Consistent naming, proper typing
- No security vulnerabilities (OWASP top 10)

### 2. Cross-Sprint Integration
- Do components built in different sprints integrate correctly?
- Any interface mismatches (type conflicts, missing fields, wrong signatures)?
- Duplicate implementations of the same concept?
- Circular dependencies introduced across sprints?

### 3. JIRA Gap Verification
- Are there open tickets in the Epic that should be Done?
- Are there implemented features without corresponding tickets?
- Any tickets marked Done that aren't actually shipped?

### 4. Security Review
- All new endpoints have auth guards (`get_current_user` dependency)?
- IDOR checks on detail endpoints (user_id scoping)?
- Input validation on all user-facing parameters?
- No `str(e)` in user-facing error messages?

### 5. Performance
- New queries: are relevant columns indexed?
- Any N+1 patterns (loop of individual queries)?
- Cache invalidation for new data paths?
- Pagination on list endpoints?

### 6. Test Coverage
- Every new endpoint: auth test + happy path + error case?
- Every new service: unit tests covering main logic?
- Edge cases: empty inputs, None values, boundary conditions?
- Regression tests for any bugs fixed?

## Output Format

```
## Phase-End Review

**Reviewed:** [list of files/areas covered]

### Critical (must fix before merge)
- [file:line] [issue] — [why it matters]

### Important (fix before next phase)
- [file:line] [issue] — [why it matters]

### Minor (note for future)
- [file:line] [issue] — [why it matters]

### Positive Observations
- [what was done well]
```

Focus on REAL issues that would cause bugs, security holes, or integration failures. Do not flag style preferences, minor naming quibbles, or "nice to have" improvements.
