// n8n Code node: "Montar Log do Turno"
// Junta o que a máquina decidiu (metricas) com os dados do turno para o v1_registrar_turno.
// Não decide nada: só monta o payload. O SQL só grava.

const maquina = $('Máquina de Estado').first().json;
const wb = $('Webhook').first().json.body || {};

let saida = '';
try { const a = $('Sofia').first().json; saida = String(a.output || a.text || '').trim(); } catch (_) {}

let entrada = '';
try { entrada = String($('Mensagem').first().json.messagem || ''); } catch (_) {}

// lastMessageDate pode vir em ISO, epoch em segundos ou em milissegundos
let latencia_ms = null;
const bruto = wb.lastMessageDate;
let t0 = typeof bruto === 'number' ? bruto : (/^\d+$/.test(String(bruto || '')) ? Number(bruto) : Date.parse(bruto));
if (t0 && t0 < 1e12) t0 *= 1000;
if (t0) {
  const d = Date.now() - t0;
  if (d >= 0 && d < 2147483647) latencia_ms = Math.round(d);
}

let usage = {};
try { usage = $('Extrair Intenção').first().json.usage || {}; } catch (_) {}

return [{
  json: {
    payload: {
      metricas: maquina.metricas,
      telefone: wb.contact?.number || null,
      nome_whatsapp: wb.contact?.name || null,
      agora: $now.setZone('America/Sao_Paulo').toISO(),
      turno: {
        entrada,
        saida,
        latencia_ms,
        modelo_ia: 'extrator gpt-5.4-mini + narrador gpt-4.1-mini',
        tokens: usage.total_tokens ?? null,   // só extrator; o nó da Sofia não expõe o uso
        custo_usd: usage.cost ?? null,
      },
    },
  },
}];
