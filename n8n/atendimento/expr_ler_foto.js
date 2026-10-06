(() => {
  const S = __SCHEMA__;
  const l = $('Webhook').first().json.body?.lastMediaMessage || '';
  const legenda = (typeof l === 'string' && !l.startsWith('http')) ? l.trim() : '';
  return JSON.stringify({
    model: 'openai/gpt-5.4-mini',
    reasoning_effort: 'none',
    max_tokens: 400,
    usage: { include: true },
    response_format: { type: 'json_schema', json_schema: S },
    messages: [
      { role: 'system', content: __SYSTEM__ },
      { role: 'user', content: [
        { type: 'text', text: 'Legenda do cliente: ' + (legenda || 'sem legenda') },
        { type: 'image_url', image_url: { url: $json.imageUrl } },
      ] },
    ],
  });
})()
