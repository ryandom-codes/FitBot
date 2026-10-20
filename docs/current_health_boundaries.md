# Current scope and privacy

This local project explains reviewed adult fitness evidence and displays logged observations. It is not a medical adviser or a personal workout/diet planner. The original [V2 boundary document](health_boundaries.md) is preserved because its hash is part of the frozen benchmark.

Before retrieval or generation, the coordinator routes recognizable diagnosis, treatment, medication, rehabilitation, dangerous weight-loss and supplement requests to fixed refusals. Current rules also refuse recognizable personal calorie/macronutrient targets and workout programs. General questions about definitions, guidance and study findings remain in scope. Current chest-pain/pressure requests receive the existing fixed emergency response and source link, without a model call. This is limited symptom coverage, not a triage system. Regex rules can miss unfamiliar wording or block a valid question.

Generated answers select exact spans from reviewed retrieved evidence; Python resolves the text and citation IDs. Checks reject edited quotes and invented citations. This establishes traceability, not clinical safety or proof that a quote fully answers the question. Population, dates and limitations remain available in source panels and answer caveats. Fixed policy messages remain visible; generated answers that fail checks are withheld.

The research model receives the research question and reviewed passages. It does not receive profile fields, check-ins, lift entries, history or their summaries. Personal information typed directly into a research question would be processed by local Ollama, so avoid doing that. Storage is outside the public repository, but local database files and exports are not encrypted and the app has no authentication. Keep it bound to loopback and use synthetic records when sharing demonstrations. Saving records does not train the model.

Prompt/schema constraints are additional safeguards, not guarantees. Injection and boundary checks are small development tests. An independent human or clinical review has not occurred.
