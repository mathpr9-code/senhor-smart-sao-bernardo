(() => {
  const c = $('Máquina de Estado').first().json.conducao || {};
  const INTERNAS = ['duplicata', 'etapa', 'fila', 'transferir_para', 'motivo_transferencia', 'resumo_encaminhamento'];
  const limpar = (v) => {
    if (Array.isArray(v)) { const a = v.map(limpar).filter((x) => x !== undefined); return a.length ? a : undefined; }
    if (v && typeof v === 'object') {
      const o = {};
      for (const [k, x] of Object.entries(v)) { const y = limpar(x); if (y !== undefined) o[k] = y; }
      return Object.keys(o).length ? o : undefined;
    }
    if (v === null || v === undefined || v === false || v === '') return undefined;
    return v;
  };
  const base = {};
  for (const [k, v] of Object.entries(c)) if (!INTERNAS.includes(k)) base[k] = v;
  return 'Contexto recebido:\n' + JSON.stringify(limpar(base) || {}) + '\n\nMensagem do cliente:\n' + $('Mensagem').first().json.messagem;
})()
