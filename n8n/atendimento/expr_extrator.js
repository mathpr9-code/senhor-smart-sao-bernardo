(() => {
  const ec = $('Carregar Estado + Catálogo').first().json;
  const cat = ec.catalogo || {};
  const est = ec.estado || {};
  const S = __SCHEMA__;
  const it = S.schema.properties.equipamentos.items.properties;
  it.categoria.enum = [...(cat.categorias || []), null];
  it.servico_sugerido.enum = [...(cat.servicos || []), null];
  S.schema.properties.objecao.enum = [...(cat.objecoes || []), null];
  const eqs = (est.trabalhos || []).filter((t) => t.status !== 'fora')
    .map((t) => [t.categoria || 'aparelho', t.marca, t.modelo].filter(Boolean).join(' ') + ', defeito: ' + (t.defeito || 'não informado'));
  const user = '<estado_resumo>\nequipamentos já falados: ' + (eqs.join('; ') || 'nenhum') +
    '\núltima pergunta da atendente: ' + (est.ultima_pergunta || 'nenhuma') +
    '\n</estado_resumo>\n<mensagem_cliente>\n' + $('Mensagem').first().json.messagem + '\n</mensagem_cliente>';
  return JSON.stringify({
    model: 'openai/gpt-5.4-mini',
    reasoning_effort: 'none',
    max_tokens: 700,
    usage: { include: true },
    response_format: { type: 'json_schema', json_schema: S },
    messages: [
      { role: 'system', content: __SYSTEM__ + '\n\n<catalogo>\n' + (cat.catalogo_texto || '') + '\n</catalogo>' },
      { role: 'user', content: user },
    ],
  });
})()
