// n8n Code node: "Montar resumo do dia"
// Fluxo: Schedule (seg a sáb, 19:05) -> Postgres "SELECT senhor_smart_at.v1_resumo_dia() AS r" -> este node -> envio WhatsApp ao dono.
// Determinístico: só números do banco, sem LLM. Nada de valor inventado.

const r = $input.first().json.r;
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');
const brl = (n) => 'R$ ' + Number(n || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 });
const pct = (a, b) => (b ? Math.round((100 * a) / b) + '%' : '—');
const dia = new Date(r.dia + 'T12:00:00').toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: '2-digit' });

const canais = Object.entries(r.por_canal || {})
  .sort((a, b) => b[1] - a[1])
  .map(([c, n]) => `${{ google: 'Google', meta: 'Meta', organico: 'Direto', site: 'Site', indicacao: 'Indicação', retorno: 'Retorno' }[c] || c} ${n}`)
  .join(' · ');

const servicos = (r.top_servicos || []).map(([nome, n]) => `${nome} (${n})`).join(', ');

const media = r.media_7_dias || {};
const comparacao = media.leads
  ? `\nMédia dos últimos 7 dias: ${fmt(media.leads)} conversas e ${fmt(media.agendados)} visitas por dia.`
  : '';

const tempo = r.tempo_primeira_resposta_s != null
  ? (r.tempo_primeira_resposta_s < 60 ? `${r.tempo_primeira_resposta_s}s` : `${Math.round(r.tempo_primeira_resposta_s / 60)} min`)
  : '—';

const linhas = [
  `*Resumo do dia — Senhor Smart*`,
  `${dia.charAt(0).toUpperCase() + dia.slice(1)}`,
  ``,
  `📲 ${fmt(r.leads)} conversas novas${canais ? ` (${canais})` : ''}`,
  `🌙 ${fmt(r.fora_do_horario)} chegaram com a loja fechada e foram atendidas`,
  `💬 ${fmt(r.orcamentos)} receberam orçamento ou orientação`,
  `📍 ${fmt(r.agendados)} combinaram de ir à loja (${pct(r.agendados, r.leads)} das conversas)`,
  r.visitas_combinadas_para_amanha ? `🗓️ ${fmt(r.visitas_combinadas_para_amanha)} ${r.visitas_combinadas_para_amanha === 1 ? 'disse que vai' : 'disseram que vão'} amanhã` : null,
  r.fechados_hoje ? `✅ ${fmt(r.fechados_hoje)} ${r.fechados_hoje === 1 ? 'serviço fechado' : 'serviços fechados'} hoje · ${brl(r.receita_hoje)}` : null,
  `⏱️ Primeira resposta em ${tempo}`,
  servicos ? `\nMais procurados: ${servicos}` : null,
  r.parados_com_orcamento ? `\n⚠️ ${fmt(r.parados_com_orcamento)} ${r.parados_com_orcamento === 1 ? 'cliente recebeu orçamento e ainda não respondeu' : 'clientes receberam orçamento e ainda não responderam'}.` : null,
  comparacao || null,
].filter((l) => l !== null);

return [{ json: { texto: linhas.join('\n') } }];
