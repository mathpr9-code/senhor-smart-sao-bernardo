-- v1.1: objeções como DADO (sem frase pronta) e detalhes técnicos estruturados por serviço.
-- O narrador (GPT-4.1-mini, literal) recebe orientação e dado; ele escreve com as próprias palavras.

-- 1. Detalhes técnicos estruturados (substituem a frase em servicos.observacao para o narrador)
alter table senhor_smart_at.servicos add column if not exists detalhes jsonb not null default '{}';
update senhor_smart_at.servicos set detalhes = d.j from (values
  ('cel_tela',     '{"pode_ser": ["tela", "placa"], "confirmado_na": "avaliacao"}'::jsonb),
  ('cel_conector', '{"alternativa_simples": "limpeza do conector", "pode_ser": ["sujeira no conector", "conector danificado"]}'),
  ('cel_agua',     '{"cuidados": ["manter desligado", "nao colocar para carregar", "nao usar arroz"], "urgencia": "quanto antes melhor"}'),
  ('cel_placa',    '{"pode_ser": ["placa", "bateria", "conector"], "confirmado_na": "avaliacao"}'),
  ('cel_software', '{"cuidados": ["backup antes, quando possivel"]}'),
  ('nb_ssd',       '{"inclui": ["SSD de 240GB a 480GB", "transferencia do sistema e arquivos"], "beneficio": "liga e abre programas bem mais rapido"}'),
  ('nb_placa',     '{"cuidados": ["manter desligado", "nao ligar na tomada"], "confirmado_na": "avaliacao"}'),
  ('vg_hdmi',      '{"pode_ser": ["porta HDMI", "cabo", "chip de video"], "confirmado_na": "avaliacao"}'),
  ('vg_limpeza',   '{"beneficio": "menos barulho e menos aquecimento"}')
) as d(id, j) where servicos.id = d.id;

-- 2. Fatos que servem de argumento. confirmado=false: a IA NUNCA afirma até o dono confirmar.
insert into senhor_smart_at.loja_info (chave, valor, confirmado) values
  ('avaliacao_sem_custo', 'avaliação na loja sem custo', false),
  ('aprovacao_antes_do_conserto', 'o cliente aprova o valor antes de qualquer conserto', false),
  ('dados_preservados', 'troca de tela, bateria e conector não apagam fotos nem conversas', false),
  ('conserto_na_frente', 'dá para acompanhar o conserto rápido na loja', false),
  ('venda_sem_consulta_spc', 'na compra de aparelho no boleto, a análise é na hora e sem consulta a SPC ou Serasa', true),
  ('referencia_local', 'a loja fica dentro do Posto Shell da Av. João Firmino, fácil de achar e de estacionar', true)
on conflict (chave) do nothing;

-- 3. Biblioteca de objeções da assistência técnica (dado + orientação, nunca resposta pronta)
create table if not exists senhor_smart_at.objecoes (
  codigo text primary key,
  nome text not null,
  por_tras text[] not null,          -- o que costuma estar por trás (para a IA entender, não para dizer)
  explorar text,                     -- o que descobrir antes de argumentar (código)
  argumentos text[] not null,        -- chaves de fatos (loja_info) ou fatos calculados pela máquina
  desejo text[] not null default '{}', -- o que o cliente ganha, para projetar o problema resolvido
  nunca text[] not null default '{}',  -- o que a IA não faz nessa situação (código)
  proximo_passo text not null,       -- convidar_avaliacao | deixar_porta_aberta | oferecer_compra
  fonte text
);
alter table senhor_smart_at.objecoes enable row level security;
revoke all on senhor_smart_at.objecoes from anon, authenticated;

