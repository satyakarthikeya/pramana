# Research note: what to do next, and what to do after

Written 2026-10-24 for the PRAMANA team. Source: a read of the repo at `origin/main` (merge of PR 31) plus web search on the same day. No source, config or test was changed.
Outline and bullets only (AGENTS.md section 7): nothing here is thesis prose.

How to read the evidence labels: **[repo]** = read in this repo; **[search]** = seen in a search result or abstract, full paper not read; **[estimate]** = my guess, not measured. I did not run anything (the Python env in this session has no `pramana` installed), so every hour and runtime below is an **[estimate]** except where a repo doc gives a number.

---

## 0. The short version

1. The strongest thing PRAMANA has is real and rare: a model never supplies a number, an LLM planner sees only exploration rows, a separate confirmation split feeds one permutation test per claim, BH is applied once per run, and only PASS reaches memory. Defend that; do not dilute it.
2. The weakest thing is **evidence about it**. Every number in the repo that supports the gate is single-claim, 100 replicates, synthetic, or written by the same person who wrote the code being scored (`GATEWAY_V3_STATUS_AND_SIGNOFF.md` section 4; `ANALYST_LAYER_STATUS.md` "Measured"). Nothing measures BH on correlated claims. The four-condition ablation in `PROJECT.md` section 6 has only A and D built.
3. With 24 hours, spend about half on three cheap experiments (section 4) that turn "we believe" into numbers with confidence intervals, and the rest on four small fixes that stop an examiner from catching you out (section 3).
4. Do not add claim types, models, or UI polish before the review.

---

## 1. Honest comparison with current tools

What the other tools do is taken from vendor docs or reviews I found (links in section 7). I found no description of multiple-testing control in any of them. **Absence from the pages I read is not proof of absence**; if the examiner asks, say "I did not find it documented", not "they don't have it".

| Dimension | PRAMANA today [repo] | ChatGPT data analysis | Julius | Hex Magic | PandasAI | DS-Agent / AutoKaggle |
|---|---|---|---|---|---|---|
| What it is | Closed menu of analyses run by code; a model only picks from the menu | Model writes and runs Python; OpenAI tells users to review the code and assumptions | Chat with a file; charts, models, some tests (third-party reviews) | Assistant inside a notebook; Hex says it is a helper, not an "AI data analyst" | `df.chat()` returns a string, dataframe, chart or number | Research agents for ML pipelines (Kaggle-style) |
| Who produces a number | Code only. Model wording is shown only if every number matches a cited result | The model's generated code | Model-generated code | Model-generated SQL/Python cells | Model-generated code | Model-generated code |
| Many-claims problem | BH once per run over all tested claims; confirmation split; look ledger | Not documented in what I read | Not documented in what I read | Not documented in what I read | Not documented in what I read | Scored on task success, not on false findings |
| Proof / audit | Proof object per claim: seed, executed code, p, q, effect, interval, power note, spec hash | Code is visible | Code visible in some plans (not checked) | Cells are visible | Code can be inspected | Code and logs |
| Refusal | Causal/universal wording refused; too-short series and leaks marked NOT_TESTABLE | Not documented | Not documented | Not documented | Not documented | n/a |
| Published evaluation | None of our own beyond a 100-rep report card and a 7-fact synthetic recall check | n/a | n/a | n/a | n/a | DS-Agent, AutoKaggle: success / valid-submission rates on ML tasks |
| Breadth | Narrow: one table, 8 claims per run, trend refused above 3,000 rows, one run at a time, ~4-6 minutes a run (375 s NHANES, 236 s finance) | Any question, many file types, fast | Any question, DBs, many models | SQL + Python, warehouse context | Any question | ML pipelines |
| Where it loses badly | Anything the menu does not contain; speed; polish; scale; no SQL; no cohort/forecast/driver tree in the story | Can state a spurious relationship with total confidence | Same | Same | Same | Not aimed at inference |

