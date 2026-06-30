const PROJ_KEYS=Object.keys(ALL_DATA);

// Cloudflare Access — decode CF_Authorization JWT to get current user's email
// JWT payload is the second base64url segment; no signature verification needed client-side
(function(){
  try{
    const jwt=(document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('CF_Authorization='))||'').replace('CF_Authorization=','');
    if(!jwt)return;
    const payload=JSON.parse(atob(jwt.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
    const email=(payload.email||'').toLowerCase();
    if(!email)return;
    window._cfUserEmail=email;
    // Derive slug from email local part: "hugh.odwyer@datamars.com" → "hugh odwyer"
    window._cfUserSlug=email.split('@')[0].replace('.',' ');
  }catch(ex){}
})();

// Persisted state via URL hash — format: #PROJ:tab  e.g. #DLK:trends
// Hash survives refresh automatically; no storage API required.
const _OOS_ONLY_TABS=["oosopen","oos"];
(function _parseHash(){
  const [p,t]=(location.hash||"").replace("#","").split(":");
  window._hsProj=ALL_DATA[p]?p:null;
  window._hsTab =t||"overview";
})();
const _lsProj=window._hsProj;
const _lsTab =window._hsTab;

// Active project state — updated by switchProject()
let AP=PROJ_KEYS[0];
let QS={}, PROJ_KEY="", PROJ_DISPLAY="", BOARD_ID="", PROJ_USE_SP=false, PROJ_USE_OOS=true;
let PROJ_REFRESH_WEBHOOK="", PROJ_REFRESH_DATA_WEBHOOK="", PROJ_REFRESH_REQUEST_WEBHOOK="", PROJ_CAPACITY_UPDATE_WEBHOOK="";
const _refreshBtn=document.getElementById("refresh-btn");
let ordered=[];
let cur="";
let curTab="overview";
let trendWindow=4; // rolling quarters shown in trend charts
let activeSprint=null; // null = all sprints; sprint ID string = filtered to that sprint
let trendsMode="quarterly"; // "quarterly" or "sprint"

function switchProject(p,skipRender){
  AP=p;
  const pd=ALL_DATA[p];
  QS=pd.qs||{};
  PROJ_KEY=pd.proj_key||p;
  PROJ_DISPLAY=pd.display||p;
  BOARD_ID=pd.board_id||"";
  activeSprint=null;  // reset to "All sprints" whenever the project changes

  // Prefer project-level flag (set by Python main()); fall back to first available
  // quarter's kpis.use_story_points for HTMLs generated before that field existed.
  const _firstKpis=Object.values(pd.qs||{})[0]?.kpis||{};
  PROJ_USE_SP=!!(pd.use_story_points??_firstKpis.use_story_points??false);
  PROJ_USE_OOS=!!(pd.use_oos??true);
  PROJ_REFRESH_WEBHOOK=pd.refresh_webhook||"";
  PROJ_REFRESH_DATA_WEBHOOK=pd.refresh_data_webhook||"";
  PROJ_REFRESH_REQUEST_WEBHOOK=pd.refresh_request_webhook||"";
  PROJ_CAPACITY_UPDATE_WEBHOOK=pd.capacity_update_webhook||"";
  if(typeof updateRefreshBtn==="function")updateRefreshBtn();
  ordered=Object.keys(QS).sort((a,b)=>{
    const[qa,ya]=a.split(" ");const[qb,yb]=b.split(" ");
    return(+yb-+ya)||(+qb[1]-+qa[1]);
  });
  cur=ordered[0]||"";
  // Update project tab UI
  document.querySelectorAll(".proj-tab").forEach(t=>t.classList.toggle("active",t.dataset.proj===p));
  // Update logo text
  const ln=document.getElementById("proj-name");if(ln)ln.textContent=PROJ_DISPLAY;
  // Rebuild quarter dropdown and sprint label
  document.getElementById("q-input").value=cur;
  buildOpts("");
  updateSprintLabel();
  if(!skipRender&&cur){
    const _t=(!PROJ_USE_OOS&&_OOS_ONLY_TABS.includes(curTab))?"overview":curTab;
    render(cur,_t);
  }
}

/* ---- Escape ---- */
function e(s){return String(s??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}

/* ---- Notes staleness notice ---- */
function notesStaleNotice(notesGeneratedAt, dataAsOf){
  if(!dataAsOf)return"";
  const dat=new Date(dataAsOf);
  if(isNaN(dat.getTime()))return"";
  const fmtTs=d=>d.toLocaleString(undefined,{day:"numeric",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",timeZoneName:"short"});
  if(!notesGeneratedAt)return`<div class="alert alert-info" style="font-size:12px;opacity:0.85">ℹ AI notes: last update unknown — will refresh on next full run.</div>`;
  const nts=new Date(notesGeneratedAt);
  if(isNaN(nts.getTime()))return"";
  if(dat-nts<60000)return"";
  let msg=`AI notes last updated: ${fmtTs(nts)}.`;
  const refreshHours=ALL_DATA[AP]?.notes_refresh_hours;
  if(refreshHours){
    const nextRun=new Date(nts.getTime()+refreshHours*3600000);
    const now=new Date();
    if(nextRun>now){
      const diffMs=nextRun-now;
      const diffH=Math.round(diffMs/3600000);
      const diffD=Math.round(diffMs/86400000);
      const label=diffH<24?`~${diffH}h`:`~${diffD}d`;
      msg+=` Next AI refresh: in ${label} (${fmtTs(nextRun)}).`;
    }
  }
  if(!refreshHours||(new Date(nts.getTime()+refreshHours*3600000)<=new Date())){
  if(NOTES_REFRESH_TIME&&NOTES_REFRESH_TIME.tz){
    try{
      const {hour,minute,tz}=NOTES_REFRESH_TIME;
      const min=minute||0;
      const now=new Date();
      const todayInSrcTz=new Intl.DateTimeFormat("en-CA",{timeZone:tz}).format(now);
      const candidate=new Date(`${todayInSrcTz}T${String(hour).padStart(2,"0")}:${String(min).padStart(2,"0")}:00`);
      const srcWall=new Intl.DateTimeFormat("en-CA",{timeZone:tz,hour:"2-digit",minute:"2-digit",hour12:false}).format(candidate);
      const [srcH,srcM]=srcWall.split(":").map(Number);
      const diffMs=((hour-srcH)*60+(min-srcM))*60000;
      let runUtc=new Date(candidate.getTime()+diffMs);
      if(runUtc<=now) runUtc=new Date(runUtc.getTime()+86400000);
      msg+=` Next AI refresh: ${fmtTs(runUtc)}.`;
    }catch(_){}
  }}
  return`<div class="alert alert-info" style="font-size:12px;opacity:0.85">ℹ ${msg}</div>`;
}

/* ---- Date formatting ---- */
function fmtDate(s,short){
  if(!s)return"";
  const d=new Date(s+"T12:00:00");
  return short
    ?d.toLocaleDateString("en-GB",{day:"numeric",month:"short"})
    :d.toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"});
}

/* ---- Badge helpers ---- */
function scls(cat){return cat==="done"?"bd":cat==="indeterminate"?"bi":"bt"}
function tcls(t){return t==="Bug"?"bbug":t==="Story"?"bstory":t==="Task"?"btask":"bt"}
function pcls(p){if(!p)return"bt";p=p.toLowerCase();return(p==="highest"||p==="high")?"bhi":p==="medium"?"bmed":"blo"}

/* ---- Quarter dropdown ---- */
// Track which year groups have been manually toggled open/closed
const _yrOpen={};
function _curYr(){return cur?(cur.split(" ")[1]||""):""}

function buildOpts(filter){
  const lc=(filter||"").toLowerCase();
  const el=document.getElementById("q-opts");
  const filtered=ordered.filter(q=>q.toLowerCase().includes(lc));
  if(!filtered.length){el.innerHTML=`<div class="q-opt" style="color:var(--muted);cursor:default">No results</div>`;return;}

  // When searching, collapse into a flat list (no accordion — results could span years)
  if(lc){
    el.innerHTML=filtered.map(q=>{
      const d=QS[q];const sc=q===cur?" sel":"";const n=(d.sprints||[]).length;
      return`<div class="q-opt${sc}" data-q="${e(q)}">${e(q)}<span class="q-badge">${n} sprint${n!==1?"s":""}</span></div>`;
    }).join("");
    el.querySelectorAll(".q-opt[data-q]").forEach(o=>{
      o.addEventListener("click",()=>{const t=curTab;cur=o.dataset.q;closeDd();render(cur,t);});
    });
    return;
  }

  // Group by year — current year open by default, older years collapsed
  const byYr={};
  filtered.forEach(q=>{const yr=q.split(" ")[1]||"?";(byYr[yr]=byYr[yr]||[]).push(q);});
  const curYr=_curYr();
  el.innerHTML=Object.keys(byYr).sort((a,b)=>b-a).map(yr=>{
    // Open if current year, or previously toggled open
    const open=(_yrOpen[yr]!==undefined)?_yrOpen[yr]:(yr===curYr);
    const arrow=open?"▾":"▸";
    const opts=byYr[yr].sort((a,b)=>+b[1]-+a[1]).map(q=>{
      const d=QS[q];const sc=q===cur?" sel":"";const n=(d.sprints||[]).length;
      return`<div class="q-opt${sc}" data-q="${e(q)}">${e(q)}<span class="q-badge">${n} sprint${n!==1?"s":""}</span></div>`;
    }).join("");
    return`<div class="q-yr-hdr" data-yr="${yr}"><span>${yr}</span><span class="q-yr-arrow">${arrow}</span></div>`
          +`<div class="q-yr-group${open?"":" collapsed"}" data-yrg="${yr}">${opts}</div>`;
  }).join("");

  // Year header toggle
  el.querySelectorAll(".q-yr-hdr").forEach(h=>{
    h.addEventListener("click",ev=>{
      ev.stopPropagation();
      const yr=h.dataset.yr;
      const grp=el.querySelector(`.q-yr-group[data-yrg="${yr}"]`);
      const nowOpen=grp.classList.toggle("collapsed");
      _yrOpen[yr]=!nowOpen;
      h.querySelector(".q-yr-arrow").textContent=nowOpen?"▸":"▾";
    });
  });

  el.querySelectorAll(".q-opt[data-q]").forEach(o=>{
    o.addEventListener("click",()=>{const t=curTab;cur=o.dataset.q;closeDd();render(cur,t);});
  });
}
function openDd(){document.getElementById("q-dd").classList.add("open");buildOpts("");document.getElementById("q-search").value="";document.getElementById("q-search").focus();}
function closeDd(){document.getElementById("q-dd").classList.remove("open");document.getElementById("q-input").value=cur;}
document.getElementById("q-input").addEventListener("click",()=>{document.getElementById("q-dd").classList.contains("open")?closeDd():openDd();});
document.getElementById("q-search").addEventListener("input",function(){buildOpts(this.value);});
document.addEventListener("click",ev=>{if(!ev.target.closest(".qs"))closeDd();});

/* ---- Project tabs — built from ALL_DATA keys ---- */
(function(){
  const container=document.getElementById("proj-tabs");
  PROJ_KEYS.forEach(p=>{
    const btn=document.createElement("button");
    btn.className="proj-tab";
    btn.dataset.proj=p;
    btn.textContent=ALL_DATA[p].display||p;
    btn.addEventListener("click",()=>switchProject(p));
    container.appendChild(btn);
  });
  // Hide tab row if only one project
  if(PROJ_KEYS.length<2)container.style.display="none";
  // Initialise state only — render happens after all const definitions below
  switchProject((ALL_DATA[_lsProj]?_lsProj:PROJ_KEYS[0]),true);
})();

/* ---- Current sprint label — updated on project switch ---- */
function updateSprintLabel(){
  const now=new Date();
  const liveLabel=`Q${Math.floor(now.getMonth()/3)+1} ${now.getFullYear()}`;
  const liveData=QS[liveLabel];
  const activeSprint=liveData?(liveData.sprints||[]).find(s=>s.state==="active"):null;
  document.getElementById("hdr-sprint").textContent=activeSprint?activeSprint.name:"";
}

/* ---- Sprint selector ---- */
function buildSprintSelector(sprints){
  const bar=document.getElementById("sprint-sel-bar");
  if(!bar)return;
  let sel=bar.querySelector(".sprint-sel");
  if(!sprints||!sprints.length){if(sel)sel.remove();return;}
  const active=activeSprint;
  const btns=[{id:null,label:"All"},...sprints.map(s=>({id:String(s.id),label:s.name.replace(/.*Sprint\s*/i,"S")}))];
  const html='<div class="sprint-sel">'+btns.map(b=>{
    const cls="ssb"+(active===b.id?" active":"");
    const onclick=b.id===null?"setActiveSprint(null)":"setActiveSprint('"+b.id+"')";
    return'<button class="'+cls+'" onclick="'+onclick+'">'+b.label+"</button>";
  }).join("")+"</div>";
  if(sel){sel.outerHTML=html;}else{bar.insertAdjacentHTML("afterbegin",html);}
}
function setActiveSprint(id){activeSprint=id;render(cur,curTab);}


/* ---- Refresh button ---- */
function updateRefreshBtn(){
  if(!_refreshBtn)return;
  _refreshBtn.style.display=PROJ_REFRESH_WEBHOOK?"":"none";
}

(function(){
  if(!_refreshBtn)return;
  const COOLDOWN_MS=60*60*1000;

  function sk(){return"last_manual_refresh_"+AP.toLowerCase();}
  function fmtTime(ts){
    const d=new Date(ts);
    return String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0");
  }
  function showModal(title,msg,extraBtn){
    document.getElementById("refresh-modal-title").textContent=title;
    document.getElementById("refresh-modal-msg").textContent=msg;
    const modal=document.getElementById("refresh-modal");
    const existing=modal.querySelector(".modal-extra-btn");
    if(existing)existing.remove();
    if(extraBtn){
      const b=document.createElement("button");
      b.className="modal-close modal-extra-btn";
      b.style.cssText="margin-right:8px;background:var(--blue-bg,#eff6ff);color:var(--blue-text,#1d4ed8);border:1px solid #bfdbfe";
      b.textContent=extraBtn.label;
      b.onclick=()=>{modal.classList.remove("open");extraBtn.action();};
      modal.querySelector(".modal-close").insertAdjacentElement("beforebegin",b);
    }
    modal.classList.add("open");
  }

  async function getLastRefresh(){
    try{
      const r=await fetch("./data/last_refresh.json?_="+Date.now());
      if(r.ok){
        const d=await r.json();
        const ts=d[AP.toLowerCase()];
        if(ts){
          const fileTs=new Date(ts).getTime();
          const localTs=+localStorage.getItem(sk())||0;
          return Math.max(fileTs,localTs);
        }
      }
    }catch(_){}
    return +localStorage.getItem(sk())||0;
  }

  _refreshBtn.addEventListener("click",async()=>{
    if(!PROJ_REFRESH_WEBHOOK)return;
    const last=await getLastRefresh();
    const now=Date.now();
    if(now-last<COOLDOWN_MS){
      const dataBtn=PROJ_REFRESH_DATA_WEBHOOK?{
        label:"Refresh data only",
        action:()=>fetch(PROJ_REFRESH_DATA_WEBHOOK,{method:"POST",mode:"no-cors"})
      }:null;
      showModal(
        "Too soon for a full refresh",
        `The dashboard was last fully refreshed (data + AI notes) at ${fmtTime(last)}. Full refreshes are limited to once per hour — try again at ${fmtTime(last+COOLDOWN_MS)}. Board data updates automatically every 10 minutes.`,
        dataBtn
      );
      return;
    }
    localStorage.setItem(sk(),String(now));
    _refreshBtn.disabled=true;
    _refreshBtn.textContent="↻ Refreshing…";

    const banner=document.getElementById("refresh-banner");
    const triggerTs=now;
    let elapsed=0;
    let pollTimer=null;
    let notFoundCount=0;
    function fmtElapsed(s){return s<60?s+"s":Math.floor(s/60)+"m "+String(s%60).padStart(2,"0")+"s";}
    function setBanner(cls,html){
      banner.className=cls;banner.innerHTML=html;banner.style.display="block";
    }
    function startElapsedTick(){
      return setInterval(()=>{elapsed++;setBanner("",`↻ Refreshing… ${fmtElapsed(elapsed)} elapsed`);},1000);
    }
    async function pollForComplete(){
      try{
        const r=await fetch("./data/last_refresh.json?_="+Date.now());
        if(r.status===404){notFoundCount++;if(notFoundCount>=3)clearInterval(pollTimer);return;}
        notFoundCount=0;
        if(r.ok){
          const d=await r.json();
          const ts=d[AP.toLowerCase()];
          if(ts&&new Date(ts).getTime()>triggerTs){
            clearInterval(elapsedTimer);clearInterval(pollTimer);
            setBanner("done","✓ Done — reloading…");
            setTimeout(()=>location.reload(),1500);
            return;
          }
        }
      }catch(_){}
    }
    const elapsedTimer=startElapsedTick();
    setBanner("","↻ Refreshing… 0s elapsed");
    pollTimer=setInterval(pollForComplete,10000);
    setTimeout(()=>{
      clearInterval(pollTimer);clearInterval(elapsedTimer);
      if(banner.className!=="done"){
        setBanner("","↻ Still working… reload in a moment to check");
        _refreshBtn.textContent="↻ Refresh";_refreshBtn.disabled=false;
      }
    },5*60*1000);

    fetch(PROJ_REFRESH_WEBHOOK,{method:"POST",mode:"no-cors"})
      .then(()=>{_refreshBtn.textContent="↻ Refresh";_refreshBtn.disabled=false;})
      .catch(err=>{
        clearInterval(elapsedTimer);clearInterval(pollTimer);
        localStorage.removeItem(sk());
        if(banner)banner.style.display="none";
        showModal(
          "Refresh failed",
          `Could not reach Home Assistant${err.message?` (${err.message})`:""}. Check that HA is running and the webhook is configured. You can try again now.`
        );
        _refreshBtn.textContent="↻ Refresh";_refreshBtn.disabled=false;
      });
  });
})();

/* ---- Request refresh — 5 quick clicks on the "Updated" timestamp in the navbar ---- */
(function(){
  const el=document.getElementById("as-of");
  if(!el)return;
  let clicks=0,timer=null;
  el.style.cursor="default";
  el.addEventListener("click",()=>{
    if(!PROJ_REFRESH_REQUEST_WEBHOOK)return;
    clicks++;
    clearTimeout(timer);
    if(clicks>=5){
      clicks=0;
      fetch(PROJ_REFRESH_REQUEST_WEBHOOK,{method:"POST",mode:"no-cors"});
      const prev=el.textContent;
      el.textContent="↻ Request sent";
      setTimeout(()=>el.textContent=prev,3000);
    }else{
      timer=setTimeout(()=>clicks=0,2000);
    }
  });
})();

/* ---- Header height sync ---- */
function _syncHdr(){
  const h=document.getElementById("site-header")?.offsetHeight;
  if(h)document.documentElement.style.setProperty("--hdr",h+"px");
}
new ResizeObserver(_syncHdr).observe(document.getElementById("site-header"));

/* ---- Back to top ---- */
window.addEventListener("scroll",()=>{document.getElementById("btt").classList.toggle("vis",window.scrollY>300);},{passive:true});

/* ---- Tab switching ---- */
function showTab(id){
  curTab=id;
  history.replaceState(null,"",location.pathname+location.search+"#"+AP+":"+id);
  document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.dataset.tab===id));
  document.querySelectorAll(".tab-pane").forEach(p=>p.classList.toggle("active",p.dataset.pane===id));
  const bar=document.getElementById("sprint-sel-bar");
  if(bar)bar.style.display=id==="trends"?"none":"";
  const ttb=document.getElementById("trends-toolbar");
  if(ttb)ttb.style.display=id==="trends"?"":"none";
  window.scrollTo({top:0,behavior:"instant"});
}

/* ---- Table builder ---- */
let _tid=0;
function mkTable(cols,rows,jiraUrl){
  const fid="f"+(_tid++);const bid="b"+_tid;const cid="c"+_tid;
  const toolbar=`<div class="ttb">
    <input class="tf" id="${fid}" placeholder="Filter…">
    <span class="tc" id="${cid}">${rows.length} item${rows.length!==1?"s":""}</span>
    ${jiraUrl?`<a class="jl" href="${e(jiraUrl)}" target="_blank">Open in Jira ↗</a>`:""}
  </div>`;
  const head=cols.map((c,i)=>`<th data-i="${i}">${e(c.h)}<span class="si"></span></th>`).join("");
  const body=rows.length
    ?rows.map(r=>`<tr class="${r._rowCls||''}">${cols.map(c=>`<td>${c.r(r)}</td>`).join("")}</tr>`).join("")
    :`<tr class="er"><td colspan="${cols.length}">No items</td></tr>`;
  const html=`<div class="tw">${toolbar}<div class="tw-body"><table><thead><tr>${head}</tr></thead><tbody id="${bid}">${body}</tbody></table></div></div>`;
  setTimeout(()=>{
    const fi=document.getElementById(fid);const tb=document.getElementById(bid);const ct=document.getElementById(cid);
    if(!fi||!tb)return;
    fi.addEventListener("input",()=>{
      const lc=fi.value.toLowerCase();let vis=0;
      tb.querySelectorAll("tr:not(.er)").forEach(r=>{const show=r.textContent.toLowerCase().includes(lc);r.style.display=show?"":"none";if(show)vis++;});
      if(ct)ct.textContent=fi.value?`${vis} of ${rows.length}`:`${rows.length} item${rows.length!==1?"s":""}`;
    });
    let ss={};
    tb.closest("table").querySelectorAll("thead th").forEach(th=>{
      th.addEventListener("click",()=>{
        const i=+th.dataset.i;const asc=ss[i]!==true;ss={};ss[i]=asc;
        tb.closest("table").querySelectorAll(".si").forEach(s=>s.textContent="");
        th.querySelector(".si").textContent=asc?" ▲":" ▼";
        const rs=Array.from(tb.querySelectorAll("tr:not(.er)"));
        rs.sort((a,b)=>{const av=a.cells[i]?.textContent.trim()??"";const bv=b.cells[i]?.textContent.trim()??"";return asc?av.localeCompare(bv,undefined,{numeric:true}):bv.localeCompare(av,undefined,{numeric:true});});
        rs.forEach(r=>tb.appendChild(r));
      });
    });
  },0);
  return html;
}

/* ---- Column helpers ---- */
function issueCols(extra){
  return[
    {h:"Key",     r:r=>`<a class="ik" href="${e(r.url)}" target="_blank">${e(r.key)}</a>`},
    {h:"Type",    r:r=>`<span class="b ${tcls(r.type)}">${e(r.type)}</span>`},
    {h:"Summary", r:r=>`<div class="is" title="${e(r.summary)}">${e(r.summary)}</div>`},
    {h:"Assignee",r:r=>e(r.assignee)},
    ...(extra||[]),
    {h:"Status",  r:r=>`<span class="b ${scls(r.status_cat)}">${e(r.status)}</span>`},
  ];
}
const priCol={h:"Priority",r:r=>r.priority?`<span class="b ${pcls(r.priority)}">${e(r.priority)}</span>`:"&mdash;"};
const lblCol={h:"Labels",  r:r=>(r.labels||[]).filter(l=>l!=="Out_Of_Sprint").map(l=>`<span class="b bt">${e(l)}</span>`).join(" ")||"&mdash;"};

/* ---- Pane wrapper ---- */
function pane(id,content){
  return`<div class="tab-pane" data-pane="${id}">${content}</div>`;
}

/* ---- Excluded-summary KPI adjustment ---- */
// Adds excluded-summary stats back into a KPI object when showOn is true.
// Works for both quarter-level (pass kpis.excl_summary_stats) and sprint-level (pass sp.excl_summary_stats).
function _adjKpis(base,exclStats,showOn){
  if(!showOn||!exclStats||!exclStats.item_count)return base;
  const newTotal    =(base.total||0)+(exclStats.item_count||0);
  const newCompleted=(base.completed||0)+(exclStats.completed_count||0);
  const newBugs     =(base.bugs||0)+(exclStats.bug_count||0);
  const newStories  =(base.stories||0)+(exclStats.story_count||0);
  const newTasks    =(base.tasks||0)+(exclStats.task_count||0);
  const newOosTotal =(base.oos_total||0)+(exclStats.oos_count||0);
  const newOosOpen  =(base.oos_open||0)+(exclStats.oos_open_count||0);
  const bc=base.completed||0,ec=exclStats.completed_count||0;
  const adjAvgCycle =(bc+ec)>0?Math.round(((base.avg_cycle_days||0)*bc+(exclStats.avg_cycle_days||0)*ec)/(bc+ec)*10)/10:(base.avg_cycle_days||0);
  const adjMedCycle =(bc+ec)>0?Math.round(((base.med_cycle_days||0)*bc+(exclStats.med_cycle_days||0)*ec)/(bc+ec)*10)/10:(base.med_cycle_days||0);
  const tl=Math.round(((base.time_logged_h||0)+(exclStats.logged_h||0))*10)/10;
  const te=Math.round(((base.time_estimated_h||0)+(exclStats.estimated_h||0))*10)/10;
  const acc=(tl>0&&te>0)?Math.round(Math.min(tl,te)/Math.max(tl,te)*100):0;
  const vari=te>0?Math.round((tl-te)/te*100):0;
  const adjAs=(base.assignee_stats||[]).map(a=>{
    const d=exclStats.by_dev&&exclStats.by_dev[a.name];
    if(!d)return a;
    const nl=Math.round((a.logged_h+(d.logged_h||0))*10)/10;
    const ne=Math.round((a.estimated_h+(d.estimated_h||0))*10)/10;
    const nc=a.completed+(d.completed||0);
    return{...a,logged_h:nl,estimated_h:ne,total:a.total+(d.total||0),completed:nc,completion_rate:(a.total+(d.total||0))?Math.round(nc/(a.total+(d.total||0))*100):0};
  });
  const existingNames=new Set(adjAs.map(a=>a.name));
  const extraDevs=Object.entries(exclStats.by_dev||{})
    .filter(([n])=>!existingNames.has(n))
    .map(([n,d])=>({name:n,account_id:'',is_team:false,team_period:null,
      total:d.total,completed:0,logged_h:d.logged_h,estimated_h:d.estimated_h,
      sp_total:0,sp_completed:0,completion_rate:0}));
  return{...base,
    total:newTotal,
    completed:newCompleted,
    completion_rate:newTotal?Math.round(newCompleted/newTotal*100):0,
    bugs:newBugs,stories:newStories,tasks:newTasks,
    bug_pct:newTotal?Math.round(newBugs/newTotal*100):0,
    oos_total:newOosTotal,oos_open:newOosOpen,
    avg_cycle_days:adjAvgCycle,med_cycle_days:adjMedCycle,
    time_logged_h:tl,time_estimated_h:te,
    estimate_accuracy_pct:acc,estimate_variance_pct:vari,
    no_estimate_count:(base.no_estimate_count||0)+(exclStats.no_estimate_count||0),
    no_estimate_pct:newTotal?(Math.round(((base.no_estimate_count||0)+(exclStats.no_estimate_count||0))/newTotal*100)):0,
    no_log_count:(base.no_log_count||0)+(exclStats.no_log_count||0),
    assignee_stats:[...adjAs,...extraDevs],
  };
}

/* ---- Main render ---- */
function render(qk,activeTab){
  const D=QS[qk];
  if(cur!==qk){activeSprint=null;trendsMode="quarterly";}
  cur=qk;
  document.getElementById("q-input").value=qk;
  document.title=PROJ_DISPLAY+" Quarter Dashboard - "+qk;

  if(!D){document.getElementById("dash").innerHTML='<div class="nodata">No data for '+e(qk)+'</div>';return;}
  const {kpis,notes,sprints}=D;
  buildSprintSelector(sprints);
  const sp=activeSprint?(kpis.per_sprint||{})[activeSprint]||null:null;
  const iss=kpis.issues||{};
  const jb=kpis.jira_base||"";
  const verIds=kpis.version_ids||{};
  let oa=activeSprint&&sp?(sp.oos_open||0):kpis.oos_open;
  const ids=(kpis.sprint_ids||[]).join(", ");
  const base=`project = ${PROJ_KEY} AND sprint in (${ids})`;

  (function(){
    const raw=kpis.as_of||"";
    let display=raw;
    if(raw){
      const d=new Date(raw);
      if(!isNaN(d.getTime()))
        display=d.toLocaleString(undefined,{day:"numeric",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",timeZoneName:"short"});
    }
    document.getElementById("as-of").textContent="Updated: "+display;
  })();

  /* Version column — needs jb and verIds closure */
  const verCol={h:"Fix Ver.",r:r=>{
    if(!(r.fix_versions||[]).length)return"—";
    return`<div class="vv">${r.fix_versions.map(v=>{
      const vid=verIds[v];
      if(vid&&jb){const url=`${jb}/projects/${PROJ_KEY}/versions/${vid}/tab/release-report-all-issues`;return`<a class="b bstory vlink" href="${e(url)}" target="_blank">${e(v)}</a>`;}
      return`<span class="b bstory">${e(v)}</span>`;
    }).join("")}</div>`;
  }};

  /* Column sets */
  const allCols =issueCols([priCol,verCol,lblCol]);
  const oosCols =issueCols([priCol,lblCol]);
  const relCols =issueCols([verCol,lblCol]);
  /* In Progress columns — Key cell includes ⓘ icon for cross-quarter carry-overs */
  const ipCols=[
    {h:"Key",r:r=>{
      const lnk=`<a class="ik" href="${e(r.url)}" target="_blank">${e(r.key)}</a>`;
      if(r.resolved_quarter){
        const sprint=r.resolved_sprint?` · ${r.resolved_sprint}`:"";
        const tip=`Completed in ${r.resolved_quarter}${sprint} · ${r.resolved_date||''}`;
        return lnk+`<span class="ri" data-tip="${e(tip)}">&#x2139;</span>`;
      }
      if(r.origin_quarter&&isCurrentQ){
        const qc=r.quarters_carried||1;
        const cls=qc>=2?"ci-red":"ci";
        const tip=`Carry-over from ${r.origin_quarter} · in progress since ${r.ip_date||''} (${qc} quarter${qc>1?"s":""})`
        return lnk+`<span class="${cls}" data-tip="${e(tip)}">&#x2139;</span>`;
      }
      return lnk;
    }},
    {h:"Type",    r:r=>`<span class="b ${tcls(r.type)}">${e(r.type)}</span>`},
    {h:"Summary", r:r=>`<div class="is" title="${e(r.summary)}">${e(r.summary)}</div>`},
    {h:"Assignee",r:r=>e(r.assignee)},
    priCol,
    {h:"Status",  r:r=>`<span class="b ${scls(r.status_cat)}">${e(r.status)}</span>`},
  ];

  /* Jira URLs per section */
  function jUrl(jql){return jb?`${jb}/issues/?jql=${encodeURIComponent(jql)}`:null;}

  const isCurrentQ=!!(sprints||[]).find(s=>s.state==="active");

  /* Sprint table */
  const sRows=(sprints||[]).slice().reverse().map(s=>{
    const start=fmtDate(s.start_date,true);const end=fmtDate(s.end_date,false);
    const dates=start&&end?`${start} — ${end}`:start?`From ${start}`:"";
    const chip=`<span class="chip chip-${e(s.status_color)}">${e(s.status_label)}</span>`;
    const surl=(jb&&s.state==="active")?`${jb}/jira/software/projects/${PROJ_KEY}/boards/${e(kpis.board_id||"")}?sprint=${e(String(s.id))}`:null;
    const nm=surl?`<a class="ik" href="${e(surl)}" target="_blank">${e(s.name)}</a>`:e(s.name);
    return`<tr><td>${nm}</td><td style="white-space:nowrap">${e(dates)}</td><td>${chip}</td><td>${e((s.state||"").charAt(0).toUpperCase()+(s.state||"").slice(1))}</td></tr>`;
  }).join("")||`<tr class="er"><td colspan="4">No sprints</td></tr>`;
  const sprintTable=`<div class="tw"><div class="tw-body"><table>
    <thead><tr><th>Sprint</th><th>Dates</th><th>Status</th><th>State</th></tr></thead>
    <tbody>${sRows}</tbody>
  </table></div></div>`;

  /* Build all tab panes */
  function spF(rows){return activeSprint?rows.filter(r=>(r.sprint_ids||[]).includes(activeSprint)):rows;}
  const ipRows      =spF(iss.in_progress||[]);
  const ipUnresolved=ipRows.filter(r=>!r.resolved_quarter);
  const ipCarried   =ipRows.filter(r=>!!r.resolved_quarter);
  const ipCarriedIn =ipRows.filter(r=>!!r.origin_quarter);
  const oosOpenRows=spF(iss.oos_open||[]);
  const oosAllRows =spF(iss.oos_all||[]);
  const relRows    =spF(iss.released||[]);
  const allRows    =spF(iss.all||[]);
  const exclSummRows=spF((iss.excluded_summary||[]).map(r=>({...r,_rowCls:(r._rowCls?r._rowCls+' excl-summary':'excl-summary')})));
  const exclKeys=new Set(exclSummRows.map(r=>r.key));

  /* Excluded-summary adjustments — apply in both quarter and sprint view */
  const showExclOn=exclSummRows.length>0&&localStorage.getItem(`showExcl_${PROJ_KEY}`)==='1';

  /* Per-tab subsets of excluded rows — only merged in when showExclOn */
  const exclIpRows  =showExclOn?exclSummRows.filter(r=>r.status_cat==='indeterminate'):[];
  const exclRelRows =showExclOn?exclSummRows.filter(r=>(r.fix_versions||[]).length&&['Released','Closed','Merged'].includes(r.status)):[];
  const exclOosAll  =showExclOn?exclSummRows.filter(r=>(r.labels||[]).includes('Out_Of_Sprint')):[];
  const exclOosOpen =showExclOn?exclOosAll.filter(r=>r.status_cat!=='done'):[];
  const exclNeRows  =showExclOn?exclSummRows.filter(r=>!r.has_estimate):[];
  function _wlogFiltered(pd){
    if(!pd||!exclKeys.size||showExclOn)return pd;
    const days={};
    for(const[dt,entries] of Object.entries(pd.days||{})){
      const filtered=Object.fromEntries(Object.entries(entries).filter(([k])=>!exclKeys.has(k)));
      if(Object.keys(filtered).length)days[dt]=filtered;
    }
    return{...pd,days};
  }
  const adjKpis=_adjKpis(kpis,kpis.excl_summary_stats||{},showExclOn);
  const adjSp=sp?_adjKpis(sp,sp.excl_summary_stats||{},showExclOn):null;
  oa=activeSprint&&adjSp?(adjSp.oos_open||0):(adjKpis.oos_open||0);

  /* KPI cards */
  const K=sp?adjSp:adjKpis;
  const cr=K.completion_rate;
  const crC=cr>=80?"green":cr>=60?"yellow":"red";
  const oosC=oa===0?"green":oa>2?"red":"yellow";
  const rollPct=K.rollover_pct||0;
  const rollC=rollPct===0?"green":rollPct<20?"yellow":"red";
  const cycleC="blue";
  const sn=sp&&sp.notes?sp.notes:{};
  const cards=sp?[
    {l:"Total Items",       v:K.total,                                                        c:"blue",  tip:"All tickets in this sprint."},
    {l:"Completed",         v:K.completed,                                                    c:"green", tip:"Tickets moved to Done in this sprint."},
    {l:"Completion Rate",   v:cr+"%",                                                         c:crC,     tip:"% of sprint tickets completed.", bar:cr, n:sn.completion_rate||""},
    {l:"Releases",          v:K.releases_shipped||0,                                          c:"blue",  tip:"Fix versions released within this sprint date range."},
    ...(PROJ_USE_OOS?[{l:"Out-of-Sprint",v:K.oos_total||0,c:"yellow",tip:"Tickets added to this sprint after it started.",n:sn.oos_total||""}]:[]),
    {l:"Bug / Story / Task",v:K.bugs+" / "+K.stories+" / "+K.tasks+" ("+K.bug_pct+"% bugs)", c:"blue",  tip:"Issue type breakdown for this sprint.",                n:sn.type_split||""},
    {l:"Rollover",          v:K.rollover_count+" items ("+rollPct+"%)",                       c:rollC,   tip:"Items carried forward from an earlier sprint this quarter.", n:sn.rollover||""},
    {l:"Cycle Time",        v:(K.med_cycle_days||0)+"d median ("+(K.avg_cycle_days||0)+"d avg)", c:cycleC, tip:"Median days In Progress to Done for tickets completed this sprint.", n:sn.cycle_time||""},
    ...(PROJ_USE_SP?[
      {l:"SP Planned",    v:K.sp_total||0,     c:"blue",  tip:"Total story points committed to this sprint."},
      {l:"SP Completed",  v:K.sp_completed||0,
       c:(K.sp_total&&K.sp_completed/K.sp_total>=.8)?"green":(K.sp_total&&K.sp_completed/K.sp_total>=.6)?"yellow":"red",
       tip:"Story points completed this sprint."},
    ]:[
      {l:"Hours Logged",      v:(K.time_logged_h||0)+"h",                                      c:"blue",  tip:"Total hours logged by the team in this sprint."},
      {l:"Estimate Accuracy", v:(K.estimate_accuracy_pct||0)+"%",
       c:K.estimate_accuracy_pct>=80?"green":K.estimate_accuracy_pct>=60?"yellow":"red",
       tip:"How close logged hours were to estimates for this sprint."},
    ]),
  ]:[
    {l:"Total Items",           v:K.total,                                           n:notes.total,            c:"blue",   tip:"All tickets in scope across every sprint this quarter, regardless of status or type."},
    {l:"Completed / Released",  v:K.completed,                                       n:notes.completed,        c:"green",  tip:"Tickets moved to Done status this quarter. Compare against Total Items to gauge delivery."},
    {l:"Completion Rate",       v:cr+"%",                                            n:notes.completion_rate,  c:crC,      tip:"Percentage of in-scope tickets completed. 80%+ is healthy; 60—79% warrants a look at blockers; below 60% is a concern.",  bar:cr},
    {l:"Releases Shipped",      v:kpis.releases_shipped,                             n:notes.releases_shipped, c:"blue",   tip:"Number of Jira fix versions released this quarter. Multiple releases indicate a healthy delivery cadence."},
    ...(PROJ_USE_OOS?[
      {l:"Out-of-Sprint (total)", v:K.oos_total, n:notes.oos_total, c:"yellow", tip:"Tickets added to a sprint after it started — unplanned reactive work. High OOS (>20% of total) signals planning or scope issues."},
      {l:"Open OOS Items",        v:oa,             n:notes.oos_open,  c:oosC,     tip:"Out-of-sprint tickets still unresolved. Any open OOS items are unplanned debt that should be closed or explicitly deferred."},
    ]:[]),
    {l:"Bug / Story / Task",    v:`${K.bugs} / ${K.stories} / ${K.tasks} (${K.bug_pct}% bugs)`, n:notes.type_split, c:"blue", tip:"Breakdown of issue types in scope. A bug ratio above 40% signals quality concerns; a healthy quarter is mostly stories and tasks."},
    {l:"Releases / Sprint",     v:`${kpis.med_releases_per_sprint} median (${kpis.avg_releases_per_sprint} avg)`, n:notes.avg_releases, c:"blue", tip:"Median releases per closed sprint — more reliable than the mean when one sprint has an unusually large batch. Healthy cadence varies by team type.",
     xn:(()=>{const med=kpis.med_releases_per_sprint||0,avg=kpis.avg_releases_per_sprint||0;return(avg>med*1.5&&avg-med>0.5)?`⚠ Average is skewed — at least one sprint had an unusually high release count (${avg} avg vs ${med} median).`:""})()},
    {l:"Sprint Rollover",       v:K.rollover_count+" items ("+rollPct+"%)",       n:notes.rollover,         c:rollC,    tip:"Tickets carried from a closed sprint without completing. Note: an item rolling across multiple sprints within the quarter may be counted more than once.",
     xn:K.rollover_count>0?"⚠ Count may include items that rolled across multiple sprints within this quarter — actual unique items could be lower.":""},
    {l:"Cycle Time",            v:`${K.med_cycle_days||0}d median (${K.avg_cycle_days||0}d avg)`,         n:notes.cycle_time,   c:cycleC,   tip:"Median calendar days from In Progress to Done — more reliable than the mean when a small number of long-running tickets inflate the average. Under 3d excellent; 3—7d normal; over 7d investigate blockers.",
     xn:(()=>{const med=K.med_cycle_days||0,avg=K.avg_cycle_days||0;return(avg>med*1.5&&avg-med>2)?`⚠ Average skewed by long-running outlier tickets (${avg}d avg vs ${med}d median) — median is the more representative figure.`:""})()},
    ...(PROJ_USE_SP?[
      {l:"SP Planned",   v:kpis.sp_total||0,        n:notes.sp_velocity||"",  c:"blue",   tip:"Total story points committed across all sprints this quarter."},
      {l:"SP Completed", v:kpis.sp_completed||0,
       c:(kpis.sp_total&&kpis.sp_completed/kpis.sp_total>=.8)?"green":(kpis.sp_total&&kpis.sp_completed/kpis.sp_total>=.6)?"yellow":"red",
       n:"", tip:"Story points completed this quarter."},
      {l:"SP Velocity",  v:(kpis.sp_velocity_avg||0)+" avg/sprint",            n:"",        c:"blue",   tip:"Average story points completed per closed sprint."},
    ]:[]),
  ];
  const kpiHtml=`<div class="kpi-grid">${cards.map(c=>`
    <div class="kpi-card ${c.c}">
      <div class="kl">${e(c.l)}${c.tip?`<span class="trend-info" data-tip="${e(c.tip)}" style="margin-left:4px">&#x2139;</span>`:""}</div>
      <div class="kv">${e(String(c.v))}</div>
      ${c.bar!==undefined?`<div class="kpi-bar"><div class="kpi-bar-fill" style="width:${Math.min(c.bar,100)}%"></div></div>`:""}
      <div class="kn">${e(c.n||"")}</div>
      ${c.xn?`<div class="kn" style="color:var(--yellow-text);margin-top:4px">${e(c.xn)}</div>`:""}
    </div>`).join("")}</div>`;

  /* OOS alert (reused in multiple panes) — must be after oosOpenRows */
  let oosAlert="";
  if(PROJ_USE_OOS){
    let alertLinks="";
    if(oa>0){
      if(activeSprint&&sp){
        const shown=oosOpenRows.slice(0,3);
        if(shown.length){
          alertLinks=" — "+shown.map(r=>`<a href="${e(r.url)}" target="_blank" data-tip="${e(r.summary)}">${e(r.key)}</a>`).join(", ");
          if(oosOpenRows.length>3)alertLinks+=` +${oosOpenRows.length-3} more`;
        }
      } else if(kpis.oos_open_detail){
        const shown=kpis.oos_open_detail.slice(0,3);
        alertLinks=" — "+shown.map(i=>`<a href="${e(jb+"/browse/"+i.key)}" target="_blank" data-tip="${e(i.summary)}">${e(i.key)}</a>`).join(", ");
        if(kpis.oos_open_detail.length>3)alertLinks+=` +${kpis.oos_open_detail.length-3} more`;
      }
    }
    oosAlert=!isCurrentQ&&oa===0?""
      :oa>2?`<div class="alert alert-red">⚠ ${oa} open out-of-sprint items need attention${alertLinks}.</div>`
      :oa>0?`<div class="alert alert-yellow">⚠ ${oa} open out-of-sprint item${oa>1?"s":""} pending${alertLinks}.</div>`
      :isCurrentQ?`<div class="alert alert-green">✓ All out-of-sprint items resolved.</div>`
      :"";
  }

  /* Release breakdown table */
  const verDets=(kpis.version_details||[]).slice().sort((a,b)=>(b.release_date||"").localeCompare(a.release_date||""));
  const relBreakdown=verDets.length?`
    <div class="section-label">Release Breakdown</div>
    <div class="tw"><div class="tw-body"><table class="rel-table">
      <thead><tr><th>Release</th><th>Date</th><th>Tickets</th></tr></thead>
      <tbody>${verDets.map(v=>{
        const url=(v.version_id&&jb)?`${jb}/projects/${PROJ_KEY}/versions/${e(v.version_id)}/tab/release-report-all-issues`:null;
        const nm=url?`<a class="ik" href="${e(url)}" target="_blank">${e(v.name)}</a>`:e(v.name);
        return`<tr><td>${nm}</td><td style="white-space:nowrap">${e(v.release_date||'—')}</td><td>${v.ticket_count}</td></tr>`;
      }).join('')}</tbody>
    </table></div></div>`:'';

  const dashHtml=[
    pane("overview",`
      ${oosAlert}
      ${notesStaleNotice(D.notes_generated_at, D.saved_at)}
      <div class="pane-title">Quarter at a Glance</div>
      <div class="pane-desc">KPIs and sprint summary for ${e(qk)}.</div>
      ${kpiHtml}
      <div class="section-label">Sprints</div>
      ${sprintTable}
    `),
    pane("inprogress",(()=>{
      const ipAll=ipRows.concat(exclIpRows);
      const ipUnresolvedAll=ipAll.filter(r=>!r.resolved_quarter);
      return`
      <div class="pane-title">In Progress <span class="tab-cnt ${!isCurrentQ&&ipUnresolvedAll.length>0?"warn":""}">${ipAll.length}</span></div>
      ${!isCurrentQ&&ipUnresolvedAll.length>0?`<div class="alert alert-yellow">⚠ ${ipUnresolvedAll.length} item${ipUnresolvedAll.length>1?"s are":" is"} still in progress after quarter close — may need follow-up.</div>`:""}
      ${!isCurrentQ&&ipCarried.length>0?`<div class="alert alert-green">✓ ${ipCarried.length} item${ipCarried.length>1?"s were":" was"} resolved in a later quarter — hover &#x2139; for details.</div>`:""}
      ${isCurrentQ?`<div class="pane-desc">Items currently being worked on across all sprints this quarter.${ipCarriedIn.length>0?` Coloured &#x2139; marks ${ipCarriedIn.length} item${ipCarriedIn.length>1?"s":""}  carried over from a previous quarter.`:""}</div>`:""}
      ${mkTable(ipCols,isCurrentQ?ipAll:ipAll.map(r=>r._rowCls==='resolved-carried'?r:{...r,_rowCls:r._rowCls||''}),jUrl(base+" AND statusCategory != Done ORDER BY status ASC, assignee ASC"))}
    `;})()),
    ...(PROJ_USE_OOS?[
    pane("oosopen",`
      ${oosAlert}
      <div class="pane-title">Open OOS Items <span class="tab-cnt ${isCurrentQ?(oa>2?"urgent":oa>0?"warn":"clear"):""}">${oosOpenRows.length+exclOosOpen.length}</span></div>
      <div class="pane-desc">Out-of-sprint items that are still open and need resolution.</div>
      ${mkTable(oosCols,oosOpenRows.concat(exclOosOpen),jUrl(base+" AND labels = Out_Of_Sprint AND statusCategory != Done ORDER BY priority ASC"))}
    `),
    pane("oos",`
      <div class="pane-title">Out-of-Sprint Items <span class="tab-cnt">${oosAllRows.length+exclOosAll.length}</span></div>
      <div class="pane-desc">All items flagged Out_Of_Sprint this quarter, including resolved ones.</div>
      ${mkTable(oosCols,oosAllRows.concat(exclOosAll),jUrl(base+" AND labels = Out_Of_Sprint ORDER BY status ASC"))}
    `),
    ]:[]),
    pane("released",`
      <div class="pane-title">Released <span class="tab-cnt">${relRows.length+exclRelRows.length}</span></div>
      <div class="pane-desc">Items with status Released, Closed, or Merged that have a fix version attached.</div>
      ${relBreakdown}
      ${mkTable(relCols,relRows.concat(exclRelRows),jUrl(base+" AND status in (Released,Closed,Merged) AND fixVersion is not EMPTY ORDER BY fixVersions ASC"))}
    `),
    pane("all",`
      <div class="pane-title">All Items <span class="tab-cnt">${allRows.length+(showExclOn?exclSummRows.length:0)}</span></div>
      <div class="pane-desc">Every issue in scope across all ${e(qk)} sprints.</div>
      ${mkTable(allCols,showExclOn?allRows.concat(exclSummRows):allRows,jUrl(base+" ORDER BY sprint ASC, status ASC"))}
    `),
    pane("time",`
      ${notesStaleNotice(D.notes_generated_at, D.saved_at)}
      ${(()=>{
        const useSp=PROJ_USE_SP||false;
        const spSel=!!(activeSprint&&sp);
        const neRows=spF(iss.no_estimate||[]);
        const ne=spSel?neRows.length:(adjKpis.no_estimate_count||0);
        const nePct=spSel?(K.total?Math.round(neRows.length/K.total*100):0):(adjKpis.no_estimate_pct||0);
        const neC=nePct===0?'green':nePct<20?'yellow':'red';

        if(useSp){
          // ---- Story Points mode ----
          const spt=spSel?(K.sp_total||0):(kpis.sp_total||0);
          const spc=spSel?(K.sp_completed||0):(kpis.sp_completed||0);
          const spPct=spt?Math.round(spc/spt*100):0;
          const spCards=spSel?[
            // Sprint view: planned / completed / completion % / no-est
            {l:'SP Planned',   v:spt, c:'blue', n:'Story points committed to this sprint.'},
            {l:'SP Completed', v:spc, c:spPct>=80?'green':spPct>=60?'yellow':'red', n:''},
            {l:'Completion',   v:spt?spPct+'%':'—', c:spPct>=80?'green':spPct>=60?'yellow':'red',
             n:'SP completed vs planned for this sprint.'},
            {l:'No SP Est',    v:ne, c:neC, n:nePct>0?nePct+'% of items in this sprint have no story points.':''},
          ]:[
            // Quarter view: planned / completed / velocity / no-est
            {l:'SP Planned',   v:kpis.sp_total||0,        c:'blue',   n:'Total story points across all sprint items this quarter.'},
            {l:'SP Completed', v:kpis.sp_completed||0,
             c:spPct>=80?'green':spPct>=60?'yellow':'red', n:notes.sp_velocity||''},
            {l:'SP Velocity',  v:(kpis.sp_velocity_avg||0)+' avg/sprint', c:'blue',
             n:'Average story points completed per closed sprint.'},
            {l:'No SP Est',    v:ne, c:neC, n:nePct>0?(notes.no_estimate||(nePct+'% of items have no story points set.')):''},
          ];
          const spKpiHtml='<div class="kpi-grid">'+spCards.map(c=>`
            <div class="kpi-card ${c.c}">
              <div class="kl">${e(c.l)}</div>
              <div class="kv">${e(String(c.v))}</div>
              <div class="kn">${e(c.n)}</div>
            </div>`).join('')+'</div>';
          const maxSp=Math.max(spt,spc,1);
          const barW=v=>Math.round((v/maxSp)*100);
          const compBar=spt?`<div class="section-label" style="margin-bottom:8px">SP Planned vs Completed</div>
            <div style="display:flex;flex-direction:column;gap:6px;max-width:480px;margin-bottom:24px">
              <div style="display:flex;align-items:center;gap:10px">
                <span style="width:90px;font-size:12px;color:var(--muted);text-align:right">Planned</span>
                <div style="flex:1;background:var(--border);border-radius:3px;height:16px;overflow:hidden">
                  <div style="width:${barW(spt)}%;height:100%;background:var(--accent);border-radius:3px"></div>
                </div>
                <span style="width:50px;font-size:12px;font-weight:600">${e(String(spt))}</span>
              </div>
              <div style="display:flex;align-items:center;gap:10px">
                <span style="width:90px;font-size:12px;color:var(--muted);text-align:right">Completed</span>
                <div style="flex:1;background:var(--border);border-radius:3px;height:16px;overflow:hidden">
                  <div style="width:${barW(spc)}%;height:100%;background:${spPct>=80?'var(--green)':spPct>=60?'var(--yellow)':'var(--red)'};border-radius:3px"></div>
                </div>
                <span style="width:50px;font-size:12px;font-weight:600">${e(String(spc))}</span>
              </div>
            </div>`:'';
          const neAlert=nePct>20
            ?`<div class="alert alert-red">⚠ ${ne} items (${nePct}%) have no story points — velocity reporting is affected.</div>`
            :nePct>0
            ?`<div class="alert alert-yellow">⚠ ${ne} items (${nePct}%) have no story points.</div>`
            :`<div class="alert alert-green">✓ All items have story point estimates.</div>`;
          const neCols=issueCols([priCol,{h:'Story Points',r:r=>r.story_points||'—'}]);
          return '<div class="pane-title">Story Points</div>'
            +'<div class="pane-desc">'+(spSel?'Story points planned vs completed for '+e(sp.sprint_name)+'.':'Story points planned vs completed across all sprints. Items without story points affect velocity reporting.')+'</div>'
            +spKpiHtml+compBar+neAlert
            +'<div class="section-label" style="margin-bottom:10px">Items Without Story Points</div>'
            +mkTable(neCols,neRows.concat(exclNeRows),jUrl(base+' AND "Story Points" is EMPTY ORDER BY status ASC'));
        }

        // ---- Time / Hours mode ----
        const _Kt=spSel?(adjSp||K):adjKpis;
        const tl=_Kt.time_logged_h||0, te=_Kt.time_estimated_h||0;
        const acc=_Kt.estimate_accuracy_pct||0, vari=_Kt.estimate_variance_pct||0;
        const nl=spSel?allRows.filter(r=>!(r.logged_h>0)).length:(adjKpis.no_log_count||0);
        const diffH=Math.round((tl-te)*10)/10;
        const diffStr=te===0?'—':(diffH>0?'+'+diffH+'h over':diffH<0?Math.abs(diffH)+'h under':'exact');
        const diffC=Math.abs(vari)<10?'green':Math.abs(vari)<25?'yellow':'red';
        const timeCards=[
          {l:'Hours Logged',      v:tl+'h',   n:spSel?'':notes.time_logged||'',    c:'blue'},
          {l:'Hours Estimated',   v:te+'h',   n:te?'':'No estimates set.',           c:'blue'},
          {l:'Estimate Accuracy', v:acc+'%',  n:'Logged vs estimated. 100% = exact.',c:diffC},
          {l:'Over / Under',      v:diffStr,  n:'Difference between logged and estimated hours.', c:diffC},
          {l:'No Estimate',       v:ne,       n:spSel?nePct+'% of items lack an estimate.':notes.no_estimate||(nePct+'% of items lack an estimate.'),c:neC},
          {l:'No Time Logged',    v:nl,       n:'Items with zero time recorded.',    c:nl===0?'green':'yellow'},
        ];
        const timeKpiHtml='<div class="kpi-grid">'+timeCards.map(c=>`
          <div class="kpi-card ${c.c}">
            <div class="kl">${e(c.l)}</div>
            <div class="kv">${e(String(c.v))}</div>
            <div class="kn">${e(c.n)}</div>
          </div>`).join('')+'</div>';
        const maxH=Math.max(tl,te,1);
        const barW=v=>Math.round((v/maxH)*100);
        const compBar=te?`<div class="section-label" style="margin-bottom:8px">Logged vs Estimated</div>
          <div style="display:flex;flex-direction:column;gap:6px;max-width:480px;margin-bottom:24px">
            <div style="display:flex;align-items:center;gap:10px">
              <span style="width:90px;font-size:12px;color:var(--muted);text-align:right">Estimated</span>
              <div style="flex:1;background:var(--border);border-radius:3px;height:16px;overflow:hidden">
                <div style="width:${barW(te)}%;height:100%;background:var(--accent);border-radius:3px"></div>
              </div>
              <span style="width:50px;font-size:12px;font-weight:600">${e(te+'h')}</span>
            </div>
            <div style="display:flex;align-items:center;gap:10px">
              <span style="width:90px;font-size:12px;color:var(--muted);text-align:right">Logged</span>
              <div style="flex:1;background:var(--border);border-radius:3px;height:16px;overflow:hidden">
                <div style="width:${barW(tl)}%;height:100%;background:${vari>25?'var(--red)':vari>0?'var(--yellow)':'var(--green)'};border-radius:3px"></div>
              </div>
              <span style="width:50px;font-size:12px;font-weight:600">${e(tl+'h')}</span>
            </div>
          </div>`:'';
        const neAlert=nePct>20
          ?`<div class="alert alert-red">⚠ ${ne} items (${nePct}%) have no time estimate — accuracy reporting is skewed.</div>`
          :nePct>0
          ?`<div class="alert alert-yellow">⚠ ${ne} items (${nePct}%) have no time estimate.</div>`
          :`<div class="alert alert-green">✓ All items have time estimates.</div>`;
        const neCols=issueCols([priCol,{h:'Logged',r:r=>r.logged_h?r.logged_h+'h':'—'}]);
        return '<div class="pane-title">Time Tracking</div>'
          +'<div class="pane-desc">Logged vs estimated hours across all sprint items. Items without estimates affect accuracy reporting.</div>'
          +timeKpiHtml+compBar+neAlert
          +'<div class="section-label" style="margin-bottom:10px">Items Without Estimates</div>'
          +mkTable(neCols,neRows.concat(exclNeRows),jUrl(base+' AND originalEstimate is EMPTY ORDER BY status ASC'));
      })()}
    `),
    pane("team",`
      ${notesStaleNotice(D.notes_generated_at, D.saved_at)}
      <div class="pane-title">Team</div>
      ${(()=>{
        const useSp=PROJ_USE_SP||false;
        const as=(adjSp?adjSp.assignee_stats:null)||adjKpis.assignee_stats||[];
        const wlog=kpis.worklog_by_person||{};
        const wlogIds=Object.keys(wlog);
        const hasWlog=wlogIds.length>0;

        // ---- Assignee summary table (always built; shown in overview mode) ----
        function mkRow(a){
          const ratC=a.completion_rate>=80?'green':a.completion_rate>=60?'yellow':'red';
          let bar;
          if(useSp){
            const spt=a.sp_total||0, spc=a.sp_completed||0;
            const spPct=spt?Math.round(spc/spt*100):0;
            const col=spPct>=80?'#22c55e':spPct>=60?'#FCE300':'#ef4444';
            bar=`<div style="display:flex;align-items:center;gap:6px">
              <div style="flex:1;min-width:60px;background:var(--border);border-radius:3px;height:8px;overflow:hidden">
                ${spt?`<div style="width:${spPct}%;height:100%;background:${col};border-radius:3px"></div>`:'<div style="width:0%"></div>'}
              </div>
              <span style="font-size:12px;font-weight:600;white-space:nowrap">${e(String(spc))} SP</span>
            </div>`;
          } else {
            bar=`<div style="display:flex;align-items:center;gap:6px">
              <div style="flex:1;min-width:60px;background:var(--border);border-radius:3px;height:8px;overflow:hidden">${(()=>{
                if(!a.estimated_h)return'<div style="width:0%"></div>';
                const over=a.logged_h>a.estimated_h;
                const acc=Math.round(Math.min(a.logged_h,a.estimated_h)/Math.max(a.logged_h,a.estimated_h)*100);
                const col=acc>=80?'#22c55e':acc>=60?'#FCE300':'#ef4444';
                const w=over?100:acc;
                return`<div style="width:${w}%;height:100%;background:${col};border-radius:3px"></div>`;
              })()}
              </div>
              <span style="font-size:12px;font-weight:600;white-space:nowrap">${e(a.logged_h+'h')}${a.estimated_h&&a.logged_h>a.estimated_h?`<span style="font-size:10px;color:#ef4444;margin-left:3px">+${Math.round((a.logged_h/a.estimated_h-1)*100)}%</span>`:''}</span>
            </div>`;
          }
          // Name cell — Jira link as before
          const jql=a.account_id
            ?`project = ${PROJ_KEY} AND sprint in (${ids}) AND assignee = "${e(a.account_id)}" ORDER BY status ASC`
            :`project = ${PROJ_KEY} AND sprint in (${ids}) AND assignee is EMPTY ORDER BY status ASC`;
          let nameCell;
          const partialTag=a.team_period?`<span class="trend-info" data-tip="${e(a.team_period)}" style="margin-left:5px">&#x2139;</span>`:'';
          if(jb){
            nameCell=`<a class="assignee-link" href="${e(jb+'/issues/?jql='+encodeURIComponent(jql))}" target="_blank">${e(a.name)}</a>`;
          } else {
            nameCell=`<span style="font-weight:500">${e(a.name)}</span>`;
          }
          // Chevron toggle for inline worklog chart
          // Cloudflare user slug: "hugh odwyer" — matched against display name case-insensitively
          const hasPersonWlog=hasWlog&&a.account_id&&wlog[a.account_id];
          const rowId=`wlog-row-${e(a.account_id||a.name).replace(/[^a-z0-9]/gi,'_')}`;
          const cfEmail=window._cfUserEmail||null;
          const cfSlug=window._cfUserSlug||null;
          const isAdmin=!WLOG_ADMINS||WLOG_ADMINS.length===0||(cfEmail&&WLOG_ADMINS.map(e=>e.toLowerCase()).includes(cfEmail));
          const nameSlug=a.name?a.name.toLowerCase():null;
          const isOwnRow=!cfSlug||!nameSlug||isAdmin||nameSlug===cfSlug;
          const chevronSvgDown=`<svg width='10' height='10' viewBox='0 0 10 10'><path d='M1 3 L5 7 L9 3' stroke='currentColor' stroke-width='1.5' fill='none' stroke-linecap='round'/></svg>`;
          const chevronSvgUp=`<svg width='10' height='10' viewBox='0 0 10 10'><path d='M1 7 L5 3 L9 7' stroke='currentColor' stroke-width='1.5' fill='none' stroke-linecap='round'/></svg>`;
          const chevron=hasPersonWlog
            ?(isOwnRow
              ?`<button onclick="(function(){var r=document.getElementById('${rowId}');var c=r.previousSibling.querySelector('.wlog-chev');var open=r.style.display==='none';r.style.display=open?'table-row':'none';c.setAttribute('data-open',open?'1':'');c.innerHTML=open?'${chevronSvgDown.replace(/'/g,"\\'")}':'${chevronSvgUp.replace(/'/g,"\\'")}\';})()" style="background:none;border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--muted);padding:2px 4px;margin-left:6px;vertical-align:middle;line-height:0;display:inline-flex;align-items:center" class="wlog-chev">${chevronSvgUp}</button>`
              :`<button onclick="(function(){var tt=document.getElementById('cf-access-notice');tt.style.display='flex';setTimeout(function(){tt.style.display='none';},3000);})()" style="background:none;border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--border);padding:2px 4px;margin-left:6px;vertical-align:middle;line-height:0;display:inline-flex;align-items:center" title="You can only view your own time log" class="wlog-chev">${chevronSvgUp}</button>`)
            :'';
          if(useSp){
            const spt=a.sp_total||0;
            const expandRow=hasPersonWlog?`<tr id="${rowId}" style="display:none"><td colspan="6" style="padding:12px 16px;background:var(--surface)">${(()=>{const sprintDates=(()=>{if(!activeSprint)return null;const s=(sprints||[]).find(s=>String(s.id)===activeSprint);return s?{start:s.start_date,end:s.end_date||String(new Date().toISOString().slice(0,10))}:null;})();return renderWorklogChart(_wlogFiltered(wlog[a.account_id]),jb,sprintDates);})()}</td></tr>`:'';
            return`<tr><td>${nameCell}${chevron}${partialTag}</td><td style="text-align:center">${e(String(a.total))}</td><td style="text-align:center">${e(String(a.completed))}</td><td style="text-align:center"><span class="b ${ratC==="green"?"bd":ratC==="yellow"?"bmed":"bbug"}">${e(a.completion_rate+"%")}</span></td><td style="min-width:140px">${bar}</td><td style="text-align:center;color:var(--muted)">${e(spt>0?String(spt):'—')}</td></tr>${expandRow}`;
          }
          const accVal=(a.logged_h>0&&a.estimated_h>0)
            ?Math.round(Math.min(a.logged_h,a.estimated_h)/Math.max(a.logged_h,a.estimated_h)*100)
            :null;
          const accInner=accVal===null
            ?`<span style="color:var(--muted)">—</span>`
            :isCurrentQ
              ?`<span style="color:var(--muted)">${accVal}%</span>`
              :`<span class="b ${accVal>=80?'bd':accVal>=60?'bmed':'bbug'}">${accVal}%</span>`;
          const expandRow=hasPersonWlog?`<tr id="${rowId}" style="display:none"><td colspan="7" style="padding:12px 16px;background:var(--surface)">${(()=>{const sprintDates=(()=>{if(!activeSprint)return null;const s=(sprints||[]).find(s=>String(s.id)===activeSprint);return s?{start:s.start_date,end:s.end_date||String(new Date().toISOString().slice(0,10))}:null;})();return renderWorklogChart(_wlogFiltered(wlog[a.account_id]),jb,sprintDates);})()}</td></tr>`:'';
          return`<tr><td>${nameCell}${chevron}${partialTag}</td><td style="text-align:center">${e(String(a.total))}</td><td style="text-align:center">${e(String(a.completed))}</td><td style="text-align:center"><span class="b ${ratC==="green"?"bd":ratC==="yellow"?"bmed":"bbug"}">${e(a.completion_rate+"%")}</span></td><td style="min-width:140px">${bar}</td><td style="text-align:center;color:var(--muted)">${e(a.estimated_h>0?a.estimated_h+'h':'—')}</td><td style="text-align:center">${accInner}</td></tr>${expandRow}`;
        }
        const thead=useSp
          ?`<thead><tr>
              <th>Assignee</th><th style="text-align:center">Items</th>
              <th style="text-align:center">Done</th><th style="text-align:center">Rate</th>
              <th>SP Completed</th><th style="text-align:center">SP Planned</th>
            </tr></thead>`
          :`<thead><tr>
              <th>Assignee${hasWlog?'<span class="trend-info" data-tip="Click the chevron next to a name to expand their daily time log" style="margin-left:4px">&#x2139;</span>':''}</th><th style="text-align:center">Items</th>
              <th style="text-align:center">Done</th><th style="text-align:center">Rate</th>
              <th>Hours Logged</th><th style="text-align:center">Estimated</th>
              <th style="text-align:center">Accuracy${isCurrentQ?'<span class="trend-info" data-tip="Partial quarter — accuracy will change as more time is logged" style="margin-left:4px">&#x2139;</span>':''}</th>
            </tr></thead>`;
        const colSpan=useSp?6:7;
        const team=as.filter(a=>a.is_team), others=as.filter(a=>!a.is_team);
        let tableHtml=as.length
          ?`<div class="section-label">Features Team</div>
            <div class="tw"><div class="tw-body"><table>${thead}<tbody>${team.map(mkRow).join("")||`<tr class="er"><td colspan="${colSpan}">No team member data</td></tr>`}</tbody></table></div></div>`
          :'<div class="nodata">No assignee data.</div>';
        if(others.length)
          tableHtml+=`<div class="section-label" style="margin-top:20px">Other Assignees</div>
            <div class="tw"><div class="tw-body"><table>${thead}<tbody>${others.map(mkRow).join("")}</tbody></table></div></div>`;

        return`<div class="pane-desc">Workload breakdown by assignee for ${activeSprint&&sp?e(sp.sprint_name):e(qk)+'. '+e(notes.assignee_workload||'')}.</div>${tableHtml}`;
      })()}
    `),
    pane("trends",renderTrends()),
    pane("nextsp",renderNextSprint()),
  ].join("");

  document.getElementById("dash").innerHTML=dashHtml;

  /* Tab bar with counts */
  const tabDefs=[
    {id:"overview",   label:"Overview"},
    {id:"inprogress", label:"In Progress",   cnt:ipRows.length+(showExclOn?exclIpRows.length:0),    cls:!isCurrentQ&&ipUnresolved.length>0?"warn":""},
    ...(PROJ_USE_OOS?[
      {id:"oosopen",label:"Open OOS",      cnt:oa+(showExclOn?exclOosOpen.length:0),               cls:isCurrentQ?(oa>2?"urgent":oa>0?"warn":"clear"):""},
      {id:"oos",    label:"Out-of-Sprint", cnt:oosAllRows.length+(showExclOn?exclOosAll.length:0),cls:""},
    ]:[]),
    {id:"released",   label:"Released",      cnt:relRows.length+(showExclOn?exclRelRows.length:0),   cls:""},
    {id:"all",        label:"All Items",     cnt:allRows.length+(showExclOn?exclSummRows.length:0),   cls:""},
    {id:"time",       label:PROJ_USE_SP?"Points":"Time"},
    {id:"team",       label:"Team"},
    {id:"trends",     label:"Trends"},
    {id:"nextsp",     label:"Next Sprint"},
  ];
  document.getElementById("tabs-bar").innerHTML=tabDefs.map(t=>{
    const badge=t.cnt!==undefined?`<span class="tab-cnt ${t.cls}">${t.cnt}</span>`:"";
    return`<button class="tab" data-tab="${t.id}">${e(t.label)}${badge}</button>`;
  }).join("");
  document.querySelectorAll(".tab").forEach(t=>t.addEventListener("click",()=>showTab(t.dataset.tab)));

  /* Sync --hdr with actual header height so toolbar sticky offset is correct */
  _syncHdr();

  showTab(activeTab||"overview");

  /* Excluded-summary toggles — sprint bar (all tabs) + trends toolbar (trends only) */
  const hasExcl=exclSummRows.length>0;
  const _exclLabel=(()=>{const lbl=D.kpis.excl_summary_label||"";return lbl?"Show "+lbl:"Show excluded";})();
  const _wireExclToggle=(lbl,cb)=>{
    if(!lbl)return;
    lbl.style.display=hasExcl?'':'none';
    lbl.lastChild.textContent=" "+_exclLabel;
    if(cb){
      cb.checked=showExclOn;
      cb.onchange=()=>{
        localStorage.setItem(`showExcl_${PROJ_KEY}`,cb.checked?'1':'0');
        render(qk,curTab);
      };
    }
  };
  _wireExclToggle(document.getElementById("excl-toggle-hdr"),   document.getElementById("exclCb"));
  _wireExclToggle(document.getElementById("excl-toggle-trends"), document.getElementById("exclCbTrends"));
}

/* ---- Worklog (Clockify-style) chart ---- */
const WLOG_COLORS=['#2563eb','#16a34a','#d97706','#7c3aed','#db2777','#0891b2','#65a30d','#ea580c','#0d9488','#4f46e5','#be123c','#0284c7','#854d0e','#166534'];

function renderWorklogChart(pd, jb, sprintDates){
  // pd = {name, days:{date:{issueKey:{s:seconds,t:summary}}}}
  // sprintDates = {start,end} or null — filters days to sprint range when set
  const allDays=pd.days||{};
  let dates=Object.keys(allDays).sort();
  if(sprintDates&&sprintDates.start&&sprintDates.end)
    dates=dates.filter(d=>d>=sprintDates.start&&d<=sprintDates.end);
  if(!dates.length)return'<div class="nodata" style="margin:16px 0">No time logged'+(sprintDates?' in this sprint':'')+'.</div>';

  // Unique issue keys → assign stable colors
  const keySet=new Set();
  dates.forEach(d=>Object.keys(allDays[d]).forEach(k=>keySet.add(k)));
  const keys=[...keySet];
  const keyCol={};keys.forEach((k,i)=>keyCol[k]=WLOG_COLORS[i%WLOG_COLORS.length]);

  // Day totals (hours)
  const dayTotals=dates.map(d=>Object.values(allDays[d]).reduce((s,v)=>s+v.s,0)/3600);
  // Cap Y axis at 10h — bars exceeding this get a clipped render + overflow marker
  const Y_CAP=10;
  const yTop=Y_CAP;

  // SVG layout — fixed chart width, bars sized to fit
  const PL=40,PT=28,PB=38,PR=12;
  const CHART_W=900;
  const BG=4;
  const BW=Math.min(32,Math.max(8,Math.floor((CHART_W-PL-PR)/dates.length)-BG));
  const svgH=168;const plotH=svgH-PT-PB;
  const svgW=Math.max(CHART_W,PL+(BW+BG)*dates.length-BG+PR);
  const yS=v=>PT+plotH-(Math.min(v,yTop)/yTop)*plotH;

  // Gridlines + y labels
  const ySteps=[0,4,8,10];
  let grid='';
  ySteps.forEach(v=>{
    grid+=`<line x1="${PL}" y1="${yS(v).toFixed(1)}" x2="${svgW-PR}" y2="${yS(v).toFixed(1)}" stroke="#e2e8f0" stroke-width="1"/>`;
    grid+=`<text x="${PL-5}" y="${(yS(v)+4).toFixed(1)}" text-anchor="end" font-size="9" fill="#94a3b8">${v}h</text>`;
  });

  // Bars + x-axis labels
  let bars='',xlbls='';
  let prevTopKey=null;
  dates.forEach((date,i)=>{
    const x=PL+i*(BW+BG);
    const d=new Date(date+'T12:00:00');
    const dow=['Su','Mo','Tu','We','Th','Fr','Sa'][d.getDay()];
    const mon=d.toLocaleDateString('en-GB',{month:'short'});
    const total=dayTotals[i];
    const capped=total>yTop;
    // Stack segments bottom-up, capped at yTop
    // Reorder segments so no two adjacent ones share the same colour (handles palette repeats)
    // Also ensure top segment colour doesn't match bottom of previous bar
    let y=svgH-PB;
    let rendered=0;
    const dayData=allDays[date];
    let dayKeys=Object.keys(dayData);
    // Greedy reorder: build stack bottom-up, each time pick next key whose colour differs from the last placed
    if(dayKeys.length>1){
      const reordered=[];
      const remaining=[...dayKeys];
      let lastCol=prevTopKey?keyCol[prevTopKey]:null;
      while(remaining.length){
        // prefer a key whose colour differs from lastCol; fall back to first if no choice
        const idx=remaining.findIndex(k=>keyCol[k]!==lastCol);
        const pick=remaining.splice(idx===-1?0:idx,1)[0];
        reordered.push(pick);
        lastCol=keyCol[pick];
      }
      dayKeys=reordered;
    }
    prevTopKey=dayKeys[dayKeys.length-1]||null;
    dayKeys.forEach(key=>{
      const h=dayData[key].s/3600;
      const hCapped=Math.min(h, yTop-rendered);
      if(hCapped<=0)return;
      const bh=(hCapped/yTop)*plotH;
      if(bh<0.5)return;
      const tip=`${key}: ${Math.round(h*10)/10}h — ${dayData[key].t}`;
      bars+=`<rect x="${x}" y="${(y-bh).toFixed(1)}" width="${BW}" height="${bh.toFixed(1)}" fill="${keyCol[key]}" rx="2" data-tip="${e(tip)}"/>`;
      y-=bh;
      rendered+=hCapped;
    });
    // Overflow indicator — hatched top strip + label showing real total
    if(capped){
      bars+=`<rect x="${x}" y="${PT}" width="${BW}" height="5" fill="url(#overflow-hatch)" opacity="0.7"/>`;
      const capLblY=i%2===0?PT-3:PT-11;
      const capLine=i%2===1?`<line x1="${(x+BW/2).toFixed(1)}" y1="${PT-3}" x2="${(x+BW/2).toFixed(1)}" y2="${PT-8}" stroke="#ef4444" stroke-width="1" opacity="0.5"/>`:'';
      bars+=capLine+`<text x="${(x+BW/2).toFixed(1)}" y="${capLblY.toFixed(1)}" text-anchor="middle" font-size="8" fill="#ef4444" font-weight="700">${Math.round(total*10)/10}h↑</text>`;
    } else if(total>=1){
      // Only show label if bar is tall enough to avoid cramping (at least 10px height)
      const barTopY=yS(total);
      const barH=svgH-PB-barTopY;
      if(barH>=14){
        const label=total>=10?Math.round(total)+'h':Math.round(total*10)/10+'h';
        bars+=`<text x="${(x+BW/2).toFixed(1)}" y="${(barTopY-4).toFixed(1)}" text-anchor="middle" font-size="9" fill="#475569" font-weight="600">${label}</text>`;
      }
    }
    // X labels: day-of-week + date + month on first of month
    xlbls+=`<text x="${(x+BW/2).toFixed(1)}" y="${svgH-PB+13}" text-anchor="middle" font-size="9" fill="#94a3b8">${dow}</text>`;
    xlbls+=`<text x="${(x+BW/2).toFixed(1)}" y="${svgH-PB+24}" text-anchor="middle" font-size="9" fill="${d.getDate()===1?'#475569':'#94a3b8'}">${d.getDate()===1?`${d.getDate()} ${mon}`:d.getDate()}</text>`;
  });

  const totalH=dayTotals.reduce((s,v)=>s+v,0);

  // Legend — sorted by total hours desc, compact two-column grid
  const legendItems=keys.map(k=>{
    const kTot=dates.reduce((s,d)=>s+(allDays[d][k]?.s||0),0)/3600;
    const summ=(allDays[dates.find(d=>allDays[d][k])]?.[k]?.t)||'';
    const href=jb?`${jb}/browse/${k}`:'#';
    return{k,kTot,summ,href};
  }).sort((a,b)=>b.kTot-a.kTot);
  const legend=legendItems.map(({k,kTot,summ,href})=>
    `<div style="display:flex;align-items:center;gap:5px;min-width:160px" title="${e(summ)}">
      <span style="width:10px;height:10px;border-radius:2px;background:${keyCol[k]};flex-shrink:0;display:inline-block"></span>
      <a href="${e(href)}" target="_blank" style="font-size:11px;font-weight:500;color:var(--text);text-decoration:none;white-space:nowrap">${e(k)}</a>
      <span style="font-size:11px;color:var(--muted);white-space:nowrap">${Math.round(kTot*10)/10}h</span>
    </div>`
  ).join('');

  // Hatch pattern def for overflow bars
  const defs=`<defs><pattern id="overflow-hatch" patternUnits="userSpaceOnUse" width="4" height="4" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" stroke="#ef4444" stroke-width="2"/></pattern></defs>`;

  return`<div style="font-size:13px;color:var(--muted);margin-bottom:12px">Total: <strong style="color:var(--text)">${Math.round(totalH*10)/10}h</strong> across <strong style="color:var(--text)">${dates.length}</strong> day${dates.length!==1?'s':''} <span class="trend-info" data-tip="Hours shown here are filtered by worklog start date within the quarter. The Hours Logged column in the table uses the issue's total time spent, which may include time logged outside this quarter — so totals can differ.">&#x2139;</span></div>
    <div style="overflow-x:auto;max-width:100%">
      <svg viewBox="0 0 ${svgW} ${svgH}" style="min-width:${Math.min(svgW,640)}px;width:${svgW>640?'100%':'auto'};display:block" xmlns="http://www.w3.org/2000/svg">
        ${defs}${grid}${bars}${xlbls}
      </svg>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:6px 16px;margin-top:12px">${legend}</div>`;
}

/* ---- Trend charts ---- */
function mkLineChart(values,labels,higherIsBetter,lastIsWip,tipVals){
  const n=values.length;
  if(n<2)return'<p style="text-align:center;color:var(--muted);font-size:12px;padding:20px 0">Not enough data</p>';
  const W=300,H=90,pL=36,pR=12,pT=10,pB=22;
  const cW=W-pL-pR,cH=H-pT-pB;
  const min=Math.min(...values),max=Math.max(...values),span=max-min||1;
  const cx=i=>pL+(n<2?cW/2:(i/(n-1))*cW);
  const cy=v=>pT+cH-((v-min)/span)*cH;
  // Per-segment colour: each segment coloured by its own direction
  function segCol(delta){
    if(higherIsBetter===null||delta===0)return'#94a3b8';
    return(higherIsBetter?delta>0:delta<0)?'#22c55e':'#ef4444';
  }
  const fmt=v=>Number.isInteger(v)?v:v.toFixed(1);
  const midY=(pT+(pT+cH))/2;
  const grid=`<line x1="${pL}" y1="${midY.toFixed(1)}" x2="${W-pR}" y2="${midY.toFixed(1)}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3,3"/>`;
  const yLbls=`<text x="${pL-4}" y="${(pT+6).toFixed(0)}" text-anchor="end" font-size="9" fill="#94a3b8">${fmt(max)}</text>`
             +`<text x="${pL-4}" y="${(pT+cH).toFixed(0)}" text-anchor="end" font-size="9" fill="#94a3b8">${fmt(min)}</text>`;
  const xLbls=labels.map((l,i)=>{
    if(n>=6&&i>0&&i<n-1&&i%2!==0)return''; // skip odd intermediates when crowded
    const lbl=l.replace('·20',"'"); // "Q1·2026"→"Q1'26" always
    const anchor=i===0?'start':i===n-1?'end':'middle';
    return`<text x="${cx(i).toFixed(1)}" y="${H-3}" text-anchor="${anchor}" font-size="9" fill="#94a3b8">${e(lbl)}</text>`;
  }).join('');
  // Area fill uses neutral tint — segments carry the colour story
  const solidPts=values.map((v,i)=>`${cx(i).toFixed(1)},${cy(v).toFixed(1)}`);
  // Per-segment fills (trapezoid under each segment) + coloured lines
  const bot=(pT+cH).toFixed(1);
  function segFill(sc){return sc==='#22c55e'?'rgba(34,197,94,.15)':sc==='#ef4444'?'rgba(239,68,68,.15)':'rgba(148,163,184,.08)';}
  const fills=[],segs=[];
  for(let i=0;i<n-1;i++){
    const x1=cx(i).toFixed(1),y1=cy(values[i]).toFixed(1);
    const x2=cx(i+1).toFixed(1),y2=cy(values[i+1]).toFixed(1);
    const isWipSeg=lastIsWip&&i===n-2;
    if(isWipSeg){
      fills.push(`<polygon points="${x1},${bot} ${x1},${y1} ${x2},${y2} ${x2},${bot}" fill="rgba(148,163,184,.06)"/>`);
      segs.push(`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,3" stroke-linecap="round"/>`);
    }else{
      const sc=segCol(values[i+1]-values[i]);
      fills.push(`<polygon points="${x1},${bot} ${x1},${y1} ${x2},${y2} ${x2},${bot}" fill="${segFill(sc)}"/>`);
      segs.push(`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${sc}" stroke-width="2" stroke-linecap="round"/>`);
    }
  }
  // Dots coloured by incoming segment direction
  const dots=values.map((v,i)=>{
    const isLast=i===n-1,isWip=isLast&&lastIsWip;
    const tip=tipVals?tipVals[i]:'';
    const tipAttr=tip?` data-tip="${tip}"`:'';
    const halfStep=n>1?cW/(n-1)/2:cW/2;
    const hL=(i===0?pL:cx(i)-halfStep).toFixed(1);
    const hW=(i===0?halfStep:(i===n-1?W-pR-cx(i)+halfStep:halfStep*2)).toFixed(1);
    const hit=`<rect x="${hL}" y="${pT}" width="${hW}" height="${H-pT-pB}" fill="transparent"${tipAttr}/>`;
    const dc=i>0&&!isWip?segCol(values[i]-values[i-1]):'#94a3b8';
    let dot;
    if(isWip)dot=`<circle cx="${cx(i).toFixed(1)}" cy="${cy(v).toFixed(1)}" r="4" fill="var(--surface)" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="2,2"/>`;
    else dot=`<circle cx="${cx(i).toFixed(1)}" cy="${cy(v).toFixed(1)}" r="${isLast?4:2.5}" fill="${isLast?dc:'var(--surface)'}" stroke="${dc}" stroke-width="1.5"/>`;
    return hit+dot;
  }).join('');
  return`<svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block" xmlns="http://www.w3.org/2000/svg">`
    +grid+yLbls
    +fills.join('')
    +segs.join('')
    +dots+xLbls+`</svg>`;
}

function trendNote(compVals,fmt,hi,lastIsWip,unit){
  unit=unit||'quarter';
  if(compVals.length<2)return'';
  const first=compVals[0],last=compVals[compVals.length-1];
  const d=last-first;
  const nq=compVals.length;
  const span=nq+' '+unit+(nq!==1?'s':'');
  const fv=fmt(typeof first==='number'&&!Number.isInteger(first)?+first.toFixed(1):first);
  const lv=fmt(typeof last==='number'&&!Number.isInteger(last)?+last.toFixed(1):last);
  if(Math.abs(d)<0.05)return`Held steady at ${lv} across ${span}.`;
  const improving=hi===null?null:(hi?d>=0:d<=0);
  const dir=d>0?'Up':'Down';
  const suffix=hi===null?'':(improving?' — trending well.':' — needs attention.');
  return`${dir} from ${fv} to ${lv} across ${span}.${suffix}`;
}

function _nsCapKey(projKey){return`ns_cap_${projKey}`;}
function _nsLoadOverrides(projKey){
  try{return JSON.parse(localStorage.getItem(_nsCapKey(projKey))||"{}");}catch(_){return{};}
}
function _nsSaveOverrides(projKey,overrides){
  localStorage.setItem(_nsCapKey(projKey),JSON.stringify(overrides));
}

function renderNextSprint(){
  const ns=ALL_DATA[AP]?.next_sprint||null;
  const useSp=PROJ_USE_SP||false;
  const jb=(Object.values(ALL_DATA[AP]?.qs||{})[0]?.kpis?.jira_base)||"";
  const HPD=8;
  function hd(h){const d=h/HPD;return`${h}h (${d%1===0?d:d.toFixed(1)}d)`;}
  const overrides=_nsLoadOverrides(AP);

  if(!ns||!ns.sprint_name){
    return`<div class="pane-title">Next Sprint</div>
      <div style="padding:32px 0;text-align:center;color:var(--muted)">No upcoming sprint found in Jira.</div>`;
  }

  const dateRange=(ns.start_date&&ns.end_date)
    ?` &nbsp;·&nbsp; ${fmtDate(ns.start_date,true)} – ${fmtDate(ns.end_date,true)}`
    :ns.start_date?` &nbsp;·&nbsp; starts ${fmtDate(ns.start_date,true)}`:"";
  const header=`<div class="pane-title">Next Sprint: ${e(ns.sprint_name)}</div>
    <div class="pane-desc">${ns.total_issues} issue${ns.total_issues!==1?"s":""} assigned${dateRange}.</div>`;

  if(!ns.total_issues){
    return header+`<div style="padding:24px 0;text-align:center;color:var(--muted)">Sprint exists but has no issues assigned yet.</div>`;
  }

  const stats=ns.assignee_stats||[];
  const issues=ns.issues||[];

  // Merge localStorage capacity overrides into stats
  const statsEff=stats.map(a=>{
    const ov=overrides[a.account_id||a.name];
    if(ov!=null){
      const cap=ov, tgt=Math.round(cap*0.7*10)/10;
      return{...a,capacity_h:cap,target_h:tgt,_overridden:true};
    }
    return a;
  });

  const hasOverrides=Object.keys(overrides).length>0;

  // Capacity table header
  const capHeader=`<tr>
    <th>Assignee</th>
    <th style="text-align:center">Assigned</th>
    <th style="text-align:center">Bugs / Stories / Tasks</th>
    <th style="text-align:center">Availability</th>
    <th style="text-align:center">Estimated</th>
    <th style="text-align:center">No Estimate</th>
    <th style="text-align:right;width:32px"></th>
  </tr>`;

  const capRows=statsEff.map(a=>{
    const cap=a.capacity_h||80, tgt=a.target_h||Math.round(cap*0.7*10)/10;
    const est=a.estimated_h||0;
    const jql=a.account_id
      ?`project = ${PROJ_KEY} AND sprint = ${ns.sprint_id} AND assignee = "${e(a.account_id)}" ORDER BY priority ASC`
      :`project = ${PROJ_KEY} AND sprint = ${ns.sprint_id} AND assignee is EMPTY ORDER BY priority ASC`;
    const nameCell=jb
      ?`<a class="assignee-link" href="${e(jb+'/issues/?jql='+encodeURIComponent(jql))}" target="_blank">${e(a.name)}</a>`
      :`<span style="font-weight:500">${e(a.name)}</span>`;
    const noEstCell=a.no_estimate>0
      ?`<span style="color:#ef4444;font-weight:600">${a.no_estimate}</span>`
      :`<span style="color:var(--muted)">0</span>`;
    const availCell=useSp?`<span style="color:var(--muted)">—</span>`
      :`<span title="Target (70% of ${cap}h capacity)">${hd(tgt)}</span>`;
    const col=!est?null:est>cap?"#ef4444":est>tgt?"#FCE300":"#22c55e";
    const estCell=useSp
      ?(a.sp_total?`${a.sp_total} SP`:`<span style="color:var(--muted)">—</span>`)
      :(est?`<span style="font-weight:600;color:${col}">${hd(est)}</span>`:`<span style="color:var(--muted)">—</span>`);
    const ovTag=a._overridden?`<span style="font-size:10px;color:#f59e0b;margin-left:4px" title="Capacity overridden locally">✎</span>`:'';
    const safeId=e((a.account_id||a.name).replace(/[^a-z0-9]/gi,'_'));
    const editBtn=`<button onclick="nsEditCapacity(${JSON.stringify(a.account_id||a.name)},${JSON.stringify(a.name)},${cap})"
      style="background:none;border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--muted);padding:1px 6px;font-size:11px"
      title="Edit availability">✎</button>`;
    return`<tr>
      <td>${nameCell}${ovTag}</td>
      <td style="text-align:center">${a.total}</td>
      <td style="text-align:center">${a.bugs}/${a.stories}/${a.tasks}</td>
      <td style="text-align:center">${availCell}</td>
      <td style="text-align:center">${estCell}</td>
      <td style="text-align:center">${noEstCell}</td>
      <td style="text-align:right">${editBtn}</td>
    </tr>`;
  }).join("");

  const exportBtn=hasOverrides
    ?`<button onclick="nsExportOverrides()" style="margin-left:12px;background:none;border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--muted);padding:2px 8px;font-size:11px">Copy JSON changes</button>
      <button onclick="nsClearOverrides()" style="margin-left:6px;background:none;border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--muted);padding:2px 8px;font-size:11px">Clear overrides</button>`
    :'';

  const capTable=`<div class="section-label" style="margin-top:20px">Capacity by Assignee
    ${exportBtn}
  </div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
    Estimated: <span style="color:#22c55e;font-weight:600">●</span> within target &nbsp;
               <span style="color:#FCE300;font-weight:600">●</span> over target, within capacity &nbsp;
               <span style="color:#ef4444;font-weight:600">●</span> over capacity &nbsp;·&nbsp;
               Availability = 70% of capacity (buffer for meetings/unplanned work)
  </div>
  <table class="iss-table"><thead>${capHeader}</thead><tbody>${capRows}</tbody></table>`;

  // Issues list — no-estimate first, then by assignee + priority
  const priOrder={"Highest":0,"High":1,"Medium":2,"Low":3,"Lowest":4};
  const sorted=[...issues].sort((a,b)=>{
    const aNoEst=a.has_estimate?1:0,bNoEst=b.has_estimate?1:0;
    if(aNoEst!==bNoEst)return aNoEst-bNoEst;
    if(a.assignee<b.assignee)return -1;
    if(a.assignee>b.assignee)return 1;
    return (priOrder[a.priority]??5)-(priOrder[b.priority]??5);
  });

  const noEstCount=issues.filter(i=>!i.has_estimate).length;
  const noEstBanner=noEstCount>0
    ?`<div class="alert alert-warn" style="font-size:12px;margin-bottom:8px">⚠ ${noEstCount} issue${noEstCount!==1?"s":""} have no estimate — availability comparison above may be understated.</div>`
    :"";

  const issueCols=`<tr><th>Key</th><th>Summary</th><th>Type</th><th>Assignee</th><th>Priority</th><th style="text-align:center">${useSp?"SP":"Est."}</th></tr>`;
  const issueRows=sorted.map(i=>{
    const noEst=!i.has_estimate;
    const rowStyle=noEst?` style="background:rgba(239,68,68,0.06)"`:`` ;
    const priC=i.priority==="Highest"||i.priority==="High"?"color:#ef4444":i.priority==="Medium"?"color:#f59e0b":"color:var(--muted)";
    const keyCell=jb?`<a href="${e(i.url)}" target="_blank" style="font-weight:600">${e(i.key)}</a>`:`<span style="font-weight:600">${e(i.key)}</span>`;
    const estCell=useSp
      ?(i.sp>0?`${i.sp} SP`:`<span style="color:#ef4444;font-weight:600">missing</span>`)
      :(i.estimated_h>0?hd(i.estimated_h):`<span style="color:#ef4444;font-weight:600">missing</span>`);
    return`<tr${rowStyle}>
      <td>${keyCell}</td>
      <td style="max-width:300px">${e(i.summary)}</td>
      <td>${e(i.type)}</td>
      <td>${e(i.assignee)}</td>
      <td style="${priC}">${e(i.priority||"—")}</td>
      <td style="text-align:center">${estCell}</td>
    </tr>`;
  }).join("");

  const issueTable=`<div class="section-label" style="margin-top:28px">All Issues</div>
    ${noEstBanner}
    <table class="iss-table"><thead>${issueCols}</thead><tbody>${issueRows}</tbody></table>`;

  return header+capTable+issueTable;
}

function nsEditCapacity(accountId,name,currentCap){
  const val=prompt(`Availability for ${name}\nEnter total sprint capacity in hours (current: ${currentCap}h).\nExample: 64 = 4 days/week × 8h × 2 weeks`,currentCap);
  if(val===null)return;
  const h=parseFloat(val);
  if(isNaN(h)||h<=0){alert("Please enter a valid number of hours.");return;}
  // Save locally for immediate preview
  const overrides=_nsLoadOverrides(AP);
  overrides[accountId]=h;
  _nsSaveOverrides(AP,overrides);
  document.querySelector('[data-pane="nextsp"]').innerHTML=renderNextSprint();
  // Push to HA webhook if configured — HA will update team JSON and trigger a re-run
  if(PROJ_CAPACITY_UPDATE_WEBHOOK){
    fetch(PROJ_CAPACITY_UPDATE_WEBHOOK,{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({project:AP,account_id:accountId,name:name,capacity_h:h}),
    }).then(r=>{
      if(!r.ok)console.warn("Capacity webhook returned",r.status);
    }).catch(err=>console.warn("Capacity webhook error:",err));
  }
}

function nsExportOverrides(){
  const overrides=_nsLoadOverrides(AP);
  const ns=ALL_DATA[AP]?.next_sprint||null;
  if(!ns)return;
  const stats=ns.assignee_stats||[];
  const lines=stats
    .filter(a=>overrides[a.account_id||a.name]!=null)
    .map(a=>{
      const cap=overrides[a.account_id||a.name];
      return`  // ${a.name}: set capacity_h to ${cap} (${cap/8}d)\n  "capacity_h": ${cap}`;
    });
  const msg=`Add "capacity_h" to each person's entry in the team JSON file:\n\n${lines.join("\n\n")}\n\nExample:\n"accountId": {"name": "Person", "capacity_h": ${Object.values(overrides)[0]||64}}`;
  prompt("Copy these changes into your team JSON file, then re-run the script:",msg);
}

function nsClearOverrides(){
  if(!confirm("Clear all local capacity overrides for this project?"))return;
  localStorage.removeItem(_nsCapKey(AP));
  document.querySelector('[data-pane="nextsp"]').innerHTML=renderNextSprint();
}

function renderTrends(){
  const now=new Date();
  const curLabel=`Q${Math.floor(now.getMonth()/3)+1} ${now.getFullYear()}`;
  const showExclOn=localStorage.getItem(`showExcl_${PROJ_KEY}`)==='1';
  // All quarters oldest→newest; keep last trendWindow, always append current if present
  const allOldestFirst=Object.keys(QS).slice().reverse();
  const completed=allOldestFirst.filter(q=>q!==curLabel);
  const hasCurrent=QS[curLabel]!==undefined;
  const windowed=completed.slice(-trendWindow);
  // If current quarter exists, append it (marked WIP) but only if we have room or it's the only one
  const qs=hasCurrent?[...windowed,curLabel]:windowed;
  const lastIsWip=hasCurrent;
  // Sprint trends need ≥2 sprints in the current quarter — quarterly trends need ≥2 quarters.
  // Check sprint data BEFORE blocking, so a project with only 1 quarter can still show sprint trends.
  const _MBase=[
    {k:'completion_rate',  lbl:'Completion Rate',  fmt:v=>v+'%', hi:true,
     desc:'% of sprint items that reached Done. Core measure of delivery against commitment.'},
    {k:'completed',        lbl:'Items Completed',  fmt:v=>v,     hi:true,
     desc:'Total issues moved to Done across all sprints in the quarter.'},
    {k:'total',            lbl:'Total Items',      fmt:v=>v,     hi:true,
     desc:'All issues across the quarter\'s sprints, regardless of status.'},
    {k:'releases_shipped', lbl:'Releases Shipped', fmt:v=>v,     hi:true,
     desc:'Number of fix versions marked as released — proxy for customer-facing delivery.'},
    ...(PROJ_USE_OOS?[{k:'oos_pct',lbl:'OOS Rate',fmt:v=>v+'%',hi:false,
     since:'Q2 2025',sinceNote:'Out-of-Sprint tracking introduced',
     desc:'% of items added to a sprint after it started (Out Of Sprint label). High values indicate scope creep or poor planning.'}]:[]),
    {k:'bug_pct',          lbl:'Bug %',            fmt:v=>v+'%', hi:false,
     desc:'Bugs as a % of all sprint items. Rising trend signals quality or tech-debt concerns.'},
    {k:'rollover_pct',     lbl:'Rollover Rate',    fmt:v=>v+'%', hi:false,
     desc:'% of items from closed sprints still not completed. High values suggest over-commitment or items abandoned without resolution.'},
    {k:'avg_cycle_days',   lbl:'Avg Cycle Time',   fmt:v=>v+'d', hi:false,
     desc:'Average days from "In Progress" to Done for completed items. Excludes items closed without being worked on.'},
    {k:'tickets_per_day',  lbl:'Tickets / Day',    fmt:v=>v,     hi:true,
     desc:'Completed items divided by calendar days elapsed in the quarter. Normalises velocity across quarters of different lengths.'},
  ];
  const _MTime=[
    {k:'time_logged_h',         lbl:'Hours Logged',      fmt:v=>v+'h', hi:true,
     autoSince:true, sinceNote:'Time logging adopted',
     desc:'Total hours logged against sprint items. Low values may indicate poor time-tracking discipline.'},
    {k:'estimate_accuracy_pct', lbl:'Estimate Accuracy', fmt:v=>v+'%', hi:true,
     autoSince:true, sinceNote:'Time tracking adopted',
     desc:'How closely logged hours matched estimates (100% = exact). Measures planning discipline, not effort.'},
    {k:'no_estimate_pct',       lbl:'Missing Estimates', fmt:v=>v+'%', hi:false,
     autoSince:true, autoSinceKey:'time_logged_h', sinceNote:'Time tracking adopted',
     desc:'% of items with no time estimate set. High values undermine sprint planning and capacity tracking.'},
  ];
  const _MSp=[
    {k:'sp_completed',    lbl:'SP Completed',       fmt:v=>v,     hi:true,
     desc:'Total story points moved to Done this quarter.'},
    {k:'sp_velocity_avg', lbl:'SP Velocity (avg)',  fmt:v=>v,     hi:true,
     desc:'Average story points completed per closed sprint. A rising trend indicates increasing team throughput.'},
    {k:'no_estimate_pct', lbl:'Missing SP Est',     fmt:v=>v+'%', hi:false,
     desc:'% of items with no story points set. High values undermine velocity reporting.'},
  ];
  const useSp=PROJ_USE_SP||false;
  const M=[..._MBase,...(useSp?_MSp:_MTime)];
  const wipNote=hasCurrent?`<p style="font-size:12px;color:var(--muted);margin-bottom:16px">` +
    `<span style="display:inline-flex;align-items:center;gap:6px">` +
    `<svg width="24" height="10" viewBox="0 0 24 10"><line x1="0" y1="5" x2="24" y2="5" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,3"/></svg>` +
    `${e(curLabel)} is in progress — shown dashed, excluded from trend direction.</span></p>`:'';
  // Sprint trends data
  const perSprint=QS[cur]?.kpis?.per_sprint||{};
  const sprintList=(QS[cur]?.sprints||[]).slice().sort((a,b)=>a.id-b.id);
  const hasSprints=sprintList.length>=2&&Object.keys(perSprint).length>=2;

  // Not enough data for either mode — show early exit
  if(qs.length<2&&!hasSprints)
    return'<div class="nodata">At least 2 sprints are needed for sprint trends, or 2 quarters for quarterly trends.</div>';
  // Only 1 quarter available — auto-switch to sprint mode if possible
  if(qs.length<2&&trendsMode==="quarterly") trendsMode="sprint";

  // Mode toggle
  const modeToggle='<div class="trend-controls" style="margin-bottom:0"><span>Mode:</span>'
    +'<button class="twb'+(trendsMode==="quarterly"?" active":"")+'" onclick="trendsMode=\'quarterly\';document.querySelector(\'[data-pane=trends]\').innerHTML=renderTrends()">Quarterly</button>'
    +(hasSprints?'<button class="twb'+(trendsMode==="sprint"?" active":"")+'" onclick="trendsMode=\'sprint\';document.querySelector(\'[data-pane=trends]\').innerHTML=renderTrends()">Sprints ('+e(cur)+')</button>':"")
    +"</div>";

  // Sprint trends view
  if(trendsMode==="sprint"&&hasSprints){
    const _SMBase=[
      {k:"completion_rate", lbl:"Completion Rate", fmt:function(v){return v+"%";}, hi:true,  desc:"% of sprint items that reached Done."},
      {k:"completed",       lbl:"Items Completed", fmt:function(v){return v;},     hi:true,  desc:"Issues moved to Done in this sprint."},
      {k:"total",           lbl:"Total Items",     fmt:function(v){return v;},     hi:true,  desc:"All issues in this sprint."},
      {k:"rollover_pct",    lbl:"Rollover Rate",   fmt:function(v){return v+"%";}, hi:false, desc:"% of items carried forward from an earlier sprint this quarter."},
      {k:"bug_pct",         lbl:"Bug %",           fmt:function(v){return v+"%";}, hi:false, desc:"Bugs as % of all sprint items."},
      {k:"avg_cycle_days",  lbl:"Avg Cycle Time",  fmt:function(v){return v+"d";}, hi:false, desc:"Average days In Progress to Done."},
    ];
    const _SMTime=[
      {k:"time_logged_h",         lbl:"Hours Logged",      fmt:function(v){return v+"h";}, hi:true, desc:"Total hours logged by the team."},
      {k:"estimate_accuracy_pct", lbl:"Estimate Accuracy", fmt:function(v){return v+"%";}, hi:true, desc:"Logged vs estimated hours accuracy."},
    ];
    const _SMSp=[
      {k:"sp_total",     lbl:"SP Planned",    fmt:function(v){return v;}, hi:true,  desc:"Story points committed this sprint."},
      {k:"sp_completed", lbl:"SP Completed",  fmt:function(v){return v;}, hi:true,  desc:"Story points completed this sprint."},
    ];
    const SM=[..._SMBase,...(useSp?_SMSp:_SMTime)];
    const sIds=sprintList.map(function(s){return String(s.id);});
    const sLbls=sprintList.map(function(s){return s.name.replace(/.*Sprint\s*/i,"S");});
    const lastState=sprintList[sprintList.length-1].state;
    const lastIsActive=lastState==="active";
    const closed=sprintList.map(function(s){return s.state.toLowerCase()==="closed";});
    // Indices of closed sprints for delta comparison
    const closedIdxs=closed.reduce(function(a,v,i){if(v)a.push(i);return a;},[]);
    const spNote=activeSprint?'<span class="trend-info" data-tip="Sprint selection does not filter Trends — all sprints within the quarter are always compared." style="vertical-align:middle;margin-left:6px">&#x2139;</span>':'';
    return '<div class="pane-title">Trends</div>'
      +'<div class="pane-desc">Sprint-on-sprint movement within '+e(cur)+'.'+spNote+'</div>'
      +modeToggle+'<br><div class="trend-grid">'+SM.map(function(m){
        const vals=sIds.map(function(sid){const sp=perSprint[sid]||{};return+(_adjKpis(sp,sp.excl_summary_stats||{},showExclOn)[m.k]||0);});
        const compVals=vals.filter(function(_,i){return closed[i];});
        const tipVals=sIds.map(function(sid,i){const sp=perSprint[sid]||{};return sLbls[i]+": "+m.fmt(+(_adjKpis(sp,sp.excl_summary_stats||{},showExclOn)[m.k]||0));});
        // Delta between last two closed sprints
        const cv=compVals[compVals.length-1]??vals[vals.length-1];
        const pv=compVals[compVals.length-2]??cv;
        const d=cv-pv;
        const improving=m.hi?d>=0:d<=0;
        let dcls='flat',dstr='—';
        if(d!==0){dcls=improving?'pos':'neg';dstr=(d>0?'+':'')+(Number.isInteger(d)?d:d.toFixed(1));}
        const dispVal=lastIsActive?vals[vals.length-1]:cv;
        const wipSub=lastIsActive?'<div class="trend-val-sub">'+e(sLbls[sLbls.length-1])+' · in progress</div>':'';
        // Delta label: "S94 → S95" using last two closed sprint labels
        const prevLbl=closedIdxs.length>=2?sLbls[closedIdxs[closedIdxs.length-2]]:null;
        const curLbl =closedIdxs.length>=1?sLbls[closedIdxs[closedIdxs.length-1]]:null;
        const deltaLbl=prevLbl&&curLbl?'<div class="delta-lbl">'+e(prevLbl)+' → '+e(curLbl)+'</div>':'';
        const infoIcon=m.desc?'<span class="trend-info" data-tip="'+e(m.desc)+'">&#x2139;</span>':'';
        const note=trendNote(compVals,m.fmt,m.hi,false,'sprint');
        if(vals.length<2)return'<div class="trend-card"><div class="trend-lbl">'+e(m.lbl)+infoIcon+'</div>'
          +'<p style="font-size:12px;color:var(--muted);padding:12px 0">Not enough data</p></div>';
        return'<div class="trend-card">'
          +'<div class="trend-hdr"><div><div class="trend-lbl">'+e(m.lbl)+infoIcon+'</div>'
          +'<div class="trend-val">'+e(String(m.fmt(dispVal)))+'</div>'+wipSub+'</div>'
          +'<div style="text-align:right;flex-shrink:0">'+deltaLbl+'<span class="trend-delta '+dcls+'">'+e(dstr)+'</span></div></div>'
          +mkLineChart(vals,sLbls,m.hi,lastIsActive,tipVals)
          +(note?'<div class="trend-note">'+e(note)+'</div>':'')
          +'</div>';
      }).join("")+"</div>";
  }

  const winOpts=[{w:4,l:"4Q"},{w:6,l:"6Q"},{w:8,l:"8Q"},{w:9999,l:"All"}];
  const winCtrl='<div class="trend-controls"><span>Show:</span>'
    +winOpts.map(function(o){return'<button class="twb'+(trendWindow===o.w?" active":"")+'" data-w="'+o.w+'">'+o.l+"</button>";}).join("")
    +"</div>";
  function qOrd(q){const[qn,yr]=q.split(' ');return+yr*4+(+qn[1]);}
  function firstNonZero(allQs,k){for(const q of allQs){if(+(QS[q]?.kpis[k]??0)>0)return q;}return null;}
  const qNote=activeSprint?'<span class="trend-info" data-tip="Sprint selection does not filter Trends — all quarters are always shown." style="vertical-align:middle;margin-left:6px">&#x2139;</span>':'';
  return '<div class="pane-title">Trends</div>'
    +'<div class="pane-desc">Quarter-on-quarter movement across key metrics. Green = improving, red = declining.'+qNote+'</div>'
    +modeToggle+"<br>"+winCtrl+wipNote+'<div class="trend-grid">'+M.map(m=>{
    // Per-metric since filtering — exclude quarters before this metric was tracked
    const mSince=m.since||(m.autoSince?firstNonZero(qs,m.autoSinceKey||m.k):null);
    const sinceOrd=mSince?qOrd(mSince):0;
    const mQs=sinceOrd?qs.filter(q=>qOrd(q)>=sinceOrd):qs;
    const mLbls=mQs.map(q=>q.replace(' ','·'));
    const mLastIsWip=lastIsWip&&mQs[mQs.length-1]===curLabel;
    const trimmed=mQs.length<qs.length;
    const vals=mQs.map(q=>{const qk=QS[q]?.kpis||{};return+(_adjKpis(qk,qk.excl_summary_stats||{},showExclOn)[m.k]??0);});
    // Delta uses last 2 completed points only
    const compVals=mLastIsWip?vals.slice(0,-1):vals;
    const cur=compVals[compVals.length-1]??vals[vals.length-1];
    const prev=compVals[compVals.length-2]??cur;
    const d=cur-prev;
    const improving=m.hi===null?null:(m.hi?d>=0:d<=0);
    let dcls='flat',dstr='—';
    if(d!==0){
      dcls=m.hi===null?'flat':improving?'pos':'neg';
      dstr=(d>0?'+':'')+(Number.isInteger(d)?d:d.toFixed(1));
    }
    const dispVal=mLastIsWip?vals[vals.length-1]:cur;
    const wipSub=mLastIsWip?`<div class="trend-val-sub">${e(mQs[mQs.length-1])} · in progress</div>`:'';
    // For the releases card, show the last release date of the displayed quarter
    let extraSub='';
    if(m.k==='releases_shipped'){
      const dispQ=mLastIsWip?mQs[mQs.length-1]:(mQs[compVals.length-1]||mQs[mQs.length-1]);
      const lrd=(QS[dispQ]?.kpis?.last_release_date)||'';
      if(lrd)extraSub=`<div class="trend-val-sub">last: ${e(lrd)}</div>`;
    }
    const prevQ=compVals.length>=2?mQs[compVals.length-2]:null;
    const curQ =compVals.length>=1?mQs[compVals.length-1]:null;
    const deltaLbl=prevQ&&curQ?`<div class="delta-lbl">${e(prevQ)} → ${e(curQ)}</div>`:'';
    const note=trendNote(compVals,m.fmt,m.hi,mLastIsWip);
    const tipVals=mQs.map((q,i)=>q+': '+m.fmt(vals[i]));
    const infoIcon=m.desc?`<span class="trend-info" data-tip="${e(m.desc)}">&#x2139;</span>`:'';
    const sinceNote=trimmed?`<div class="trend-note" style="opacity:.7">&#x2139; ${e(m.sinceNote)} — data from ${e(mSince||'')} onwards.</div>`:'';
    if(mQs.length<2)return`<div class="trend-card"><div class="trend-lbl">${e(m.lbl)}${infoIcon}</div>`
      +`<p style="font-size:12px;color:var(--muted);padding:12px 0">Not enough data</p>${sinceNote}</div>`;
    return`<div class="trend-card">`
      +`<div class="trend-hdr"><div><div class="trend-lbl">${e(m.lbl)}${infoIcon}</div>`
      +`<div class="trend-val">${e(String(m.fmt(dispVal)))}</div>`
      +wipSub+extraSub
      +`</div><div style="text-align:right;flex-shrink:0">${deltaLbl}<span class="trend-delta ${dcls}">${e(dstr)}</span></div></div>`
      +mkLineChart(vals,mLbls,m.hi,mLastIsWip,tipVals)
      +(note?`<div class="trend-note">${e(note)}</div>`:'')
      +sinceNote
      +`</div>`;
  }).join('')+'</div>';
}

/* ---- Init ---- */
if(!ordered.length){
  document.getElementById("dash").innerHTML=`<div class="nodata">No quarter data available.</div>`;
}else{
  const _initTab=(!PROJ_USE_OOS&&_OOS_ONLY_TABS.includes(_lsTab))?"overview":_lsTab;
  render(ordered[0],_initTab);
}

/* ---- Trend window selector ---- */
document.body.addEventListener('click',ev=>{
  const btn=ev.target.closest('.twb');
  if(!btn)return;
  trendWindow=+btn.dataset.w;
  const pane=document.querySelector('[data-pane="trends"]');
  if(pane)pane.innerHTML=renderTrends();
});

/* ---- Hover tooltip for chart data points ---- */
document.body.addEventListener('mousemove',ev=>{
  const t=ev.target.closest('[data-tip]');
  const tt=document.getElementById('tt');
  if(t){
    tt.textContent=t.dataset.tip;
    tt.classList.add('vis');
    // Position above cursor, clamped so it never bleeds off screen edges
    const pad=8,vw=window.innerWidth,vh=window.innerHeight;
    const tw=tt.offsetWidth,th=tt.offsetHeight;
    let x=ev.clientX-tw/2;
    let y=ev.clientY-th-12;
    if(x<pad)x=pad;
    if(x+tw>vw-pad)x=vw-tw-pad;
    if(y<pad)y=ev.clientY+18; // flip below cursor if too close to top
    tt.style.left=x+'px';
    tt.style.top=y+'px';
  }else{
    tt.classList.remove('vis');
  }
});