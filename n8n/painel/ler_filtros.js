// n8n Code node: "Ler filtros"
// Link: /webhook/painel-senhor-smart?t=<TOKEN>&dias=30   (dias: 7, 30 ou 90; teste=1 inclui as conversas de teste)
// O token é a única proteção do link: quem tem o link vê os números agregados (sem nome, telefone ou conversa).
const TOKEN = '__TOKEN__';
const q = $('Webhook').first().json.query || {};
const ok = q.t === TOKEN;
const dias = [7, 30, 90].includes(Number(q.dias)) ? Number(q.dias) : 30;
const hoje = $now.setZone('America/Sao_Paulo');
return [{ json: {
  ok,
  dias,
  teste: q.teste === '1',
  inicio: hoje.minus({ days: dias - 1 }).toISODate(),
  fim: hoje.toISODate(),
  agora: hoje.toFormat('dd/MM HH:mm'),
  token: TOKEN,
} }];