Blunt reading:
- **Best today:** provenance of every number, a confirmation split that stops the planner's choices from being the test data, one correction per run, effect bands, power notes, and refusing to call a REJECT "false".
- **Worst today:** you cannot yet show, with a number, that this beats a plain "ask the model" baseline. Until you can, "execution-grounded verification" is a design claim, not a result.
- The benchmarks below all score **answer correctness**. None of what I found scores whether an agent reports false findings. That is the gap PRAMANA can credibly fill, and it is an evaluation you can build (section 4).

How the benchmarks are structured [search]:
- InfiAgent-DABench: closed-form questions with a fixed answer format so scoring is automatic; the ICML version lists 603 questions on 124 CSVs, and 34 models were tested. Other paper versions give different counts, so cite the version you use.
- DA-Code: 500 tasks in data wrangling, ML and EDA, Python and SQL, executed in a controlled environment; the best model reached 30.5%.
- DSBench: 466 analysis and 74 modelling tasks; the best agent solved about 34% of analysis tasks.
- DSEval: also checks the quality of the solution and side effects such as unintended changes to the original data.
- 2026 preprints (seen through secondary summaries only, treat as unverified): coding agents drift toward p-hacking under "explore alternatives" framing; opposing persona priming gives opposite conclusions from the same data; a proposal to preregister the analysis. They support the PRAMANA design but I did not read them.

---

## 2. What the statistics literature says, for a single-user exploration tool

| Idea | What it fixes | Applies here? |
|---|---|---|
| Garden of forking paths (Gelman and Loken) | Analysis choices made after seeing the data inflate false positives even with no intent to fish | **Yes, and PRAMANA already answers it**: the planner sees exploration rows only; the gate sees confirmation rows. Say this first in the defence. Residual leak: the same confirmation rows are looked at again by every later run and chat question (design doc W1; look ledger discloses, does not block) |
| Benjamini-Hochberg | FDR across all claims in a run | In use. Guarantee needs independence or positive dependence (Benjamini and Yekutieli); claims sharing a column are not obviously in that class. **Not measured here** |
| Benjamini-Yekutieli | FDR under any dependence, at a cost of about log(m) in the threshold | Conservative fallback if the correlated-family experiment (E2) shows excess FDR |
| Westfall-Young maxT / Romano-Wolf | Uses the same permutations to respect dependence; controls FWER, not FDR | Natural fit because the gate already permutes; a real change to the verdict rule, so verification-owner sign-off. Later |
| Online FDR: alpha-investing, LORD++, SAFFRON | A stream of tests, error control at every time | Only matters for chat. Design doc decision 4 parked it. For one user and short sessions a per-dataset count of questions asked is enough for now. Guarantees need independence or non-negative dependence |
| E-values / e-BH (Wang and Ramdas) | FDR under arbitrary dependence with no correction for it | Needs e-values, not permutation p-values. Research track, not a quick change |
| Reusable holdout (Dwork et al.) | Many adaptive looks at one holdout | The look ledger takes the idea (a budget of looks). Full Thresholdout is overkill |
| Data fission / thinning | Split one observation instead of rows, so less power is lost | Original construction covers Gaussian and Poisson; rank tests and clustered rows are outside it. No |
| Selective inference (Fithian, Sun, Taylor) | Valid inference after selection; "data carving" beats pure splitting in power | The principled long-term answer to the 50/50 split cost. Too big for now |
| Model-X knockoffs | FDR control for variable selection with a known covariate distribution | Possible for the Measured "drivers" menu only. Not for pairwise claims. Later at best |
| Specification curve / multiverse | Show the spread over defensible analyses | The attacks already do a small version; keep only equivalent re-asks, as the design doc says |

What a single-user tool should not do: pretend that one BH family per run controls errors across a user's whole week of questions. State it plainly: "FDR is controlled within a run; across runs and chat questions the number of looks is disclosed, not corrected."

---

## 3. Ranked improvements

Scoring: **Thesis value** = what an examiner will credit (H/M/L). **Risk** = to the prime directive `memory_write => verdict == PASS` and to statistics correctness. Hours are **[estimate]** for one developer with an assistant.

### 3A. Do by tomorrow night (about 12 hours in total)

