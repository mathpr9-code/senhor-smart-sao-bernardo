// n8n Code node: "Config"
// Para quem vai o resumo do dia e por qual conexão do WhatsApp (DeskRio) ele sai.
// connectionId: o mesmo que chega no webhook do atendimento (body.connectionId) da Senhor Smart.
const DESTINO = 'PREENCHER_NUMERO';        // ex.: 5511999999999 (DDI + DDD + número)
const CONEXAO = 'PREENCHER_CONNECTION_ID';  // ex.: 64000123
if (DESTINO.startsWith('PREENCHER') || CONEXAO.startsWith('PREENCHER')) {
  throw new Error('Preencha DESTINO e CONEXAO no nó Config antes de ativar o resumo.');
}
// "Testar agora" inclui as conversas de teste (ticket negativo); o agendado só conta cliente real.
let teste = false;
try { teste = $('Testar agora').isExecuted; } catch (_) {}
return [{ json: { destino: DESTINO, conexao: Number(CONEXAO), incluir_teste: teste } }];
