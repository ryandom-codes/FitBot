# V1 health boundaries

This project offers general adult exercise and food-label education and describes explicitly logged records. It is not a clinically validated medical or triage system. Its rules and prompt can miss paraphrases.

The coordinator checks scope before retrieval or generation, for both retrieval methods. Fixed policy responses are labeled separately from generated research answers.

- Refuse personal diagnosis, symptom or test interpretation, treatment, medication choices/doses, rehabilitation prescriptions and medical clearance.
- Refuse starvation, purging, deliberate dehydration, extreme weight-loss instructions and steroid/drug stacks.
- Refuse individualized medical nutrition, including therapeutic plans for conditions, medication interactions, pregnancy and children.
- Refuse supplement brand, dosing, stack and personal recommendation requests: no supplement efficacy/dosing corpus is included in V1.
- For current chest pain/pressure or a request to keep exercising through it, give fixed emergency guidance: stop exercising and seek emergency help; US 911 or the local emergency number elsewhere. Do not diagnose, suggest medicine or delay with follow-up questions. This rule is incomplete symptom coverage.
- If supplied evidence cannot establish a research answer, say so. Related passages do not establish an optimal personal program or cause of an individual plateau.

Research answers include status, answer, cited key points, caveats and follow-up questions. Citation identity and attachment checks establish traceability, not truth or medical safety. The demo withholds outputs that trigger its limited unsafe-content or injection-marker checks; evaluation retains failures.

Personal records remain in a sibling private directory. There is no authentication, database encryption, clinical oversight or suitability for a public multi-user deployment. Only synthetic records belong in the repository. Saving records does not train or fine-tune the pretrained LLM.

Policy provenance reviewed October 7, 2026: [NHLBI emergency symptom guidance](https://www.nhlbi.nih.gov/health/heart-attack/symptoms) (March 24, 2022) and [NIH ODS supplement overview](https://ods.od.nih.gov/factsheets/WYNTK-Consumer/) (January 4, 2023). These support the boundary policy; they are not an approved supplement recommendation corpus.
