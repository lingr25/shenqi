/* ============================================================
   神祇读神奇 · 方舟底层机制工作台 — views & router
   ============================================================ */

/* ---------- footer ---------- */
document.getElementById('footer').innerHTML = `
  <div>神祇读神奇 · 方舟底层机制工作台 — 基于 <span class="mono">kb_trial/curated_high_quality.json</span>（schema ${esc(DB.schema_version)} · ${DB.entries.length} 条）离线生成 · 生成日期 ${esc(DB.built)}</div>
  <div>本页面为<b>草稿层（draft）知识产品</b>：全部结论的置信上限为「文本出处支持」（text-source-supported），审核基于转写文本逐条比对，<b>未核听原片音画、未做游戏内实测</b>；「全部已审」不等于「全部正确」。用于生产前请回看引文所指时刻的原片。</div>
  <div>非官方粉丝归档，与鹰角网络、B 站无关；机制结论以游戏实际版本为准。群聊引文已脱敏（不含群号、QQ 号与昵称）。内容许可：CC BY-NC-SA 4.0 · 代码许可：MIT</div>`;

/* ---------- overview ---------- */
function renderOverview(){
  const st = DB.stats;
  const featured = ENTRIES.filter(e=>e.rv==='user_verified');
  const months = Object.entries(st.months).sort();
  const maxM = Math.max(...months.map(m=>m[1]), 1);
  return `
  <section id="hero">
    <div class="kicker">MECHANICS WORKBENCH · 双轨互证 · 逐字溯源</div>
    <h1>明日方舟<em>底层机制</em>终极工作台</h1>
    <p class="sub">把硬核机制主播「神祇读神奇」的录播推导与核心机制群的拆包实测，压缩成 ${DB.entries.length} 条可检索、可交叉、可证伪的原子规则。每一条结论都能展开到逐字引文，录播条目一键跳回 B 站原片精确秒数。</p>
    <div class="statband">
      <div class="stat"><div class="n">${DB.entries.length}</div><div class="l">甄选原子规则</div></div>
      <div class="stat"><div class="n blue">${st.tracks.vod}</div><div class="l">录播轨条目</div></div>
      <div class="stat"><div class="n gold">${st.tracks.qq}</div><div class="l">群聊实测条目</div></div>
      <div class="stat"><div class="n">${st.bv_count}</div><div class="l">覆盖录播分P</div></div>
      <div class="stat"><div class="n gold">${st.user_verified}</div><div class="l">★ 用户认证</div></div>
      <div class="stat"><div class="n">${TOPICS.length}</div><div class="l">专题板块</div></div>
    </div>
    <div class="startpath">
      <a href="#/topics"><b>→</b>第一次来？从专题讲义进入知识版图</a>
      <a href="#/constants"><b>▦</b>直接查核心常数速查表</a>
      <a href="#/search"><b>⌕</b>已知关键词，去检索终端</a>
    </div>
  </section>

  <div class="notice" style="margin-top:16px">
    <b>阅读前须知：</b>本库为草稿层甄选结果，非官方发布、非权威结论。所有判定均基于转写文本（官方 AI 字幕 / 云端 ASR / 脱敏群聊片段）逐条比对，<b>未核听原片、未做游戏内实测</b>；官方字幕中的 ASR 讹写不代表主播原话。录播与群聊结论冲突时并列呈现，不做自动裁决。
  </div>

  <h3 style="margin:26px 0 14px;font-size:17px">知识版图 <span class="faint small mono">KNOWLEDGE MAP</span></h3>
  <div class="topicgrid">
    ${TOPICS.map(t=>{
      const list = ENTRIES.filter(e=>e.tp===t.id);
      return `<a class="tcard" style="--tc:${t.color}" href="#/topic/${t.id}">
        <div class="tc-name"><span class="tc-dot"></span>${t.name}</div>
        <div class="tc-en">${t.en}</div>
        <div class="tc-intro">${t.intro}</div>
        ${trackBarHTML(trackCounts(list))}
        <div class="tc-meta"><span class="tc-count">${list.length} 条</span><span class="faint">进入专题 →</span></div>
      </a>`;
    }).join('')}
  </div>

  <div class="grid" style="grid-template-columns:1.2fr 1fr;margin-top:26px">
    <div class="panel">
      <h3>收录时间线（录得月份）</h3>
      <div class="hist">
        ${months.map(([m,n])=>`<div class="bar"><b>${n}</b><i style="height:${Math.max(4, n/maxM*72)}px"></i><span>${m==='null'?'未标注':String(m).replace(/(\d{4})(\d{2})/,'$1-$2')}</span></div>`).join('')}
      </div>
      <p class="small faint" style="margin-top:10px">「录得」指该机制讨论发生的年月（按来源时间归并），未标注多为早期录播批次。</p>
    </div>
    <div class="panel">
      <h3>双轨互证机制</h3>
      <p class="small dim">每条规则标注来源轨：<span class="bdg tr-vod_official">录播 · 官方字幕</span> <span class="bdg tr-vod_cloud">录播 · 云端ASR</span> <span class="bdg tr-qq">群聊实测 · QQ</span> <span class="bdg tr-mixed_or_unknown">双轨混合</span></p>
      <p class="small dim" style="margin-top:8px">录播轨承载主播的系统推导与实机演示，精确到秒可回原片核对；群聊轨承载 22.7 万条讨论中沉淀的拆包数据、实测帧数与追问答疑（已脱敏）。两轨结论冲突时并列保留，留待人工判断 —— 本工作台不做自动裁决。</p>
      <p class="small dim" style="margin-top:8px">审核状态：<span class="bdg userver">★ 用户认证</span> 为用户明确评价「优秀」的整卡；<span class="bdg agentver">代理审核·文本层</span> 为代理逐条读源比对确认（置信上限：文本出处支持）。</p>
    </div>
  </div>

  <h3 style="margin:30px 0 14px;font-size:17px">★ 用户认证条目 <span class="faint small mono">${featured.length} 条 · 用户明确评价「优秀」</span></h3>
  ${featured.map(e=>entryCard(e,'',true)).join('')}
  `;
}

