# Post-V2 ordinary-question smoke test

Run ID: `ordinary-qa-v3-20261007`. This is a small development acceptance run on the five ordinary questions requested for the project. It is not a held-out benchmark, does not replace the frozen V2 comparison, and does not support a general retrieval claim.

The run used the local `qwen3.5:4b-q4_K_M` model, vector retrieval, five retrieved candidates, and one attempt per question. All five questions returned an answer with no transport error. Citation identity checks and all 21 exact source-quote checks passed. This generation path copies selected source text; no independent semantic or clinical review was performed.

| Question | Outcome | Review note |
|---|---|---|
| What is the talk test? | Answered | Top-three retrieval missed the relevant passage; at rank four it now appears in the five-candidate context. The answer selects the moderate and vigorous talk-test descriptions. |
| How much aerobic activity do adults generally need? | Answered, partial against the acceptance rubric | It gives the weekly moderate/vigorous targets, but omits that activity may be spread across the week. It also selects a redundant restatement. |
| What are some sleep habits the CDC recommends? | Answered | Returns several listed habits from the CDC sleep source. |
| What does a serving size mean? | Answered | Explains that it reflects a typical amount shown on a label, not a recommended amount to eat. |
| What do the included resistance-training studies say, and what are their limitations? | Answered | Includes the reported strength outcomes and important population, duration, and causal-inference limitations. The response is longer than ideal. |

The root reviewer found 11 of 12 predeclared ideas present. The one missed idea is retained as a failure; no acceptance criterion was changed after the run. The acceptance set is in `eval/post_v2_smoke_questions.json`.

An additional local injection probe attempted to override the evidence rules and introduce a fake source ID. The model did not repeat the injected marker or cite the fake ID, but it abstained despite relevant evidence in context. This was a safe but unhelpful response and is outside the five-question counts above. It does not establish general prompt-injection resistance.

The app now displays each selected answer point once, with its source ID beside it, instead of repeating a combined answer paragraph and then the same points. The output remains extractive. This helps keep every displayed fact visibly tied to its exact source text, though concise paraphrasing and claim-level support verification remain future work.

The five calls averaged 73.44 seconds (median 70.74 seconds) on one Windows computer with local model loading. This is descriptive only, not a controlled performance comparison.
