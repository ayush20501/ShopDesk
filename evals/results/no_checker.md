# Eval run: no_checker

Config: chunking=heading, retrieval=hybrid, checker=off

| Metric | Result |
|---|---|
| Questions | 75 |
| **Fully correct (all checks)** | **100%** |
| Routing accuracy | 100% (71 questions) |
| Retrieval found the right policy | 100% (24 questions) |
| Answer text correct | 100% |
| Right action prepared (or none) | 100% |
| Crashed questions | 0 |
| Answers rewritten after the checker objected | 0 |
| Average seconds per question | 4.8 |

| Question type | Fully correct |
|---|---|
| action | 100% |
| chat | 100% |
| eligibility | 100% |
| order | 100% |
| policy | 100% |
| safety | 100% |
