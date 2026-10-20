// Dependency-free headless acceptance using installed Chrome/Edge and Node 22+.
// This uses synthetic data only; it is not a manual or second-machine sign-off.
import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile, access } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const root = process.cwd();
const base = process.env.PRAMANA_TEST_URL || "http://127.0.0.1:8081";
if (!["127.0.0.1", "localhost"].includes(new URL(base).hostname)) throw new Error("Local test only");
const output = path.join(root,"artifacts/v1-browser");
const data = path.join(root,"data/v1-browser");
await mkdir(output,{recursive:true}); await mkdir(data,{recursive:true});
const candidates = [process.env.PRAMANA_TEST_BROWSER,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"].filter(Boolean);
let executable;
for (const candidate of candidates) { try { await access(candidate); executable=candidate; break; } catch {} }
if (!executable) throw new Error("Set PRAMANA_TEST_BROWSER to an installed Chromium browser");
try {
  await fetch("http://127.0.0.1:9223/json/version");
  throw new Error("Debug port 9223 is already in use; do not attach to another browser");
} catch (error) {
  if (error.message.startsWith("Debug port")) throw error;
}
const browser = spawn(executable,["--headless=new","--remote-debugging-port=9223",
  `--user-data-dir=${path.join(data,"profile")}`,"--no-first-run","--no-default-browser-check","about:blank"],
  {stdio:"ignore",windowsHide:true});
let socket, nextId=0;
const pending = new Map();
const errors = [], results=[];
const assert = (value,message) => { if (!value) throw new Error(message); };
try {
  let pages;
  for (let i=0;i<50;i++) { try { pages=await (await fetch("http://127.0.0.1:9223/json/list")).json(); break; } catch { await delay(300); } }
  const page=pages?.find(item=>item.type === "page"); assert(page,"Headless browser did not expose a page");
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=event=>{
    const message=JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const {resolve,reject,timer}=pending.get(message.id); clearTimeout(timer);pending.delete(message.id);
      message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text);
  };
  const rpc=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++nextId, timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},30000);
    pending.set(id,{resolve,reject,timer}); socket.send(JSON.stringify({id,method,params}));
  });
  const evaluate=async expression=>{
    const result=await rpc("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const wait=async (expression,label,timeout=600000)=>{
    const end=Date.now()+timeout;
    while(Date.now()<end) { if(await evaluate(expression)) return; await delay(1000); }
    throw new Error(`Timed out: ${label}; state=${await evaluate('document.body.innerText')}`);
  };
  await rpc("Page.enable"); await rpc("Runtime.enable");
  await rpc("Browser.setDownloadBehavior",{behavior:"allow",downloadPath:output});
  await rpc("Emulation.setDeviceMetricsOverride",{width:1366,height:1000,deviceScaleFactor:1,mobile:false});
  await rpc("Page.navigate",{url:base});
  await wait('document.readyState === "complete" && typeof document.getElementById("sample")?.onclick === "function" && !document.getElementById("sample").disabled',"startup",30000);
  for(let round=0;round<2;round++) {
    const started=Date.now();
    if(round === 0) await evaluate('document.getElementById("sample").click()');
    else {
      const original=await (await fetch(`${base}/api/sample`)).text();
      const changed=original.trimEnd().split(/\r?\n/).map((line,i)=>{
        if(!i) return line; const cells=line.split(",");cells[1]=String(Number(cells[1])+2);return cells.join(",");
      }).join("\n")+"\n";
      const upload=path.join(data,"second-synthetic.csv");await writeFile(upload,changed);
      await evaluate('document.getElementById("new-run").click()');
      const document=await rpc("DOM.getDocument");
      const element=await rpc("DOM.querySelector",{nodeId:document.root.nodeId,selector:"#dataset"});
      await rpc("DOM.setFileInputFiles",{nodeId:element.nodeId,files:[upload]});
      await evaluate('document.getElementById("upload").requestSubmit()');
    }
    let prior="";
    const end=Date.now()+600000;
    while(Date.now()<end) {
      const state=await evaluate('({status:document.getElementById("run-status").textContent, progress:document.getElementById("progress").textContent, id:document.getElementById("run-id").textContent, error:document.getElementById("run-error").textContent})');
      if(state.progress!==prior) { console.log(JSON.stringify({round:round+1,...state}));prior=state.progress; }
      if(state.status === "completed" && state.id) break;
      assert(!["degraded","failed"].includes(state.status),`Run failed: ${JSON.stringify(state)}`);
      await delay(1500);
    }
    await wait('Number(document.getElementById("passed-count").textContent)>0 && document.getElementById("export-json").hasAttribute("href")',"results");
    const id=await evaluate('document.getElementById("run-id").textContent');
    const result=await (await fetch(`${base}/api/runs/${id}/results`)).json();
    assert(result.run.status==="completed","Completed result required");
    assert(result.candidate_count<=8 && result.unverified_candidate_count===0,"Bounded complete family required");
    assert(result.verified_insights.some(row=>row.claim.includes("age_years") && row.claim.includes("systolic_bp")),"Planted true pair must PASS");
    assert(result.rejected_claims.some(row=>row.claim.includes("moon_phase_pilot")),"Pilot decoy must REJECT");
    if(round) assert(result.run.past_lessons.length>0,"Second dataset must receive historical hints");
    assert(await evaluate('!document.getElementById("preview-panel").hidden'),"Data preview missing");
    await evaluate('document.querySelector("#passed button").click()');
    assert(await evaluate('document.getElementById("proof-dialog").open && document.getElementById("proof-readable").textContent.includes("Random seed")'),"Readable proof missing");
    assert(await evaluate('!document.querySelector("#proof-dialog details").open'),"Raw proof must start collapsed");
    await evaluate('document.querySelector("#proof-dialog details summary").click()');
    assert(await evaluate('document.getElementById("proof-text").textContent.includes("falsification_code")'),"Raw proof toggle missing");
    await evaluate('document.getElementById("close-proof").click()');
    for(const format of ["json","csv"]) await evaluate(`document.getElementById("export-${format}").click()`);
    for(const format of ["json","csv"]) {
      const filename=path.join(output,`pramana-${id}.${format}`);
      let body;
      for(let i=0;i<30;i++) {try{body=await readFile(filename,"utf8");break;}catch{await delay(300);}}
      assert(body?.length>0,`${format} browser download missing`);
      if(format==="json") assert(JSON.parse(body).verified_insights.length>0,"JSON download invalid");
      else assert(body.startsWith("insight_id,claim,is_finding"),"CSV header invalid");
    }
    await evaluate('document.getElementById("browse").click()');
    await wait('document.querySelectorAll("#lessons .lesson").length>0',"memory");
    const memory=await (await fetch(`${base}/api/memory`)).json();
    assert(memory.every(lesson=>lesson.proof.verdict==="PASS"),"Memory contains a non-PASS lesson");
    // Exact stored text guarantees a match; an approximate query may honestly
    // return no results at the configured similarity cutoff, which is not a defect.
    await evaluate(`document.getElementById("memory-query").value=${JSON.stringify(memory[0].text)};document.getElementById("search").requestSubmit()`);
    await wait('document.querySelectorAll("#lessons .lesson").length>0',"memory search");
    for(const width of [1366,390]) {
      await rpc("Emulation.setDeviceMetricsOverride",{width,height:1000,deviceScaleFactor:1,mobile:false});
      await evaluate('document.getElementById("passed").scrollIntoView()');
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`Horizontal overflow at ${width}px`);
      const image=await rpc("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
      await writeFile(path.join(output,`round-${round+1}-${width}.png`),Buffer.from(image.data,"base64"));
    }
    await evaluate('document.getElementById("dataset").focus()');
    await rpc("Input.dispatchKeyEvent",{type:"keyDown",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
    await rpc("Input.dispatchKeyEvent",{type:"keyUp",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
    assert(await evaluate('document.activeElement.id === "question"'),"Keyboard focus did not reach the question");
    results.push({round:round+1,run_id:id,elapsed_seconds:(Date.now()-started)/1000,
      pass_count:result.verified_insights.length,reject_count:result.rejected_claims.length,
      planted_pair_pass:true,pilot_decoy_reject:true,pass_only_memory:true});
  }
  assert(errors.length===0,`Browser exceptions: ${errors}`);
  await writeFile(path.join(output,"acceptance.json"),JSON.stringify({headless:true,manual:false,
    second_machine:false,base,results,browser_exceptions:errors},null,2));
  console.log(JSON.stringify({passed:true,results,output}));
  await rpc("Browser.close").catch(()=>{});
} finally {socket?.close();browser.kill();}
