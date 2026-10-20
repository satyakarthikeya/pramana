"use strict";
const $ = (id) => document.getElementById(id);
let selected = null, poll = null;
const terminal = new Set(["completed", "degraded", "failed"]);
function message(text) { $("message").textContent = text; }
async function request(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Request failed.");
  return body;
}
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function proofButton(proof) {
  const button = node("button", "View proof", "subtle");
  button.type = "button";
  button.onclick = () => { $("proof-text").textContent = JSON.stringify(proof, null, 2);
    $("proof-dialog").showModal(); };
  return button;
}
function number(value) { return value == null ? "—" : Number(value).toPrecision(4); }
function showRows(id, rows) {
  const target = $(id); target.replaceChildren();
  if (!rows.length) { target.textContent = "None in this run."; return; }
  const table = node("table"), head = node("tr");
  ["Claim", "Outcome", "p / q", "Effect", "Score", "Audit"].forEach(t => head.append(node("th", t)));
  const thead = node("thead"); thead.append(head); table.append(thead);
  const tbody = node("tbody");
  rows.forEach(row => {
    const p = row.proof, tr = node("tr");
    [row.claim, p.gate_outcome, `${number(p.p_value)} / ${number(p.q_value)}`,
      `${number(p.effect_size)} ${p.effect_metric || ""}`, number(p.evidence_score)]
      .forEach(value => tr.append(node("td", value)));
    const audit = node("td"); audit.append(proofButton(p)); tr.append(audit); tbody.append(tr);
  });
  table.append(tbody); const wrapper = node("div", undefined, "table-wrap");
  wrapper.append(table); target.append(wrapper);
}
async function recentRuns() {
  const runs = await request("/api/runs"); $("runs").replaceChildren();
  if (!runs.length) $("runs").append(node("p", "No runs yet.", "empty"));
  runs.forEach(run => {
    const button = node("button", run.file_name, "run");
    button.append(node("small", `${run.status} · ${new Date(run.created_at).toLocaleString()}`));
    button.onclick = () => selectRun(run.run_id); $("runs").append(button);
  });
}
async function selectRun(id) {
  selected = id; clearTimeout(poll);
  $("passed-count").textContent = "—"; $("rejected-count").textContent = "—";
  $("passed").replaceChildren(node("p", "Waiting for verification.", "empty"));
  $("rejected").replaceChildren(node("p", "Waiting for verification.", "empty"));
  await updateRun(id);
}
async function updateRun(id) {
  if (id !== selected) return;
  try {
    const run = await request(`/api/runs/${id}`);
    if (id !== selected) return;
    $("run-status").textContent = run.status; $("run-id").textContent = run.run_id;
    $("run-error").textContent = run.error || "";
    if (terminal.has(run.status)) {
      try {
        const result = await request(`/api/runs/${id}/results`);
        if (id !== selected) return;
        showRows("passed", result.verified_insights); showRows("rejected", result.rejected_claims);
        $("passed-count").textContent = result.verified_insights.length;
        $("rejected-count").textContent = result.rejected_claims.length;
        if (result.unverified_candidate_count) message(
          `${result.unverified_candidate_count} candidates lack proofs and are withheld.`);
      } catch (error) {
        $("passed").textContent = "No result snapshot is available.";
        $("rejected").textContent = "No result snapshot is available.";
      }
      await recentRuns();
    } else { poll = setTimeout(() => updateRun(id), 2000); }
  } catch (error) { message(error.message); }
}
$("upload").onsubmit = async (event) => {
  event.preventDefault(); $("start").disabled = true; message("Uploading dataset…");
  try {
    const run = await request("/api/runs", {method:"POST", body:new FormData(event.target)});
    message("Run accepted. Verified results will appear when execution finishes.");
    await recentRuns(); await selectRun(run.run_id);
  } catch (error) { message(error.message); }
  finally { $("start").disabled = false; }
};
function lessons(items) {
  $("lessons").replaceChildren();
  if (!items.length) $("lessons").append(node("p", "No matching verified lessons.", "empty"));
  items.forEach(hit => {
    const lesson = hit.lesson || hit, article = node("article", undefined, "lesson");
    article.append(node("span", "HISTORICAL HINT", "badge pass"), node("p", lesson.text));
    article.append(node("small", `Source run ${lesson.run_id} · ${lesson.proof.insight_id}`));
    if (hit.similarity != null) article.append(node("small", `Similarity ${number(hit.similarity)}`));
    article.append(proofButton(lesson.proof)); $("lessons").append(article);
  });
}
$("search").onsubmit = async (event) => {
  event.preventDefault();
  try { lessons(await request("/api/memory/search", {method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({query:$("memory-query").value, top_k:5})})); }
  catch (error) { $("lessons").textContent = error.message; }
};
$("browse").onclick = async () => {
  try { lessons(await request("/api/memory")); }
  catch (error) { $("lessons").textContent = error.message; }
};
$("close-proof").onclick = () => $("proof-dialog").close();
$("refresh").onclick = () => recentRuns().catch(error => message(error.message));
recentRuns().catch(error => message(error.message));
