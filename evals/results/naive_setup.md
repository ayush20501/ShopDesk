# Eval run: naive_setup

Config: chunking=fixed, retrieval=vector, checker=off

| Metric | Result |
|---|---|
| Questions | 75 |
| **Fully correct (all checks)** | **95%** |
| Routing accuracy | 100% (71 questions) |
| Retrieval found the right policy | 96% (24 questions) |
| Answer text correct | 95% |
| Right action prepared (or none) | 100% |
| Crashed questions | 0 |
| Answers rewritten after the checker objected | 0 |
| Average seconds per question | 4.5 |

| Question type | Fully correct |
|---|---|
| action | 100% |
| chat | 100% |
| eligibility | 70% |
| order | 100% |
| policy | 96% |
| safety | 100% |

## Failures

- **p13** What is the COD fee?  
  retrieval missed ['payments.md'], got ['loyalty.md', 'shipping.md']; missing one of ['49']
- **e01** Can I return the Pebble Buds Pro from order 1001?  
  missing one of ['10 days', '10-day']
- **e04** Can I return the blanket from order 1005?  
  missing one of ['30 days', '30-day']
- **e05** Can I still return the charger from order 1008?  
  missing one of ['@yes']
