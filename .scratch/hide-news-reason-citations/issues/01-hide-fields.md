# 01 — Hide fields at presentation and response boundaries

Type: task
Status: resolved
Blocked by: none

## Answer

Removed recommendation reason and related citations from production article/detail views. Public brief projection filters nested news fields using the API schema, including existing stored briefs. StoredNewsItem preserves the original internal validation contract. Updated design guidance and generated client types.

Validation: npm run build passed (contract, TypeScript, user and admin builds). Targeted brief HTTP regression and execution suite: 18 passed. HTTP coverage checks both list/detail omission and unchanged persisted news records. Browser visual/responsive checks were not run.