| # | Item | Thesis value | Hours | Risk | Files it would touch |
|---|---|---|---|---|---|
| 1 | **Run the three experiments in section 4** (E1 gate vs no gate, E2 correlated-claim FDR, E3 blind planted-fact recall with decoys). Write the metrics and seeds into a file before the first run | **H** | 6 | None to the invariant: scripts read proofs and never write memory. Any number quoted needs the verification owner's sign-off (AGENTS.md 8.10) | New `scripts/calibration/eval_gate_ablation.py`, `eval_correlated_fdr.py`, `eval_blind_recall.py`; results into `docs/` (reuses `pramana/evaluation/planted.py`, `verification/fdr.py`, `verification/stats`) |
| 2 | **Partial last period detection** (a table that ends mid-month makes a false year-on-year drop the headline; listed under "Not done" in `ANALYST_LAYER_STATUS.md`). Flag it in data quality and compare like with like or say "last period incomplete" | **H** (a finance examiner will find this in minutes) | 1.5 | None (Exact tier only) | `src/pramana/analysis/computed/runner.py` (`period_change`, `data_quality`), a known-answer test in `tests/unit/analysis/` |
| 3 | **Surface the forecast headline in the story**: next 3 periods with an interval, and whether it beats seasonal-naive. Already computed in the Measured tier, only not shown (`ANALYST_LAYER_STATUS.md` "Not done"; `PLAN_data_analyst.md` A8) | M-H (the first thing a finance reviewer asks) | 2 | None: Measured never reaches the gate | `src/pramana/analysis/computed/story.py`, `computed/summary.py`, `web/src/components/Computed.tsx` |
| 4 | **Demo freeze and defence sheet**: run the offline profile (`PRAMANA_ANALYSIS_ENGINE=deterministic`, template generator, Langfuse off) once on NHANES demo and the finance table with fixed seeds; save the outputs and screenshots; write a one-page list of the questions an examiner will ask (why PASS, why REJECT, what is the family, what does q mean, what did you not test) with the file that answers each | **H** (the live profile took 236-375 s, the planner proposes different claims each run, and a live API or Langfuse failure fails closed by design) | 1.5 | None | `docs/` only; outputs in ignored `artifacts/` |
| 5 | **Sync the stale documents before an examiner reads them.** Examples: `PROJECT.md` section 2 says DeepSeek writes the test by default, but `AGENTS.md` section 2 says the vetted template is the default; `README.md` limitations say "no confounder adjustment, held-out replication", yet the gateway has a confirmation split and an adjusted-association attack; `PROJECT.md` section 6 says only A and D exist, which is still true but should say B and C are stubs in `evaluation/conditions.py` | M | 1 | `PROJECT.md` and `AGENTS.md` are shared files: announce the change (AGENTS.md 8.7) | `README.md`, `PROJECT.md` (owner sign-off), `docs/V1.md` |

Total: 12 hours. Order: 2, 1 (start the E2 and E1 jobs running in the background), 3, 4, 5, then fill in the numbers.

If only 6 hours exist: items 1 (just E2 and E3) and 4.

### 3B. Later (after the review), ranked

