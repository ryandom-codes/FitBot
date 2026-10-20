# V2 evaluation results

Run: v2-20261007-fresh. The paired test used local qwen3.5:4b-q4_K_M, 18 questions, and 36 total attempts. Questions and code were frozen before generation. The two retrieval methods received the same question and shared context limits; method order alternated. Each method made one attempt per question with no retries. Raw outputs remain in the private project workspace.

## Retrieval and generation results

Retrieval scores use the ten answerable questions only; missing-evidence and safety cases are measured separately.

| Metric | BM25 keyword | Embedding vector |
| --- | ---: | ---: |
| Hit@3 | 90% (9/10) | 100% (10/10) |
| Chunk recall@3 | 85% | 100% |
| Frozen evidence-unit coverage@3 | 90% | 100% |
| Mean question-level completeness | 76.7% | 91.7% |
| Pooled fulfilled units | 18/27 (66.7%) | 25/27 (92.6%) |
| Fully complete questions | 6/10 | 8/10 |
| Expected status matches | 18/18 | 18/18 |
| Citation identity validity | 100% (62/62) | 100% (65/65) |
| Exact quote integrity | 100% (45/45) | 100% (50/50) |
| Unsupported claims against supplied passages | 0/45 | 0/50 |

The completeness mean gives each question equal weight; pooled unit coverage gives each required fact equal weight. They differ because questions contain different numbers of required facts. Both are reported so the denominator is visible. The review was AI-assisted and checked claims against passages supplied for that attempt. It is not human, medical, or clinical validation. Exact quotes and valid citation IDs establish traceability, not relevance or completeness. For example, a keyword answer to the sleep-habits question returned accurate age-specific sleep-duration rows instead of habits; its citation and quote checks passed while its required facts were not fulfilled.

Vector retrieval did better on this small, frozen question set. That is a result for these documents, questions, model, and settings—not evidence that vector search always wins. One frozen rubric item (N10) combines two population-limitation claims but treats their source IDs as alternatives. Its evidence-unit coverage can therefore be optimistic; the benchmark was preserved unchanged and this defect is disclosed rather than silently repaired.

## Safety, abstention, and timing

Both methods matched the expected status for all 18 questions. Each correctly abstained on the two missing-evidence cases, the deterministic safety route handled all four boundary cases without an LLM call, and both methods ignored the two untrusted-note attacks. Both answers to the intensity-and-talk-test injection question still omitted the requested numeric intensity scale, so resistance to the attack did not guarantee a complete answer. These are results on a tiny test set, not a safety guarantee.

Each method made 14 local model calls; the other four outputs used fixed policy responses. Total request time includes retrieval, generation, and verification on one Windows computer with mixed model-loading conditions.

| Timing | BM25 keyword | Embedding vector |
| --- | ---: | ---: |
| Mean | 56.00 s | 45.91 s |
| Median | 54.21 s | 47.37 s |
| Nearest-rank p95 | 68.29 s | 70.67 s |

The timings are descriptive; they are not a controlled speed comparison.

## What I would improve next

The next evaluation version should split N10 into atomic rubric units and use a new question set after any retrieval or prompt changes. I would also improve keyword handling for short multiword questions, add a semantic relevance check so a true quote cannot answer the wrong question, and have a human independently review a sample of claims and safety responses. I would keep each run and its failures instead of replacing results after a change.

The earlier V1 run and its limitations are preserved in [the V1 report](v1/evaluation_summary.md), with the frozen project snapshot in [archives/v1_snapshot.zip](../archives/v1_snapshot.zip).
