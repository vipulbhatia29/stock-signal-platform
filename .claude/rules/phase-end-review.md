---
description: Phase-end review dimensions — additional review criteria when running end-of-phase review
---

# Phase-End Review Dimensions

When `superpowers:requesting-code-review` is triggered at phase end (user says "phase-end review" or `/phase-closeout` is invoked), include these ADDITIONAL dimensions alongside standard code quality review:

## Additional Dimensions

1. **Cross-sprint integration consistency**
   - Do components built in different sprints work together correctly?
   - Are there interface mismatches between sprints?
   - Any duplicate or conflicting implementations?

2. **JIRA gap verification**
   - Query the JIRA board for open tickets in the current Epic
   - Are there tickets still open that should be Done?
   - Are there completed features missing tickets?

3. **Security review of new endpoints**
   - Do all new endpoints have proper auth guards?
   - Any IDOR vulnerabilities on detail endpoints?
   - Input validation on all user-facing parameters?

4. **Performance implications**
   - New database queries: are they indexed?
   - Any N+1 query patterns?
   - Cache invalidation for new data paths?

5. **Test coverage of new features**
   - Every new endpoint has auth + happy + error tests?
   - Every new service has unit tests?
   - Any untested edge cases visible from the code?

## Trigger Detection

This rule activates when ANY of these conditions are true:
- User explicitly says "phase-end review" or "end of phase review"
- `/phase-closeout` skill is invoked
- User says "we're done with this phase"

Present: "Phase-end review. Including integration + JIRA gap + security + performance + coverage. Adjust dimensions?"