| # | Item | Thesis value | Hours | Risk | Files |
|---|---|---|---|---|---|
| L1 | **Finish the ablation**: build condition B (agent loop, no gate) and C (same model with an LLM critic, prompted to succeed, as `OPEN_ISSUES.md` issue 3 requires), then run A-D on 20-40 planted tables. This is the thesis centrepiece in `PROJECT.md` section 6 | **H** | 10-14 | Low (read-only on the gate); C must be built fairly or the result is worthless | `src/pramana/evaluation/conditions.py`, new proposer adapters |
| L2 | **Memory ablation**: is the "self-evolving" part useful? Run dataset B with and without lessons from dataset A and score the proposals. Today memory only offers hints to re-test, and nothing measures whether they help. The title promises more than the evidence shows | **H** (a likely examiner question) | 4-6 | None if hints stay hints | `src/pramana/memory/`, evaluation scripts |
| L3 | **If E2 shows excess FDR**: switch the in-run correction to a permutation-based joint procedure (Westfall-Young style) or BY as a conservative fallback | H if triggered | 6-8 | **High**: changes p-values/FDR; verification-owner approval and a test that REJECT never upgrades | `src/pramana/verification/fdr.py`, `gateway.py`, `configs/verification.yaml` |
| L4 | **Cohort retention** (needs a customer id and a date; the retail table has both): retention by first-purchase month, plain arithmetic, known-answer test | M | 3 | None | `analysis/computed/analyst.py`, `story.py`, web chart |
| L5 | **Driver tree**: revenue = customers x orders per customer x average order value, with each factor's share of the change (log decomposition so the parts add up exactly, asserted like price/volume/mix) | M-H | 3 | None | `analysis/computed/analyst.py` |
| L6 | **Anomaly explanation**: for each flagged row or month, show which segment and which factor (price or volume) account for it | M | 3 | None | `analysis/computed/runner.py` (`outliers`), `analyst.py` |
| L7 | **Data-quality scorecard** as one block at the top (missingness, duplicates, type surprises, identity violations, incomplete last period, outlier rows) with a count each. Most pieces exist in `data_quality` | M | 2 | None | `analysis/computed/runner.py`, `web/src/components/Brief.tsx` |
| L8 | **Question-answer accuracy suite**: ~30 closed-form questions on the Exact tier with gold from an independent pandas script, DABench-style `@name[value]` answers. Remove famous CSVs; DeepSeek may have seen the public DABench files, so use it only as an external comparison (`EVALUATION.md` section 4 says the same) | M | 4 | None | `docs/EVALUATION.md` plan, new script |
| L9 | **Tested claims T5/T7/T8** (segment drove the change, model beats baseline, adjusted association) and attacks for period-change and seasonality (all seven "do not apply" today) | M | 8+ | Medium: new claim types, owner sign-off | `verification/`, `analysis/planner/` |
| L10 | **Online FDR for chat** (LORD++ or SAFFRON) only if chat becomes multi-question. State the independence assumption next to the code | L-M | 8 | High: statistics decision | `chat/`, `verification/` |
| L11 | **Block bootstrap interval for trend claims** (none today for block-differenced series), and a trend method for tables above 3,000 rows | M | 6 | Medium | `verification/interval.py`, `stats/` |
| L12 | Hierarchical or DBSCAN second clustering view; drill-down round; head-to-head showing KNN is picked when it should be | L | 5+ | None | `analysis/measured/` |

Known open bug worth one hour before any polish: the DeepSeek reword of the summary fell back to code wording on the retail table ("a number that is not in the figure"), not investigated (`ANALYST_LAYER_STATUS.md`). It is the only visible model feature on the results page, and it fails on the real-data demo.

---

## 4. The three evaluation experiments most worth running

Rule for all three: **write the metric, the seeds, the sample sizes and the "bad result" line into a file first and commit it** (the same logic as `SPEC.md` section 1: a scoring rule chosen after seeing outputs is worthless). Do not rerun until it looks better; that is a garden of forking paths on your own evaluation. Report 95% intervals (`scipy.stats.binomtest(...).proportion_ci`), not bare rates. `EVALUATION.md` section 2 already notes that 200 null datasets only detect a doubling of the error rate (0.10) with about 85% power; say so beside any null result.

### E1. Gate versus no gate (the thesis headline)

