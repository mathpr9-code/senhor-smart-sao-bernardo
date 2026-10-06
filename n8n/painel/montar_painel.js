// n8n Code node: "Montar Painel"
// Recebe o JSON de senhor_smart_at.painel() e devolve a página HTML do painel ao vivo.
// Só apresentação: nenhum número é calculado aqui além de proporções para desenhar.

const f = $('Ler filtros').first().json;
const p = $('Painel').first().json.p || {};
const k = p.kpis || {};

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const n = (v) => Number(v || 0).toLocaleString('pt-BR');
const brl = (v) => 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 });
const pct = (a, b) => (b ? Math.round((100 * a) / b) + '%' : '—');
const dataBR = (iso) => { const [y, m, d] = String(iso).split('-'); return `${d}/${m}`; };
const tempo = (s) => (s == null ? '—' : s < 60 ? `${s}s` : `${Math.round(s / 60)} min`);
const CANAL = { google: 'Google', meta: 'Meta (anúncios)', organico: 'Direto / orgânico', site: 'Site', indicacao: 'Indicação', retorno: 'Cliente que voltou' };

// ---------- barras horizontais (uma cor; o rótulo identifica) ----------
function barras(linhas, opt = {}) {
  const max = Math.max(1, ...linhas.map((l) => l.v));
  if (!linhas.length) return `<p class="vazio">Sem dados no período.</p>`;
  return `<div class="bars${opt.cls ? ' ' + opt.cls : ''}">` + linhas.map((l) => `
    <div class="bar" data-tip="${esc(l.tip || `${l.nome}: ${n(l.v)}`)}">
      <span class="name">${esc(l.nome)}</span><span class="num">${n(l.v)}${l.extra ? ` <em>${esc(l.extra)}</em>` : ''}</span>
      <span class="track"><span class="fill" style="width:${Math.max(l.v ? 2 : 0, (100 * l.v) / max)}%"></span></span>
    </div>`).join('') + `</div>`;
}

// ---------- funil ----------
const funil = (p.funil || []).map(([nome, v]) => ({ nome, v }));
const topo = funil[0]?.v || 0;
const funilHtml = barras(funil.map((l) => ({ ...l, extra: topo ? pct(l.v, topo) : '', tip: `${l.nome}: ${n(l.v)} (${pct(l.v, topo)} das conversas)` })), { cls: 'funil' });