/* ---------- topics ---------- */
function renderTopics(){
  return `
  <h2 style="margin-bottom:6px">专题讲义</h2>
  <p class="dim" style="max-width:820px;margin-bottom:20px">参照人类讲义《机制合订本》的章节脉络，将 ${DB.entries.length} 条原子规则组织为 ${TOPICS.length} 个专题板块。每个专题按子类分组通读，随时展开证据链核原文。认知顺序建议：先「帧时序」建立逐帧世界观，再依次进入寻路、位移、索敌、伤害。</p>
  <div class="topicgrid">
    ${TOPICS.map(t=>{
      const list = ENTRIES.filter(e=>e.tp===t.id);
      return `<a class="tcard" style="--tc:${t.color}" href="#/topic/${t.id}">
        <div class="tc-name"><span class="tc-dot"></span>${t.name}</div>
        <div class="tc-en">${t.en}</div>
        <div class="tc-intro">${t.intro}</div>
        ${trackBarHTML(trackCounts(list))}
        <div class="tc-meta"><span class="tc-count">${list.length} 条</span><span class="faint">开始阅读 →</span></div>
      </a>`;
    }).join('')}
  </div>`;
}

function renderTopicDetail(tid){
  const t = TP_BY_ID[tid];
  if (!t) return `<p class="dim">未知专题。</p>`;
  const list = ENTRIES.filter(e=>e.tp===tid);
  const groups = {};
  list.forEach(e=>{ (groups[e.cat] = groups[e.cat]||[]).push(e); });
  const cats = Object.entries(groups).sort((a,b)=>b[1].length-a[1].length);
  const entCount = {};
  list.forEach(e=>(e.ents||[]).forEach(n=>{entCount[n]=(entCount[n]||0)+1;}));
  const topEnts = Object.entries(entCount).sort((a,b)=>b[1]-a[1]).slice(0,14);
  return `
  <div class="tplayout">
    <div class="tprail">
      ${TOPICS.map(x=>`<a href="#/topic/${x.id}" class="${x.id===tid?'on':''}"><span>${x.name}</span><span class="n">${ENTRIES.filter(e=>e.tp===x.id).length}</span></a>`).join('')}
    </div>
    <div>
      <div class="chapter-head" style="--tc:${t.color}">
        <div class="en">${t.en}</div>
        <h2>${t.name}</h2>
        <p>${t.intro_long||t.intro}</p>
        <div style="margin-top:10px;display:flex;gap:14px;align-items:center;flex-wrap:wrap">
          <span class="mono" style="color:${t.color};font-size:18px;font-weight:700">${list.length} 条规则</span>
          <div style="width:220px">${trackBarHTML(trackCounts(list))}</div>
        </div>
        ${topEnts.length?`<div style="margin-top:10px">${topEnts.map(([n,c])=>`<span class="entchip" data-act="ent" data-v="${esc(n)}">${esc(n)}<span class="c">${c}</span></span>`).join('')}</div>`:''}
      </div>
      ${cats.map(([cat, items])=>`
        <div class="subcat" style="--tc:${t.color}">${esc(cat)} <span class="faint mono" style="font-size:11px">${items.length}</span></div>
        ${items.map(e=>entryCard(e,'',false)).join('')}
      `).join('')}
    </div>
  </div>`;
}

