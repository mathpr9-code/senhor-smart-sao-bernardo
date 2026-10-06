// n8n Code node: "Montar Nota Interna"
// Nota para a equipe após a transferência. Fonte única: conducao.resumo_encaminhamento da máquina.
// Determinístico, sem IA, sem inventar: campo vazio vira "não informado".

const conducao = $('Máquina de Estado').first().json.conducao || {};
const r = conducao.resumo_encaminhamento || {};
const pp = $('Pós-processador').first().json;

const CANAL = { google: 'Google', meta: 'Meta (anúncio)', organico: 'Direto / orgânico', site: 'Site',
  indicacao: 'Indicação', retorno: 'Cliente que voltou' };
const MOTIVO = {
  visita_combinada: 'Cliente combinou de ir à loja',
  pediu_humano: 'Cliente pediu para falar com uma pessoa',
  comprar_aparelho: 'Cliente quer comprar aparelho',
  reclamacao: 'Reclamação sobre serviço',
  status_servico: 'Pergunta sobre aparelho que já está na loja',
};
const brl = (v) => (v == null ? null : 'R$ ' + Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 }));
const ou = (v) => (v == null || v === '' ? 'não informado' : v);

const linhas = ['🤖 Resumo da Sofia (IA)'];
linhas.push(`Motivo: ${MOTIVO[r.motivo] || (pp._fallback ? 'A IA não conseguiu responder e passou para a equipe' : ou(r.motivo))}`);
linhas.push(`Cliente: ${ou(r.cliente)}`);
if (r.origem) linhas.push(`Origem: ${CANAL[r.origem.canal] || ou(r.origem.canal)}${r.origem.campanha ? ` · ${r.origem.campanha}` : ''}`);
for (const [i, e] of (r.equipamentos || []).entries()) {
  const partes = [ou(e.equipamento), e.modelo, e.defeito ? `defeito: ${e.defeito}` : null,
    e.servico ? `serviço: ${e.servico}` : null, e.preco != null ? `valor passado: ${brl(e.preco)}` : null];
  linhas.push(`Aparelho ${i + 1}: ${partes.filter(Boolean).join(' · ')}`);
}
if (r.impacto) linhas.push(`O que pesa para o cliente: ${r.impacto}`);
if (r.visita) linhas.push(`Visita: ${ou(r.visita.quando)}`);

return [{ json: { nota_interna: linhas.join('\n') } }];