// ---------- por dia: colunas agrupadas (conversas x visitas), um eixo só ----------
function porDia() {
  const mapa = Object.fromEntries((p.diario || []).map(([d, c, ag]) => [d, { c, ag }]));
  const dias = [];
  for (let i = f.dias - 1; i >= 0; i--) {
    const d = $now.setZone('America/Sao_Paulo').minus({ days: i }).toISODate();
    dias.push({ d, c: mapa[d]?.c || 0, ag: mapa[d]?.ag || 0 });
  }
  const W = 760, H = 220, padL = 28, padR = 18, padB = 26, padT = 10;
  const max = Math.max(1, ...dias.map((x) => x.c));
  const passo = Math.ceil(max / 4) || 1, topoY = passo * 4;
  const largura = (W - padL - padR) / dias.length;
  const bw = Math.max(1.5, Math.min(14, largura / 2 - 2));
  const y = (v) => padT + (H - padT - padB) * (1 - v / topoY);
  let s = `<div class="rolagem"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Conversas e visitas combinadas por dia">`;
  for (let g = 0; g <= 4; g++) {
    const v = g * passo;
    s += `<line x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}" class="${g ? 'grid' : 'base'}"/><text x="${padL - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
  }
  const cadaRotulo = Math.ceil(dias.length / 10);
  dias.forEach((x, i) => {
    const cx = padL + largura * i + largura / 2;
    const tip = `${dataBR(x.d)} · ${n(x.c)} conversas · ${n(x.ag)} visitas combinadas`;
    s += `<g data-tip="${esc(tip)}"><rect x="${cx - largura / 2}" y="${padT}" width="${largura}" height="${H - padT - padB}" class="hit"/>`;
    if (x.c) s += `<rect x="${cx - bw - 1}" y="${y(x.c)}" width="${bw}" height="${y(0) - y(x.c)}" rx="${Math.min(4, bw / 2)}" class="s1"/>`;
    if (x.ag) s += `<rect x="${cx + 1}" y="${y(x.ag)}" width="${bw}" height="${y(0) - y(x.ag)}" rx="${Math.min(4, bw / 2)}" class="s2"/>`;
    s += `</g>`;
    if (i % cadaRotulo === 0 || i === dias.length - 1) s += `<text x="${cx}" y="${H - 8}" text-anchor="middle">${dataBR(x.d)}</text>`;
  });
  s += `</svg></div>`;
  const tabela = `<details><summary>Ver em tabela</summary><table><thead><tr><th>Dia</th><th>Conversas</th><th>Visitas</th></tr></thead><tbody>${
    dias.filter((x) => x.c).map((x) => `<tr><td>${dataBR(x.d)}</td><td>${x.c}</td><td>${x.ag}</td></tr>`).join('') || '<tr><td colspan="3">Sem conversas</td></tr>'}</tbody></table></details>`;
  return s + tabela;
}

// ---------- mapa de calor dia x hora (azul sequencial) ----------
function calor() {
  const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
  const H0 = 7, H1 = 22;
  const m = {};
  (p.heatmap || []).forEach(([dow, h, v]) => { m[`${dow}-${h}`] = v; });
  const max = Math.max(0, ...Object.values(m));
  const passo = (v) => (!v ? 0 : Math.min(6, 1 + Math.floor((5 * (v - 1)) / Math.max(1, max - 1))));
  let s = `<div class="heat" style="grid-template-columns: 34px repeat(${H1 - H0 + 1}, minmax(0, 1fr))"><span></span>`;
  for (let h = H0; h <= H1; h++) s += `<span class="hh">${h % 3 === 0 ? h + 'h' : ''}</span>`;
  DIAS.forEach((nome, i) => {
    s += `<span class="hd">${nome}</span>`;
    for (let h = H0; h <= H1; h++) {
      const v = m[`${i + 1}-${h}`] || 0;
      s += `<span class="cell q${passo(v)}" data-tip="${nome} ${h}h: ${v} ${v === 1 ? 'conversa' : 'conversas'}"></span>`;
    }
  });
  return s + `</div><div class="heat-legend"><span>menos</span>${[1, 2, 3, 4, 5, 6].map((q) => `<i class="cell q${q}"></i>`).join('')}<span>mais</span></div>`;
}

// ---------- blocos ----------
const canais = (p.canais || []).map(([c, v, ag]) => ({ nome: CANAL[c] || c, v, extra: `${n(ag)} visitas`, tip: `${CANAL[c] || c}: ${n(v)} conversas, ${n(ag)} visitas (${pct(ag, v)})` }));
const equipamentos = (p.equipamentos || []).map(([nome, v, ag]) => ({ nome, v, extra: `${n(ag)} visitas` }));
const servicos = (p.servicos || []).map(([nome, v, fe]) => ({ nome, v, extra: fe ? `${n(fe)} fechados` : '' }));
const modelos = (p.modelos || []).map(([nome, v]) => ({ nome, v }));
const par = p.parados || {};

const kpi = (lbl, val, note, hl) => `<div class="kpi${hl ? ' hl' : ''}"><span class="lbl">${lbl}</span><span class="val">${val}</span>${note ? `<span class="note">${note}</span>` : ''}</div>`;
const link = (d) => `<a href="?t=${encodeURIComponent(f.token)}&dias=${d}${f.teste ? '&teste=1' : ''}" class="${d === f.dias ? 'on' : ''}">${d} dias</a>`;

const vazio = !k.leads;
const corpo = vazio ? `<div class="card"><h2>Ainda não há conversas neste período</h2><p class="desc">Assim que a Sofia começar a atender, os números aparecem aqui automaticamente.</p></div>` : `
<section class="kpis">
  ${kpi('Conversas', n(k.leads), `${n(k.fora_horario)} chegaram com a loja fechada`)}
  ${kpi('Orçamentos enviados', n(k.orcamentos), `${pct(k.orcamentos, k.leads)} das conversas`)}
  ${kpi('Visitas combinadas', n(k.agendados), `${k.conversao_agendamento ?? 0}% das conversas`, true)}
  ${kpi('Serviços fechados', n(k.fechados), k.fechados ? `${brl(k.receita)} · ticket médio ${brl(k.ticket_medio)}` : 'lançados pela equipe na loja')}
</section>
<section class="mini">
  <div><span>Primeira resposta</span><b>${tempo(k.tempo_primeira_resposta_s)}</b></div>
  <div><span>Até combinar a visita</span><b>${k.horas_ate_agendar != null ? String(k.horas_ate_agendar).replace('.', ',') + ' h' : '—'}</b></div>
  <div><span>Recuperados no follow-up</span><b>${n(k.recuperados_followup)}</b></div>
  <div><span>Custo da IA no período</span><b>US$ ${Number(k.custo_ia_usd || 0).toFixed(2).replace('.', ',')}</b></div>
</section>
${par.orcamento_sem_agendar ? `<div class="flag" role="status"><b>⚠ Atenção:</b> ${n(par.orcamento_sem_agendar)} ${par.orcamento_sem_agendar === 1 ? 'cliente recebeu' : 'clientes receberam'} orçamento e ainda não combinou a visita.</div>` : ''}
<section class="grid2">
  <div class="card"><div class="head"><h2>Funil do atendimento</h2></div><p class="desc">Quantas conversas chegaram em cada etapa, da primeira mensagem ao serviço fechado.</p>${funilHtml}</div>
  <div class="card"><div class="head"><h2>De onde vêm os clientes</h2></div><p class="desc">Conversas por origem e quantas viraram visita.</p>${barras(canais)}</div>
</section>
<section class="card">
  <div class="head"><h2>Conversas por dia</h2><div class="legend"><span><i class="s1"></i>Conversas</span><span><i class="s2"></i>Visitas combinadas</span></div></div>
  ${porDia()}
</section>
<section class="grid2">
  <div class="card"><h2>Serviços mais procurados</h2>${barras(servicos)}</div>
  <div class="card"><h2>Aparelhos</h2>${barras(equipamentos)}<h3>Modelos mais citados</h3>${barras(modelos)}</div>
</section>
<section class="card"><div class="head"><h2>Quando os clientes chamam</h2></div><p class="desc">Conversas por dia da semana e hora. A Sofia atende também fora do horário da loja.</p>${calor()}</section>`;

const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel Senhor Smart</title><meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{--bg:#f4f6f8;--surface:#fff;--line:#dde3ea;--grid:#e9edf2;--base:#c3c2b7;--ink:#0f1b2a;--ink-2:#4a5768;--ink-3:#6b7685;--brand:#0e5c4a;--brand-soft:#e3f1ec;--s1:#2a78d6;--s2:#eb6834;
--q1:#cde2fb;--q2:#9ec5f4;--q3:#6da7ec;--q4:#3987e5;--q5:#256abf;--q6:#104281;--warn-bg:#fff4dc;--warn-ink:#7a4b00;
--f-d:"Bricolage Grotesque","Segoe UI",system-ui,sans-serif;--f-b:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d1218;--surface:#151c24;--line:#263140;--grid:#1e2833;--base:#383835;--ink:#eef2f6;--ink-2:#b4bfcc;--ink-3:#8f9bab;--brand:#4fc3a1;--brand-soft:#16302a;--s1:#3987e5;--s2:#d95926;
--q1:#184f95;--q2:#1c5cab;--q3:#256abf;--q4:#3987e5;--q5:#6da7ec;--q6:#b7d3f6;--warn-bg:#3a2c0c;--warn-ink:#f5cf7a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0d1218;--surface:#151c24;--line:#263140;--grid:#1e2833;--base:#383835;--ink:#eef2f6;--ink-2:#b4bfcc;--ink-3:#8f9bab;--brand:#4fc3a1;--brand-soft:#16302a;--s1:#3987e5;--s2:#d95926;
--q1:#184f95;--q2:#1c5cab;--q3:#256abf;--q4:#3987e5;--q5:#6da7ec;--q6:#b7d3f6;--warn-bg:#3a2c0c;--warn-ink:#f5cf7a;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f-b);font-size:15px;line-height:1.5}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 48px;display:grid;gap:16px}
header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px}
.brand{display:flex;align-items:center;gap:12px}.mark{width:42px;height:42px;border-radius:11px;background:var(--brand);color:var(--surface);display:grid;place-items:center;font-family:var(--f-d);font-weight:700}
h1{font-family:var(--f-d);font-size:24px;margin:0;line-height:1.15}.sub{margin:0;color:var(--ink-2);font-size:13.5px}
.periodo{display:flex;gap:6px;flex-wrap:wrap}.periodo a{color:var(--ink-2);text-decoration:none;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:6px 12px;font-size:13px}
.periodo a.on{border-color:var(--brand);color:var(--brand);font-weight:600}.teste{align-self:center;font-size:12px;background:var(--warn-bg);color:var(--warn-ink);border-radius:999px;padding:3px 10px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;display:grid;gap:4px;align-content:start}
.kpi .lbl{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3);font-weight:600}
.kpi .val{font-family:var(--f-d);font-size:36px;font-weight:700;line-height:1.05}.kpi .note{font-size:13px;color:var(--ink-2)}
.kpi.hl{border-color:var(--brand);background:var(--brand-soft)}
.mini{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.mini div{display:flex;justify-content:space-between;gap:8px;align-items:baseline;border-bottom:1px solid var(--line);padding:6px 2px;font-size:13.5px;color:var(--ink-2)}
.mini b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 20px;display:grid;gap:12px;min-width:0;align-content:start}
.card h2{font-family:var(--f-d);font-size:18px;margin:0}.card h3{font-size:14px;margin:6px 0 0;color:var(--ink-2)}.desc{margin:0;color:var(--ink-2);font-size:13.5px}
.head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 16px;align-items:center}
.legend{display:flex;gap:14px;font-size:13px;color:var(--ink-2)}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.legend i.s1{background:var(--s1)}.legend i.s2{background:var(--s2)}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.bars{display:grid;gap:10px}.bar{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;font-size:13.5px}
.bar .name{min-width:0;overflow-wrap:anywhere}.bar .num{color:var(--ink);font-variant-numeric:tabular-nums;font-weight:600}.bar .num em{font-style:normal;font-weight:400;color:var(--ink-2);margin-left:6px}
.bar .track{grid-column:1/-1;height:8px;background:var(--grid);border-radius:4px;overflow:hidden}.bar .fill{display:block;height:100%;border-radius:0 4px 4px 0;background:var(--s1)}
.funil .fill{background:var(--brand)}
.rolagem{overflow-x:auto}.chart{width:100%;min-width:560px;height:auto;display:block}.chart text{font-family:var(--f-b);fill:var(--ink-3);font-size:11px}
.chart .grid{stroke:var(--grid);stroke-width:1}.chart .base{stroke:var(--base);stroke-width:1}.chart .s1{fill:var(--s1)}.chart .s2{fill:var(--s2)}.chart .hit{fill:transparent}
.chart g:hover .s1,.chart g:hover .s2{opacity:.85}
.heat{display:grid;gap:3px;font-size:11px;color:var(--ink-3)}.heat .hh{text-align:left}.heat .hd{align-self:center}
.cell{display:block;aspect-ratio:1.6;border-radius:3px;background:var(--grid)}.q1{background:var(--q1)}.q2{background:var(--q2)}.q3{background:var(--q3)}.q4{background:var(--q4)}.q5{background:var(--q5)}.q6{background:var(--q6)}
.heat-legend{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--ink-3)}.heat-legend i{width:18px;aspect-ratio:1.6}
.flag{background:var(--warn-bg);color:var(--warn-ink);border-radius:10px;padding:10px 14px;font-size:14px}
.vazio{color:var(--ink-3);font-size:13.5px;margin:0}
details{font-size:13px;color:var(--ink-2)}summary{cursor:pointer}table{border-collapse:collapse;margin-top:8px;font-variant-numeric:tabular-nums}td,th{padding:4px 12px 4px 0;text-align:left;border-bottom:1px solid var(--line)}
.tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);font-size:12.5px;padding:7px 10px;border-radius:8px;z-index:9;max-width:260px;opacity:0;transition:opacity .08s}
footer{color:var(--ink-3);font-size:12.5px;text-align:center}
@media (max-width:860px){.kpis,.mini{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:1fr}.kpi .val{font-size:30px}}
@media (max-width:520px){.mini{grid-template-columns:1fr}.kpi{padding:12px 14px}.kpi .val{font-size:26px}.card{padding:14px}.heat{gap:2px}.heat .hh{font-size:9px}h1{font-size:20px}}
</style></head><body><div class="wrap">
<header><div class="brand"><div class="mark">SS</div><div><h1>Senhor Smart · Atendimento</h1><p class="sub">Sofia, assistente de IA no WhatsApp · ${dataBR(f.inicio)} a ${dataBR(f.fim)}</p></div></div>
<nav class="periodo" aria-label="Período">${f.teste ? '<span class="teste">inclui conversas de teste</span>' : ''}${[7, 30, 90].map(link).join('')}</nav></header>
${corpo}
<footer>Atualizado em ${esc(f.agora)} · números ao vivo do atendimento</footer>
</div><div class="tip" id="tip" role="tooltip"></div>
<script>(()=>{const t=document.getElementById('tip');document.addEventListener('pointermove',e=>{const el=e.target.closest('[data-tip]');if(!el){t.style.opacity=0;return}t.textContent=el.dataset.tip;const x=Math.min(e.clientX+14,innerWidth-t.offsetWidth-8),y=Math.min(e.clientY+14,innerHeight-t.offsetHeight-8);t.style.left=x+'px';t.style.top=y+'px';t.style.opacity=1});document.addEventListener('pointerleave',()=>t.style.opacity=0)})();</script>
</body></html>`;

return [{ json: { html } }];
