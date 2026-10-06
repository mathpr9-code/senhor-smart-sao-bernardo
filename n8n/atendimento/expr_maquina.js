JSON.stringify({
  ticket_id: Number($('Webhook').first().json.body.ticketId),
  estado: $('Carregar Estado + Catálogo').first().json.estado || null,
  leitura: (() => { try { return JSON.parse($('Extrair Intenção').first().json.choices[0].message.content); } catch (e) { return { intencao: 'outro', equipamentos: [], perguntas: [] }; } })(),
  foto: null,
  contexto_dados: $('Carregar Contexto').first().json.contexto,
  agora: $now.setZone('America/Sao_Paulo').toISO(),
  nome_whatsapp: $('Webhook').first().json.body.contact?.name || null,
  mensagem_texto: String($('Webhook').first().json.body.lastMessage ?? ''),
  mensagem_data: String($('Webhook').first().json.body.lastMessageDate ?? ''),
  anuncio: $('Filtra webhook').first().json.vemDeAnuncio ? ($('Webhook').first().json.body.title || 'Anúncio Meta') : null,
  primeira_mensagem: $('Mensagem').first().json.messagem
})
