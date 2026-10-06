// n8n Code node: "Interpretar Foto"
// Lê o JSON do "Ler Foto" (visão) e monta o texto curto que entra no buffer como [FOTO_DO_CLIENTE: ...].
// O extrator lê esse texto junto com a legenda. Quando esta execução é a vencedora do buffer,
// a Máquina de Estado também recebe os campos estruturados (foto), só se tipo = aparelho.

const item = $input.first().json;
const raw = String(item?.choices?.[0]?.message?.content || '')
  .replace(/^```(?:json)?\s*/i, '')
  .replace(/\s*```\s*$/, '')
  .trim();

let f = { tipo: 'outro', categoria: null, marca: null, modelo: null, danos: [], descricao: '', confianca: 'baixa' };
try { f = { ...f, ...JSON.parse(raw) }; } catch (_) { f.descricao = raw; }

let texto;
if (f.tipo === 'aparelho') {
  const aparelho = [f.categoria, f.marca, f.modelo].filter(Boolean).join(' ') || 'aparelho';
  const danos = (f.danos || []).length ? `; danos visíveis: ${f.danos.join(', ')}` : '';
  texto = `${aparelho}${danos}. ${f.descricao || ''}`;
} else if (f.tipo === 'documento') {
  texto = 'documento, não é foto de aparelho';
} else {
  texto = f.descricao || 'imagem sem aparelho';
}

return [{ json: { ...f, descricao_texto: texto.trim(), usage: item.usage || null } }];