- **Question:** For the same proposed claims on the same data, how many false reports does each decision rule produce, and what does the gate cost in recall?
- **Design:** One gateway run per dataset. From the stored proofs (every tested claim has a raw p, a q and an effect), compute four reported sets: (a) raw p below 0.05, no correction; (b) BH only; (c) BH plus effect floor; (d) the full gate (PASS). Score each against the planted truth with `pramana.evaluation.metrics.score_reported`: false reports per null dataset, FDP, precision, recall.
- **Data:** `build_planted_dataset` (`src/pramana/evaluation/planted.py`) with `configs/evaluation.yaml` schedule `k_per_dataset: [3, 3, 2, 0]` and the effect levels (clear 2.5x, moderate 1.8x, just above 1.25x, just below 0.7x of the floor). Needs an NHANES-shaped extract: use the `extract_shape` block of `configs/evaluation.yaml` for a synthetic one, or `data/demo/nhanes_demo.csv` after `scripts/build_demo_nhanes.py`. Start with 20 datasets.
- **Proposer:** the deterministic rule scan and the template generator, so no API key or Langfuse is needed. If DeepSeek is available, add condition A (a single model call, everything reported) as a fifth row.
- **Command (to be written, ~100 lines):** `python scripts/calibration/eval_gate_ablation.py --datasets 20 --permutations 1000 --out artifacts/e1.json`
- **Under an hour?** Probably for 20 datasets at 1,000 permutations **[estimate]**; time one dataset first. Do not use 10,000 permutations for the first pass.
- **Good result:** rule (a) reports several false findings per null dataset, rules (b)-(d) report at most about alpha of datasets with any false report, and (d) keeps recall on "clear" and "moderate" effects (the design doc measured 0.97 power at rho about 0.3, n = 100).
- **Bad result and what it means:** if (d) loses most "just above" effects, that is the price of the 50/50 split and the floor; say so, do not tune the floor to hide it. If (b)-(d) still report false findings in more than about 10% of null datasets, the gate is leaking and E2 is the next step. If (a) is not much worse than (d), the tables are too easy; plant more nulls.

### E2. False discoveries under correlated claims (the unmeasured hole, W3)

- **Question:** Does BH keep the false discovery proportion at or below alpha when the claims in a run share columns and the columns are correlated?
- **Design:** Simulate tables with a latent-factor structure (for example 12 columns driven by 2 shared factors plus a few truly related pairs). Propose all pairwise correlation claims (up to the run cap, or raise `m_max` in a copy of the config, never the committed file). Compute permutation p-values with `pramana.verification.stats.permutation_test` directly (no sandbox, so each replicate takes seconds), correct with `pramana.verification.fdr.apply_bh`, and also with BY and a Westfall-Young maxT computed in the script only. Record per replicate: false discoveries, discoveries, FDP.
- **Data:** synthetic, three dependence settings (independent, positive factor loadings, mixed-sign loadings), 500-1,000 replicates each, n = 200 and 1,500 rows.
- **Command (to be written):** `python scripts/calibration/eval_correlated_fdr.py --reps 500 --permutations 1000 --out artifacts/e2.json`
- **Under an hour?** Yes, if run without the sandbox **[estimate]**; time 10 replicates first. The existing report card is not a substitute: it pins `m_max` to 1 and a family of one claim (`scripts/calibration/gate_report_card.py`, `pinned_config`).
- **Good result:** mean FDP at or below 0.05 (with its interval) in all three settings, including the mixed-sign one. Then the BH-once-per-run claim has evidence under dependence.
- **Bad result and what it means:** mean FDP clearly above 0.05 in the mixed-sign or shared-column settings. That is a finding, not a failure: it justifies L3 (a joint procedure) and gives the thesis a real contribution. Do not hide it and do not change alpha to make it pass; report it and escalate to the verification owner.

### E3. Blind planted-fact recall with decoy tables (replaces the circular 7 of 7)

- **Question:** Does the analyst layer surface a planted fact in its top 8 figures when the table, the fact and the size are not chosen by the person who built the figures, and how often does it lead with something when nothing is planted?
- **Why:** `analyst_recall.py` has six tables written by the same author as the figures that find them; the doc itself says it "does not show it finds unknown ones". 7 of 7 against 3 of 7 is a regression check, not a result.
- **Design:** A seeded generator draws random tables (sector, size 200-5,000 rows, 12-36 months, 3-6 segments) and plants 0, 1 or 2 facts from a library with a random size (price up volume down, a segment collapses, a season, a 6x row, concentration). Roughly a third of the tables carry no fact (decoys). Someone other than the figure author writes the generator and the matching rule (a teammate, or the assistant under written instructions); the matching rule is frozen before scoring. Score recall at top 8 per fact type and size, and the number of "lead" figures on decoy tables that claim a change larger than a stated materiality.
- **Data:** synthetic and said to be synthetic; add the UCI Online Retail II table as one real, unscored case.
- **Command (to be written):** `python scripts/calibration/eval_blind_recall.py --tables 60 --seed 20261026 --top 8 --out artifacts/e3.json`, reusing `compute_analysis` and `ranked` as `analyst_recall.py` does.
- **Under an hour?** Yes (the Exact tier is code only; minutes) **[estimate]**, apart from writing the generator.
- **Good result:** recall of at least 0.85 for facts at or above a moderate size, a recall-versus-size curve that falls off smoothly, and few strong leads on decoys.
- **Bad result and what it means:** recall near the 3 of 7 baseline on facts the figures were not written for means the earlier 7 of 7 was fitted to the tables; say so in the review before an examiner does. A high decoy lead rate means the ranking weights in `configs/analysis.yaml` (`computed.story_weights`, provisional) are doing too much.

