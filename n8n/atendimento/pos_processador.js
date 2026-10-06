// n8n Code node: "Pós-processador"
// Só mecânica: separa as bolhas (|||), limpa markdown e barra vazamento de campo interno.
// Transferência e fila vêm da máquina (conducao), nunca do texto.

const conducao = $('Máquina de Estado').first().json.conducao || {};
const filas = ($('Carregar Contexto').first().json.contexto || {}).filas || {};

let texto = '';
try { const a = $('Sofia').first().json; texto = String(a.output || a.text || '').trim(); } catch (_) {}

let precisa_transferir = !!conducao.deve_transferir;
let queueId = conducao.transferir_para || null;

// nomes de campo da conducao que nunca podem aparecer para o cliente
const VAZAMENTO = [
  /contexto recebido/i, /\bconducao\b/i, /\b[a-z]+_[a-z_]+\b/, /[{}\[\]]/,
];

const limpo = texto
  .replace(/\*\*|__/g, '')
  .replace(/^#+\s*/gm, '')
  .replace(/^\s*[-•]\s+/gm, '')
  .trim();

let segmentos = limpo.split(/\n?\|\|\|\n?/).map((s) => s.trim()).filter(Boolean);
if (segmentos.length > 3) segmentos = [...segmentos.slice(0, 2), segmentos.slice(2).join('\n')];

const vazou = segmentos.some((s) => VAZAMENTO.some((re) => re.test(s)));
let fallback = null;
if (!segmentos.length || vazou) {
  // resposta vazia ou com campo interno: não envia o texto e passa para a equipe
  fallback = vazou ? 'vazamento' : 'resposta_vazia';
  segmentos = ['Só um instante, vou pedir para alguém da equipe continuar com você por aqui.'];
  precisa_transferir = true;
  queueId = queueId || filas.humano || null;
}

return segmentos.map((s, i) => ({
  json: {
    resposta_final: s,
    precisa_transferir,
    queueId,
    _fallback: fallback,
    _segmento: i + 1,
    _total_segmentos: segmentos.length,
  },
}));