/* ---------- search ---------- */
let FACETS = {};
function renderSearch(params){
  const q = params.get('q')||'';
  FACETS = {
    topic: params.get('topic')||'',
    track: params.get('track')||'',
    review: params.get('review')||'',
    scope: params.get('scope')||'',
  };
  const results = searchEntries(q, (FACETS.topic||FACETS.track||FACETS.review||FACETS.scope)?FACETS:null);
  const shown = results.slice(0, 300);
  const facetGroup = (title, key, opts)=>`
    <div class="facet"><h4>${title}</h4>
      ${opts.map(([v,l])=>`<button class="fchip ${FACETS[key]===v?'on':''}" data-act="facet" data-k="${key}" data-v="${v}">${l}</button>`).join('')}
    </div>`;
  return `
  <div class="searchlayout">
    <div>
      ${facetGroup('专题 TOPIC','topic', TOPICS.map(t=>[t.id, t.name]))}
      ${facetGroup('来源轨 TRACK','track', [['vod','录播轨'],['vod_official','官方字幕'],['vod_cloud','云端ASR'],['qq','群聊轨'],['mixed_or_unknown','双轨混合']])}
      ${facetGroup('审核 REVIEW','review', [['user_verified','★ 用户认证'],['agent_verified','代理审核']])}
      ${facetGroup('范围 SCOPE','scope', [['universal','通用机制'],['general_mechanism','通用(旧标)'],['entity_mechanism','实体机制'],['instance','特例实例']])}
      ${(FACETS.topic||FACETS.track||FACETS.review||FACETS.scope)?`<button class="btn" data-act="clearfacets">清空全部筛选</button>`:''}
    </div>
    <div>
      <input id="searchbox" placeholder="输入机制名 / 干员 / 黑话 / 常数，空格分隔多词（AND）…" value="${esc(q)}">
      <div id="resmeta">${q||FACETS.topic||FACETS.track?`${results.length} 条命中 · 显示前 ${shown.length} 条`:`输入关键词开始检索；或直接用左侧筛选浏览全部 ${ENTRIES.length} 条`}</div>
      <div id="results">${shown.map(r=>entryCard(r.e, q, true)).join('')}</div>
    </div>
  </div>`;
}

/* ---------- constants ---------- */
function renderConstants(){
  return `
  <h2 style="margin-bottom:6px">常数速查</h2>
  <p class="dim" style="max-width:820px;margin-bottom:18px">主表摘自人类讲义《机制合订本》附录 A（单轨线性总结，仅供参考对比）；点击任意一行即可跳入检索终端，用甄选库中可溯源的原子规则交叉验证。下方「语料高频数值」为从 ${DB.entries.length} 条规则正文中自动聚类的数字出现榜。</p>
  <div class="panel">
    <h3>核心常数表 · 源自讲义附录 A</h3>
    <table class="ctable">
      <tr><th style="width:170px">常数</th><th>数值与说明</th><th style="width:90px"></th></tr>
      ${DB.constants.map(c=>`<tr>
        <td class="cv">${esc(c.n)}</td>
        <td class="dim">${esc(c.v)}</td>
        <td><span class="cq mono small" data-act="goq" data-v="${esc(c.q)}" style="color:var(--acc)">查证 →</span></td>
      </tr>`).join('')}
    </table>
  </div>
  <div class="panel" style="margin-top:18px">
    <h3>语料高频数值 <span class="faint small mono">自动聚类 · 点击检索</span></h3>
    <div>${DB.nums.map(n=>`<span class="numchip" data-act="goq" data-v="${esc(n.t)}"><b>${esc(n.t)}</b><span class="c">×${n.c}</span></span>`).join('')}</div>
  </div>`;
}

