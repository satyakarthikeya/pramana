"use strict";
const $ = id => document.getElementById(id);
const terminal = new Set(["completed", "degraded", "failed"]);
let selected = null, poll = null, busy = false;
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function number(value) { return value == null ? "Not measured" : Number(value).toPrecision(4); }
function message(text) { $("message").textContent = text; }
function lock(value) { busy = value; $("start").disabled = value; $("sample").disabled = value; }
async function request(path, options) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { throw new Error("The server returned an unreadable response. Try again."); }
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The request could not be completed.");
  return body;
}
function fallbackReason(proof) {
  return ({supported:"Supported on this dataset, not a causal conclusion.", refuted:"The observed direction does not support the claim.",
    negligible:"The effect was below the configured floor.", inconclusive:"Not significant after correction, or execution failed.",
    not_testable:"The claim could not be tested."})[proof.gate_outcome] || "Not verified.";
}
function proofButton(row) {
  const button = node("button", "View proof", "subtle"); button.type = "button";
  button.onclick = () => {
    const p = row.proof; $("proof-readable").replaceChildren();
    $("proof-readable").append(node("p", row.claim || "Historical verified lesson"));
    const facts = node("dl", undefined, "facts");
    for (const [label, value] of [["Verdict",p.verdict], ["Reason", row.explanation || fallbackReason(p)],
      ["Test", p.test_type || "Not run"], ["Raw p-value", number(p.p_value)], ["Corrected q-value", number(p.q_value)],
      ["Effect", `${number(p.effect_size)} ${p.effect_metric || ""}`], ["Reported effect", `${number(p.reported_effect)} ${p.reported_effect_metric || ""}`],
      ["Available complete rows",row.complete_rows ?? "Not recorded"], ["Random seed",p.seed],
      ["Permutations",row.n_permutations ?? "See stored source"], ["Tested hypotheses in family",p.n_hypotheses_in_batch ?? "Not tested"],
      ["Family",p.bh_family_id]]) { facts.append(node("dt",label),node("dd",String(value))); }
    $("proof-readable").append(facts,node("h3","Executed program"),node("pre",p.falsification_code || "No program executed."));
    $("proof-text").textContent = JSON.stringify(p,null,2);
    $("proof-dialog").querySelector("details").open = false;
    $("proof-dialog").showModal();
  };
  return button;
}
function showRows(id, rows, verdict) {
  const target = $(id); target.replaceChildren();
  if (!rows.length) { target.append(node("p",verdict === "PASS" ? "No verified findings in this run." : "No rejected claims in this run.","empty")); return; }
  rows.forEach(row => {
    if (row.proof.verdict !== verdict) throw new Error("Result verification mismatch. Findings have been withheld.");
    const p = row.proof, card = node("article",undefined,"finding");
    card.append(node("span",verdict === "PASS" ? "VERIFIED FINDING" : "NOT A FINDING",`badge ${verdict === "PASS" ? "pass" : "reject"}`),node("h4",row.claim));
    card.append(node("p",row.explanation || fallbackReason(p)));
    card.append(node("p",`Direction: ${p.observed_direction || "not measured"} · Effect: ${number(p.effect_size)} ${p.effect_metric || ""}${row.effect_strength ? ` · ${row.effect_strength} configured band` : ""}`,"muted"));
    card.append(node("p",`Corrected q: ${number(p.q_value)} · Complete paired rows: ${row.complete_rows ?? "not recorded"}`,"muted"),proofButton(row));
    target.append(card);
  });
}
function showPreview(preview) {
  $("preview-panel").hidden = !preview; if (!preview) return;
  $("preview-summary").textContent = `${preview.rows} cleaned rows · ${preview.columns} columns. Preview and types are not findings.`;
  $("column-preview").replaceChildren();
  preview.detected_columns.forEach(column => $("column-preview").append(node("p",`${column.name}: ${column.role}${column.usable ? "" : " — excluded"}. ${column.reasons.join("; ")}`,"muted")));
  if (preview.omitted_columns) $("column-preview").append(node("p",`${preview.omitted_columns} additional columns omitted from the bounded preview.`));
  $("data-preview").replaceChildren();
  preview.sample_rows.forEach(row => $("data-preview").append(node("pre",Object.entries(row).map(([k,v])=>`${k}: ${v}`).join("\n"))));
}
async function recentRuns() {
  const runs = await request("/api/runs"); $("runs").replaceChildren();
  lock(runs.some(run => !terminal.has(run.status)));
  if (!runs.length) $("runs").append(node("p","No runs yet. Try the synthetic sample.","empty"));
  runs.forEach(run => {
    const button = node("button",run.file_name,"run");
    button.append(node("small",`${run.status} · ${new Date(run.created_at).toLocaleString()}`));
    button.onclick = () => selectRun(run.run_id); $("runs").append(button);
  });
}
function exportsFor(id) {
  for (const format of ["json","csv"]) {
    const link = $(`export-${format}`); link.setAttribute("aria-disabled",String(!id));
    if (id) { link.href = `/api/runs/${id}/export/${format}`; link.setAttribute("download",""); }
    else link.removeAttribute("href");
  }
}
async function selectRun(id) {
  selected = id; clearTimeout(poll); exportsFor(null); showPreview(null);
  $("hints-panel").hidden = true;
  $("passed-count").textContent = "—"; $("rejected-count").textContent = "—";
  $("passed").textContent = "Waiting for complete verification. This may take several minutes.";
  $("rejected").textContent = "Rejections will be listed separately after verification.";
  await updateRun(id);
}
async function updateRun(id) {
  if (id !== selected) return;
  try {
    const run = await request(`/api/runs/${id}`); if (id !== selected) return;
    $("run-status").textContent = run.status; $("run-id").textContent = run.run_id;
    const elapsed = Math.max(0,Math.floor((Date.now()-Date.parse(run.created_at))/1000));
    $("progress").textContent = terminal.has(run.status) ? "Run finished. Each finding below has its proof." : `${run.progress} · ${elapsed}s elapsed · still running`;
    $("run-error").textContent = run.error || ""; showPreview(run.preview);
    $("hints-panel").hidden = !run.past_lessons?.length;
    lessons(run.past_lessons || [],"hints");
    if (terminal.has(run.status)) {
      try {
        const result = await request(`/api/runs/${id}/results`); if (id !== selected) return;
        showRows("passed",result.verified_insights,"PASS"); showRows("rejected",result.rejected_claims,"REJECT");
        $("passed-count").textContent = result.verified_insights.length; $("rejected-count").textContent = result.rejected_claims.length;
        exportsFor(id);
        message(run.status === "completed" ? "Verification complete. Review the findings, proofs and downloads below." : "Run ended with an error. Only proof-bearing results are shown.");
        if (result.unverified_candidate_count) message(`${result.unverified_candidate_count} proposals lack proofs and are withheld.`);
      } catch (error) { $("passed").textContent = "No verified result snapshot is available."; $("rejected").textContent = error.message; }
      await recentRuns();
    } else { lock(true); poll = setTimeout(()=>updateRun(id),2000); }
  } catch (error) { message(`${error.message} Use Refresh to reconnect.`); }
}
async function begin(path,options) {
  lock(true); message("Preparing your run…");
  try { const run = await request(path,options); message("Run accepted. Data preview and progress appear below; please wait for verification."); await recentRuns(); await selectRun(run.run_id); }
  catch (error) { message(error.message); await recentRuns().catch(()=>{}); }
}
$("upload").onsubmit = event => { event.preventDefault(); if (!busy) begin("/api/runs",{method:"POST",body:new FormData(event.target)}); };
$("sample").onclick = () => { if (!busy) begin("/api/runs/sample",{method:"POST"}); };
$("new-run").onclick = () => {
  selected = null; clearTimeout(poll); $("upload").reset(); exportsFor(null); showPreview(null); $("hints-panel").hidden = true;
  $("run-status").textContent = "New analysis"; $("run-id").textContent = ""; $("run-error").textContent = ""; $("progress").textContent = "";
  $("passed").textContent = "Upload a table or try the sample."; $("rejected").textContent = "No run selected.";
  $("passed-count").textContent = "—"; $("rejected-count").textContent = "—";
  message(busy ? "The active run continues. Wait for it to finish; use Refresh to check." : "Ready for another table."); $("dataset").focus();
};
function lessons(items,targetId="lessons") {
  const target = $(targetId); target.replaceChildren();
  if (!items.length) target.append(node("p","No matching verified lessons.","empty"));
  items.forEach(hit => {
    const lesson = hit.lesson || hit;
    if (lesson.proof.verdict !== "PASS") return;
    const card = node("article",undefined,"lesson"); card.append(node("span","HISTORICAL HINT — RE-TEST REQUIRED","badge"),node("p",lesson.text));
    const link = node("a",`Source run ${lesson.run_id}`); link.href = `#run=${encodeURIComponent(lesson.run_id)}`;
    link.onclick = event => { event.preventDefault(); selectRun(lesson.run_id); $("result-title").scrollIntoView(); };
    card.append(link,node("small",`Claim: ${lesson.candidate.claim}`),node("small",`Stored ${new Date(lesson.stored_at).toLocaleString()}`));
    card.append(proofButton({claim:lesson.candidate.claim,proof:lesson.proof})); target.append(card);
    request(`/api/runs/${encodeURIComponent(lesson.run_id)}`).then(run=>card.append(node("small",`Dataset: ${run.file_name}`))).catch(()=>card.append(node("small","Source dataset metadata is not available in this local history.")));
  });
}
$("search").onsubmit = async event => {
  event.preventDefault(); $("lessons").textContent = "Searching verified history…";
  try { lessons(await request("/api/memory/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:$("memory-query").value,top_k:5})})); }
  catch(error) { $("lessons").textContent = error.message; }
};
$("browse").onclick = async () => { $("lessons").textContent = "Loading verified history…"; try { lessons(await request("/api/memory")); } catch(error) { $("lessons").textContent = error.message; } };
$("close-proof").onclick = () => $("proof-dialog").close();
$("refresh").onclick = async () => { try { await recentRuns(); if (selected) await updateRun(selected); } catch(error) { message(error.message); } };
recentRuns().then(()=>{ if (location.hash.startsWith("#run=")) return selectRun(decodeURIComponent(location.hash.slice(5))); }).catch(error=>{ $("runs").textContent = `Could not load runs: ${error.message}`; });
