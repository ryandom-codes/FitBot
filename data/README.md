# Reviewed source snapshots

`sources.json` contains selected text from eight public sources, accessed October 7, 2026. It includes original URLs, section headings, source dates (unknown stays null), licenses, selection/omission notes and SHA256 hashes. Agency date labels are displayed/review dates, not necessarily publication dates. Snapshot access dates are not evidence-search dates.

| Source | Type and scope |
| --- | --- |
| CDC Adult Activity Overview | Adult public-health activity guidance |
| CDC What Counts for Adults | Aerobic and strengthening examples |
| CDC Measure Intensity | Talk test and relative/absolute intensity |
| CDC About Sleep | Adult sleep-duration ranges and six sleep-habit suggestions |
| NIDDK Health Tips for Adults | Selected nutrient-rich food examples; reviewed September 2020 |
| NIDDK Food Portions | Portion/serving concepts; reviewed July 2021 |
| FDA Nutrition Facts explanation | Serving basis, energy and %Daily Value; page date not established |
| Lyristakis et al. (2026), Sports Medicine | Resistance-training systematic review/meta-analysis, DOI [10.1007/s40279-026-02432-5](https://doi.org/10.1007/s40279-026-02432-5); search through July 10, 2025 |

The first seven sources are agency educational summaries, not original experiments. The research selection preserves eligibility, an effect paragraph and selected complete limitation sentences. The trials concern adults without a current diagnosed medical/musculoskeletal condition, training at least four weeks versus nonexercise controls; concurrent exercise was excluded. The analysis focuses on chest/quadriceps strength and mostly short-term untrained populations. It does not establish a personal optimal program, hypertrophy split or protein target. Every research chunk carries compact, explicitly authored scope/limitations metadata alongside the original excerpt.

Text was extracted through the Exa webpage tool after direct official-URL requests returned HTTP403. Selected passages were checked against official pages; extraction method and hashes are recorded. Whitespace/list formatting is normalized. Pictures, logos, figures, full tables, references' content, linked pages and navigation are excluded. A figure-range dash in the research extraction was checked against the publisher. Selection details are recorded per section. Raw page extractions remain outside the public repository.

Source excerpts were developed by CDC, NIDDK and FDA as identified. Originals are available free at the linked agency websites. **This independent project is not endorsed by these agencies, HHS or the United States Government.** Generated explanations are application outputs, not agency text.

Reuse policies: [CDC](https://www.cdc.gov/other/agencymaterials.html), [NIDDK](https://www.niddk.nih.gov/copyright), [FDA](https://www.fda.gov/about-fda/about-website/website-policies). The research text is credited to Lyristakis, Wundersitz, Cousins, Huynh, Zadow and Gordon (2026), under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); see the [original paper](https://link.springer.com/article/10.1007/s40279-026-02432-5). Excerpts omit specified sentences/assets; formatting is normalized and applicability metadata is authored for this project. No third-party images are redistributed.

The bundled JSON is sufficient to run offline ingestion and local research; an API key and live source crawling are not needed. To refresh, fetch only reviewed URLs into a private raw directory and write a **candidate**, inspect changes manually, then rebuild the index and create a new evaluation version:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_sources.py --raw-dir ..\fitness-research-assistant-private\raw-sources-new --output ..\fitness-research-assistant-private\sources-candidate.json
```

Some sites block direct requests. The script deliberately fails on missing headings/redirects rather than replacing sources silently. It also supports `--offline` for saved HTML and `--extracted-pages` for a private JSON URL-to-Markdown mapping obtained from readable official pages; record the extraction tool accurately when making a new corpus. Do not overwrite the frozen corpus after seeing evaluation results.

`demo_history.json` is entirely synthetic. Real records belong only in the private SQLite database. HHS scientific-report PDF ingestion, broader nutrition research and source freshness automation are future work.