/* ---------- entities ---------- */
function renderEntities(){
  const groups = {};
  DB.entities.forEach(en=>{ (groups[en.ty]=groups[en.ty]||[]).push(en); });
  const order = ['operator','enemy','mechanic','shenqi_slang','slang','device','status','untyped'];
  return `
  <h2 style="margin-bottom:6px">实体索引</h2>
  <p class="dim" style="max-width:820px;margin-bottom:18px">基于统一实体索引（PRTS 别名 + QQ 黑话消歧）对全库规则做实体挂接。点击任一实体，检索其全部相关规则。</p>
  ${order.filter(ty=>groups[ty]).map(ty=>`
    <div class="panel" style="margin-bottom:14px">
      <h3>${ENT_TYPE_LABEL[ty]||ty} <span class="faint small mono">${groups[ty].length}</span></h3>
      <div>${groups[ty].map(en=>`<span class="entchip" data-act="goq" data-v="${esc(en.n)}">${esc(en.n)}<span class="c">${en.c}</span></span>`).join('')}</div>
    </div>`).join('')}`;
}

/* ---------- entry permalink ---------- */
function renderEntry(id){
  const e = BY_ID[id];
  if (!e) return `<p class="dim">条目不存在：${esc(id)}</p>`;
  const t = TP_BY_ID[e.tp];
  return `
  <p class="small" style="margin-bottom:14px"><a href="#/topic/${e.tp}" style="color:${t.color}">← 返回专题「${t.name}」</a></p>
  ${entryCard(e,'',true).replace('class="entry"','class="entry open showr"')}
  <div class="panel" style="margin-top:14px">
    <h3>数据血缘</h3>
    <dl class="kv">
      <dt>条目 ID</dt><dd class="mono small">${esc(e.i)}</dd>
      <dt>分类</dt><dd>${esc(e.cat)}（专题：${esc(t.name)}）</dd>
      <dt>来源轨</dt><dd>${(TRACK_META[e.tr]||{}).label||esc(e.tr)} · 来源层：${esc(e.sl||'')}</dd>
      <dt>录得时间</dt><dd>${e.ym?String(e.ym).replace(/(\d{4})(\d{2})/,'$1 年 $2 月'):'未标注'}</dd>
      <dt>审核状态</dt><dd>${e.rv==='user_verified'?'★ 用户认证':'代理审核（文本层）'} · 置信上限 text-source-supported</dd>
      <dt>冲突策略</dt><dd class="small dim">不做自动优先级裁决；来源分歧并列呈现，留待人工判断。</dd>
    </dl>
  </div>`;
}

/* ---------- about ---------- */
function renderAbout(){
  return `
  <h2 style="margin-bottom:14px">关于本工作台</h2>
  <div class="panel" style="margin-bottom:14px">
    <h3>这是什么</h3>
    <p class="small dim">《明日方舟》硬核机制主播「神祇读神奇」（B 站 UID 374873950，直播间 31229274）录播机制讲解 + 官方机制讨论群精华讨论的<b>甄选原子规则库</b>的交互式阅读终端。本页由 <span class="mono">kb_trial/curated_high_quality.json</span>（${DB.entries.length} 条，schema ${esc(DB.schema_version)}）离线生成，单文件、无外部依赖、可离线打开。</p>
    <p class="small dim" style="margin-top:8px">与人类讲义《机制合订本》的关系：讲义适合线性建立心智模型但信息有损、含 ASR 记音错字；本工作台保留全量逐字证据与多维元数据，两者互为补充（常数速查主表即摘自讲义附录 A）。</p>
  </div>
  <div class="panel" style="margin-bottom:14px">
    <h3>置信口径（务必阅读）</h3>
    <p class="small dim">全部条目的置信上限为 <b>text-source-supported</b>（文本出处支持）：审核为代理依据转写文本逐条比对，<b>未核听原片音画、未做游戏内实测</b>。官方 AI 字幕存在 ASR 讹写，字幕出现某字不等于主播确实这么说；引文一律保留原始逐字文本不动，仅在同源上下文可自证时订正派生表述（条目标注「派生订正」）。「全部已审」不等于「全部正确」。</p>
    <p class="small dim" style="margin-top:8px">审核状态：<b>★ 用户认证</b> = 用户明确评价「优秀」的整卡（${DB.stats.user_verified} 条）；<b>代理审核</b> = 代理逐条读源确认（${DB.stats.agent_verified} 条）。云端 ASR 轨权威性低于官方字幕轨。录播轨与群聊轨冲突时<b>并列呈现、不做自动裁决</b>。</p>
  </div>
  <div class="panel" style="margin-bottom:14px">
    <h3>隐私与来源</h3>
    <p class="small dim">群聊轨引文已脱敏：不含群号、QQ 号与昵称，仅保留消息文本、窗口标识与时间。录播轨引文来自 B 站官方 AI 字幕或云端 ASR 重转写（针对无官方字幕分 P），时间戳可一键跳回原片核对。</p>
  </div>
  <div class="panel">
    <h3>许可</h3>
    <p class="small dim">非官方粉丝归档，与鹰角网络、B 站无关；机制结论以游戏实际版本为准。内容：CC BY-NC-SA 4.0（署名-非商业-相同方式共享）；代码：MIT。</p>
  </div>`;
}