Run order: E2 and E1 in the background first (they are the slow ones), write E3's generator while they run.

Extra, only if time remains: re-run one claim across 20 seeds and report how often its verdict flips (reproducibility of PASS/REJECT near the boundary).

---

## 5. What an analyst would expect and is missing

Checked against the story layout in `PLAN_data_analyst.md` and `ANALYST_LAYER_STATUS.md`:
- **Present:** period change, price/volume/mix, segment growth, concentration, margins, seasonality, row-level outliers, customer view, RFM, segment profiles, data quality.
- **Missing or hidden:** forecast headline (computed, not in the story; 3A item 3), cohort retention (L4), driver tree (L5), anomaly explanation (L6), a single data-quality scorecard (L7), incomplete last period (3A item 2), budget-versus-actual (no budget column convention yet), a plain statement of what was not checked.
- **Do not build** a general "ask anything" analyst to compete with the tools in section 1. The menu is the point.

---

## 6. Do not do before the review

- Do not add a new claim type, model, clustering method or UI section. Every addition is untested surface area that an examiner can poke.
- Do not change a threshold, band, alpha or permutation count to make a demo or an experiment look better (`DESIGN_verification_gateway_v3.md` section 6). A result you tuned is not a result.
- Do not quote "7 of 7" as evidence the system finds true facts. It is a check on tables you wrote.
- Do not quote the 100-replicate rates as calibration. 0.080 with a standard error of 0.027 does not distinguish a correct gate from a slightly liberal one.
- Do not present PASS counts as accuracy. A PASS is "held up on these rows", not "true". Never write "proven" or "correct".
- Do not rely on a live DeepSeek plus Langfuse demo as the only path. It takes minutes, the planner varies run to run, and failing closed is the designed behaviour. Have the offline recording ready.
- Do not run the gate repeatedly on the same dataset hoping for a better outcome; the look ledger exists to catch exactly that, and E1-E3 should be pre-specified.
- Do not claim a head-to-head against ChatGPT, Julius, Hex or PandasAI unless you ran the same tasks on them and saved the outputs.
- Do not use InfiAgent-DABench or DSBench as evidence of uncontaminated performance: the data is public and DeepSeek may have seen it.
- Do not widen the sandbox import list or let the agent write scikit-learn code (`PLAN_data_analyst.md` "Choice B"); that is an AGENTS.md section 4 change needing the verification owner.
- Do not touch `memory_write`, FDR, p-value or sandbox code without the verification owner's approval (AGENTS.md 8.10), and do not merge anything directly to `main`.
- Do not let an AI draft the report prose (AGENTS.md section 7: under 20% AI-generated). Use this file as an outline.
- Do not hide a bad E2 result. A measured weakness with a plan is stronger than a clean number nobody can reproduce.
- Do not describe the synthetic finance table as real data.

---

## 7. Sources (all found by search on 2026-10-24; I read abstracts and summaries, not full papers)

