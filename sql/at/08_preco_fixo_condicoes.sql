-- 06/10 (Matheus): preço fixo por serviço (teste: maior valor da faixa), condição entrada + parcelas,
-- avaliação sem custo e aprovação antes do conserto confirmadas, fila da base de teste DeskRio.
alter table senhor_smart_at.preco_referencia add column if not exists preco numeric(10,2);
update senhor_smart_at.preco_referencia set preco = preco_max where preco is null;

update senhor_smart_at.loja_info set confirmado = true, valor = 'avaliação na loja sem custo, dentro do horário de funcionamento'
 where chave = 'avaliacao_sem_custo';
update senhor_smart_at.loja_info set confirmado = true where chave = 'aprovacao_antes_do_conserto';
insert into senhor_smart_at.loja_info (chave, valor, confirmado) values
  ('condicao_entrada', '240', true), ('condicao_parcelas_max', '18', true), ('condicao_meio', 'boleto', true)
on conflict (chave) do update set valor = excluded.valor, confirmado = true;
update senhor_smart_at.loja_info set valor = '64000523' where chave in ('fila_tecnico', 'fila_vendas', 'fila_humano');

update senhor_smart_at.objecoes set argumentos = v.a from (values
 ('preco_alto', '{condicao_pagamento,garantia_servico,avaliacao_sem_custo,aprovacao_antes_do_conserto,faixa_inclui_peca_e_mao_de_obra}'::text[]),
 ('comparou_concorrente', '{garantia_servico,aprovacao_antes_do_conserto,condicao_pagamento,referencia_local}'),
 ('vou_pesquisar', '{avaliacao_sem_custo,condicao_pagamento,horario_texto}'),
 ('desconfianca', '{aprovacao_antes_do_conserto,avaliacao_sem_custo,garantia_servico,conserto_na_frente,referencia_local}'),
 ('nao_vale_a_pena', '{condicao_pagamento,dados_preservados,venda_aparelhos,venda_sem_consulta_spc}')
) v(c, a) where objecoes.codigo = v.c;
-- v1_carregar_contexto: 'precos' passa a incluir a chave 'preco' (aplicado por replace da definição).