/* ---------- router ---------- */
function parseHash(){
  const h = location.hash.slice(2) || 'overview';
  const [path, qs] = h.split('?');
  return { parts: path.split('/'), params: new URLSearchParams(qs||'') };
}
function route(){
  const {parts, params} = parseHash();
  const v = parts[0] || 'overview';
  const view = document.getElementById('view');
  document.querySelectorAll('#nav a').forEach(a=>{
    a.classList.toggle('on', a.dataset.nav === (v==='topic'?'topics':v==='entry'?'topics':v));
  });
  if (v==='overview') view.innerHTML = renderOverview();
  else if (v==='topics') view.innerHTML = renderTopics();
  else if (v==='topic') view.innerHTML = renderTopicDetail(parts[1]);
  else if (v==='search') view.innerHTML = renderSearch(params);
  else if (v==='constants') view.innerHTML = renderConstants();
  else if (v==='entities') view.innerHTML = renderEntities();
  else if (v==='entry') view.innerHTML = renderEntry(decodeURIComponent(parts[1]||''));
  else if (v==='about') view.innerHTML = renderAbout();
  else view.innerHTML = renderOverview();
  window.scrollTo(0,0);
  const sb = document.getElementById('searchbox');
  if (sb){ sb.focus(); const L = sb.value.length; try{ sb.setSelectionRange(L,L); }catch(_){} }
}
window.addEventListener('hashchange', route);

/* ---------- events ---------- */
document.addEventListener('click', ev=>{
  const t = ev.target.closest('[data-act]');
  if (!t) return;
  const act = t.dataset.act;
  if (act==='toggle'){
    const card = t.closest('.entry');
    card.classList.toggle('open');
    t.textContent = (card.classList.contains('open')?'▼':'▶') + t.textContent.slice(1);
  } else if (act==='review'){
    t.closest('.entry').classList.toggle('showr');
  } else if (act==='ent' || act==='goq'){
    location.hash = '#/search?q=' + enc(t.dataset.v);
  } else if (act==='facet'){
    const k = t.dataset.k;
    const cur = FACETS[k];
    FACETS[k] = (cur===t.dataset.v)?'':t.dataset.v;
    syncSearchHash();
  } else if (act==='clearfacets'){
    FACETS = {topic:'',track:'',review:'',scope:''};
    syncSearchHash();
  }
});
function syncSearchHash(){
  const q = (document.getElementById('searchbox')||{}).value || (parseHash().params.get('q')||'');
  const p = new URLSearchParams();
  if (q) p.set('q', q);
  ['topic','track','review','scope'].forEach(k=>{ if (FACETS[k]) p.set(k, FACETS[k]); });
  location.hash = '#/search?' + p.toString();
}
document.addEventListener('input', ev=>{
  if (ev.target.id === 'searchbox'){
    clearTimeout(window.__st);
    window.__st = setTimeout(syncSearchHash, 350);
  }
});
document.addEventListener('keydown', ev=>{
  if ((ev.ctrlKey||ev.metaKey) && ev.key.toLowerCase()==='k'){
    ev.preventDefault();
    const gi = document.getElementById('gsearch-input');
    if (location.hash.startsWith('#/search')){ const sb=document.getElementById('searchbox'); if(sb){sb.focus();return;} }
    gi.focus(); gi.select();
  }
  if (ev.key==='Enter' && ev.target.id==='gsearch-input'){
    location.hash = '#/search?q=' + enc(ev.target.value);
  }
});

/* boot */
ENTRIES.forEach(e=>{ e.qtext = e.ev.reduce((s,c)=>s+c.q.reduce((s2,q)=>s2+' '+q.x,''),'').toLowerCase(); });
if (!location.hash) location.hash = '#/overview';
route();