insert into senhor_smart_at.objecoes (codigo, nome, por_tras, explorar, argumentos, desejo, nunca, proximo_passo, fonte) values
  ('preco_alto', 'Achou caro',
   '{nao_entendeu_o_que_inclui,comparando_com_outro_lugar,sem_dinheiro_agora,acha_que_nao_compensa}',
   'o_que_pesa_mais', '{faixa_inclui_peca_e_mao_de_obra,garantia_servico,valor_final_na_avaliacao,aprovacao_antes_do_conserto}',
   '{aparelho_funcionando_de_novo,impacto_relatado}', '{dar_desconto,inventar_promocao,desvalorizar_concorrente,insistir_duas_vezes}',
   'convidar_avaliacao', 'LAER (Jeb Blount): ouvir, reconhecer, explorar, responder; valor antes de preço'),
  ('comparou_concorrente', 'Achou mais barato em outro lugar',
   '{peca_de_qualidade_diferente,sem_garantia_no_outro,quer_seguranca}',
   'o_que_esta_incluso_no_outro', '{garantia_servico,valor_final_na_avaliacao,referencia_local}',
   '{seguranca_de_garantia,aparelho_funcionando_de_novo}', '{falar_mal_do_concorrente,prometer_cobrir_preco,dar_desconto}',
   'convidar_avaliacao', 'Valor percebido x preço; prova de segurança'),
  ('vou_pesquisar', 'Vai pesquisar / vai pensar',
   '{inseguranca_sobre_valor,falta_informacao,quer_comparar,sem_tempo_agora}',
   'o_que_falta_saber', '{valor_final_na_avaliacao,avaliacao_sem_custo,horario_texto}',
   '{impacto_relatado}', '{pressionar,criar_urgencia_falsa,insistir_duas_vezes}',
   'deixar_porta_aberta', 'Sandler: descobrir a dúvida real; respeitar o tempo do cliente'),
  ('nao_vale_a_pena', 'Acha que não vale consertar / prefere comprar outro',
   '{aparelho_antigo,conserto_caro_perto_do_novo,ja_queria_trocar}',
   'quanto_gosta_do_aparelho', '{faixa_inclui_peca_e_mao_de_obra,dados_preservados,venda_aparelhos,venda_sem_consulta_spc}',
   '{manter_fotos_e_conversas,economia,aparelho_novo_no_boleto}', '{empurrar_conserto,julgar_a_escolha}',
   'oferecer_compra', 'Dois caminhos honestos: consertar ou trocar na própria loja'),
  ('desconfianca', 'Medo de trocarem peça ou de não resolver',
   '{experiencia_ruim_antes,medo_de_golpe,medo_de_piorar}',
   'o_que_aconteceu_antes', '{garantia_servico,aprovacao_antes_do_conserto,conserto_na_frente,referencia_local}',
   '{seguranca_de_garantia}', '{minimizar_o_medo,prometer_resultado}',
   'convidar_avaliacao', 'Reversão de risco; transparência'),
  ('medo_perder_dados', 'Medo de perder fotos e conversas',
   '{fotos_de_familia,trabalho_no_celular,privacidade}',
   null, '{dados_preservados}',
   '{manter_fotos_e_conversas}', '{prometer_que_nada_se_perde_sem_fato_confirmado}',
   'convidar_avaliacao', 'Segurança dos dados como valor central'),
  ('prazo_urgente', 'Precisa do aparelho rápido',
   '{trabalho,contato_com_familia,sem_outro_aparelho}',
   null, '{prazo_servico,horario_texto,loja_aberta_agora}',
   '{aparelho_de_volta_hoje,impacto_relatado}', '{prometer_prazo_fora_do_dado}',
   'convidar_avaliacao', 'Velocidade como benefício quando o dado permite'),
  ('sem_tempo_de_ir', 'Difícil ir até a loja',
   '{trabalha_no_horario,mora_longe,nao_conhece_o_local}',
   'melhor_dia_e_periodo', '{referencia_local,horario_texto,leva_e_traz}',
   '{aparelho_funcionando_de_novo}', '{prometer_leva_e_traz_sem_fato_confirmado}',
   'convidar_avaliacao', 'Remover atrito; detalhe prático de dia/período')