Tools and benchmarks
- InfiAgent-DABench: Evaluating Agents on Data Analysis Tasks. https://arxiv.org/pdf/2401.05507 and https://proceedings.mlr.press/v235/hu24s.html
- DA-Code: Agent Data Science Code Generation Benchmark for Large Language Models. https://arxiv.org/pdf/2410.07331
- DSBench: How Far Are Data Science Agents from Becoming Data Science Experts? https://arxiv.org/pdf/2409.07703
- Benchmarking Data Science Agents (DSEval). https://arxiv.org/pdf/2402.17168
- AutoKaggle: A Multi-Agent Framework for Autonomous Data Science Competitions. https://arxiv.org/pdf/2410.20424
- DS-Agent: Automated Data Science by Empowering Large Language Models with Case-Based Reasoning. https://arxiv.org/pdf/2402.17453
- OpenAI Help Center, "Data analysis with ChatGPT" (article 8437071). https://help.openai.com/en/articles/8437071-chatgpt-advanced-data-analysis
- Hex Magic: use Magic (docs) https://docs.hex.tech/docs/hex-magic/use-magic ; Hex blog on Magic AI https://hex.tech/blog/magic-ai/
- PandasAI docs, getting started. https://docs.pandas-ai.com/v3/getting-started
- Julius AI review (third-party; indicative only). https://unite.ai/julius-ai-review

Agents and false discovery (preprints, summaries only)
- The Agentic Garden of Forking Paths. https://www.alphaxiv.org/abs/2607.01507.md
- Mitigating LLM-based p-Hacking by Preregistering for the Next LLM (Thomas, Gligoric, Shah). https://arxiv.org/abs/2606.27687
- Summary of the p-hacking prompt-framing study. https://hyper.ai/en/stories/67c34dbcea0efe82aef64fcf999af940

Statistics
- Benjamini and Hochberg (1995), Controlling the False Discovery Rate. https://www.dcscience.net/Benjamini-Hochberg-1995-FDR.pdf
- Benjamini and Yekutieli (2001), The control of the false discovery rate in multiple testing under dependency. https://projecteuclid.org/euclid.aos/1013699998
- Romano and Wolf (2005), Exact and Approximate Stepdown Methods for Multiple Hypothesis Testing. https://econ-papers.upf.edu/papers/727.pdf
- Meinshausen, Maathuis, Buhlmann, Asymptotic optimality of the Westfall-Young permutation procedure for multiple testing under dependence. https://ar5iv.labs.arxiv.org/html/1106.2068
- Gelman and Loken, The garden of forking paths (American Scientist, 2014; I did not find the original text, only summaries). https://forrt.org/glossary/english/garden_of_forking_paths/
- Foster and Stine (2008), Alpha-Investing. https://repository.upenn.edu/handle/20.500.14332/47482
- Ramdas, Zrnic, Wainwright, Jordan, SAFFRON. https://arxiv.org/pdf/1802.09098
- Fisher, Online FDR Control for LORD and SAFFRON under Positive, Local Dependence. https://arxiv.org/pdf/2110.08161
- Online multiple hypothesis testing (survey; describes LORD++). https://arxiv.org/pdf/2208.11418
- e-GAI: e-value-based Generalized Alpha-Investing. https://arxiv.org/pdf/2506.01452
- Wang and Ramdas, False discovery rate control with e-values. https://arxiv.org/abs/2009.02824
- Dwork et al., The reusable holdout. https://arxiv.org/pdf/1506.02629.pdf
- Leiner, Duan, Wasserman, Ramdas, Data fission. https://arxiv.org/pdf/2112.11079
- Fithian, Sun, Taylor, Optimal Inference After Model Selection. https://arxiv.org/pdf/1410.2597
- Candes, Fan, Janson, Lv, Panning for Gold: Model-X Knockoffs. https://arxiv.org/pdf/1610.02351
- Simonsohn, Simmons, Nelson, Specification curve analysis (Nature Human Behaviour, 2020). https://link.springer.com/article/10.1038/s41562-020-0912-z

Not cited because I did not find them this session: the original LORD++ paper (Ramdas et al. 2017) and the Del Giudice and Gangestad multiverse paper cited in `DESIGN_verification_gateway_v3.md`. Check those before reusing them.

---

## 8. Limits of this note

- I did not run the code, the tests or any experiment; hour counts and runtimes are guesses.
- Tool comparisons rest on vendor pages and a few third-party reviews, some of them marketing; features change.
- Several 2026 preprints were seen only as summaries; do not cite their numbers without reading them.
- A reviewer who knows the statistics will test the three claims that matter most: BH under dependence (E2), whether recall is more than fitted (E3), and whether the gate buys anything (E1). Those are the places to be ready.
