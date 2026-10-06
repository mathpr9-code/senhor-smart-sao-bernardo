// n8n Code node: "Config"
// Para quem vai o resumo do dia e por qual conexão do WhatsApp (DeskRio) ele sai.
// connectionId: o mesmo que chega no webhook do atendimento (body.connectionId) da Senhor Smart.
const DESTINO = 'PREENCHER_NUMERO';        // ex.: 5511999999999 (DDI + DDD + número)
const CONEXAO = 'PREENCHER_CONNECTION_ID';  // ex.: 64000123
// true = soma as conversas de teste (ticket negativo). Em produção, deixar false.
const INCLUIR_TESTE = false;
if (DESTINO.startsWith('PREENCHER') || CONEXAO.startsWith('PREENCHER')) {
  throw new Error('Preencha DESTINO e CONEXAO no nó Config antes de ativar o resumo.');
}
// "Testar agora" também inclui as conversas de teste.
let manual = false;
try { manual = $('Testar agora').isExecuted; } catch (_) {}
return [{ json: { destino: DESTINO, conexao: Number(CONEXAO), incluir_teste: INCLUIR_TESTE || manual } }];