on conflict (codigo) do update set nome = excluded.nome, por_tras = excluded.por_tras, explorar = excluded.explorar,
  argumentos = excluded.argumentos, desejo = excluded.desejo, nunca = excluded.nunca,
  proximo_passo = excluded.proximo_passo, fonte = excluded.fonte;

-- 4. O Carregar Contexto passa a entregar objeções e detalhes (continua cego ao estado)
create or replace function senhor_smart_at.v1_carregar_contexto(p_agora timestamptz default now())
returns jsonb language sql stable
set search_path = senhor_smart_at, public as $$
  select jsonb_build_object(
    'loja', (select jsonb_object_agg(chave, valor) from loja_info where confirmado and chave not like 'fila_%'),
    'loja_a_confirmar', (select coalesce(jsonb_agg(chave), '[]') from loja_info where not confirmado and chave not like 'fila_%'),
    'filas', (select jsonb_object_agg(replace(chave, 'fila_', ''), valor) from loja_info where chave like 'fila_%'),
    'horario', (select jsonb_agg(jsonb_build_object('dia_semana', dia_semana, 'abre', to_char(abre, 'HH24:MI'),
                                                    'fecha', to_char(fecha, 'HH24:MI'), 'fechado', fechado) order by dia_semana)
                from horario_funcionamento),
    'feriados', (select coalesce(jsonb_agg(jsonb_build_object('data', data, 'nome', nome)), '[]') from feriados
                 where data between (p_agora at time zone 'America/Sao_Paulo')::date
                                and (p_agora at time zone 'America/Sao_Paulo')::date + 14),
    'categorias', (select jsonb_agg(jsonb_build_object('id', id, 'nome', nome, 'atende', atende,
                                                       'fila_transferencia', fila_transferencia)) from categorias),
    'modelos', (select jsonb_agg(jsonb_build_object('categoria', categoria, 'marca', marca, 'padrao', padrao,
                                                    'exibicao', exibicao, 'linha', linha, 'prioridade', prioridade)
                                 order by prioridade, id) from modelos),
    'servicos', (select jsonb_agg(jsonb_build_object('id', id, 'categoria', categoria, 'nome', nome, 'sintomas', sintomas,
                                                     'prazo', prazo_texto, 'exige_diagnostico', exige_diagnostico,
                                                     'detalhes', detalhes)) from servicos),
    'precos', (select jsonb_agg(jsonb_build_object('servico_id', servico_id, 'linha', linha, 'min', preco_min,
                                                   'max', preco_max, 'validado', validado)) from preco_referencia),
    'origem_regra', (select jsonb_agg(jsonb_build_object('prioridade', prioridade, 'campo', campo, 'padrao', padrao,
                                                         'canal', canal, 'campanha', campanha) order by prioridade)
                     from origem_regra),
    'objecoes', (select jsonb_agg(to_jsonb(o) - 'fonte') from objecoes o)
  )
$$;

create or replace function senhor_smart_at.v1_catalogo_extrator()
returns jsonb language sql stable
set search_path = senhor_smart_at, public as $$
  select jsonb_build_object(
    'categorias', (select jsonb_agg(id order by id) from categorias),
    'servicos', (select jsonb_agg(id order by id) from servicos),
    'objecoes', (select jsonb_agg(codigo order by codigo) from objecoes),
    'catalogo_texto', (
      select string_agg(c.id || ': ' || coalesce(
               (select string_agg(s.id || ' (' || s.nome || ')', ', ' order by s.id) from servicos s where s.categoria = c.id),
               'não atendemos'), E'\n' order by c.id)
      from categorias c)
      || E'\n\nobjecoes: ' || (select string_agg(codigo || ' (' || nome || ')', ', ' order by codigo) from objecoes)
  )
$$;
