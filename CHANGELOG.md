# Release history

## V2.1 — Post-Benchmark Reliability Update

Prepared October 20, 2026. Created and maintained by Ryan Dominguez with AI-assisted implementation and review.

- Retrieves up to five candidate passages so relevant evidence ranked fourth can reach the answer stage.
- Displays sourced answer points once, handles fixed policy responses, and clears stale results after request errors.
- Includes example questions, expandable caveats, and private tracking with synthetic demo records.
- Adds regression and development acceptance evidence, corpus documentation corrections, and private-artifact exclusions.
- Uses neutral post-V2 filenames for development checks. Original experiment IDs inside evidence files remain unchanged.

The frozen V2 benchmark used top-three retrieval. Its results, rubric limitations, and archived runtime remain preserved. Separate development acceptance checked 11 cases, with 11 expected-status/mechanical passes and 20/20 exact quote checks; this is not a fresh held-out accuracy estimate. See [the acceptance review](reports/post_v2_acceptance_review.md) for failures and limits.

Known limits include repetitive or context-dependent quotations, weak missing-evidence follow-ups, a small corpus, and incomplete safety-pattern coverage. Local generation can take a minute or longer. The project has not trained an LLM and has no independent clinical validation.

## Historical evidence

V1 and V2 are preserved in [the archives](archives/README.md). Future releases will document changes and measure them on fresh questions. V3 implementation and model training are future work.
