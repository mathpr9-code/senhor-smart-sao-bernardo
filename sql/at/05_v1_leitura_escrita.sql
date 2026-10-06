-- Funções v1 da Senhor Smart (assistência). Regra: SQL passa informação, a máquina decide.
--   v1_carregar_estado   -> lê o estado (jsonb) que a máquina gravou; NULL no 1º turno
--   v1_catalogo_extrator -> enums vivos para o json_schema strict do extrator
--   v1_carregar_contexto -> dado da loja para a máquina; NUNCA lê o estado (regra de ouro)
--   v1_atualizar_estado  -> grava o estado_novo devolvido pela máquina
--   v1_registrar_turno   -> grava as métricas e o log que a máquina calculou
--   v1_followup_candidatos / v1_registrar_followup -> dado para o fluxo agendado de follow-up

-- O estado é da máquina (shape definido em Python). O banco só guarda.
alter table senhor_smart_at.conversa_estado add column if not exists estado jsonb;
alter table senhor_smart_at.conversa_estado drop constraint if exists conversa_estado_ticket_id_fkey;
alter table senhor_smart_at.atendimento add column if not exists ultima_msg_cliente_em timestamptz;

create or replace function senhor_smart_at.v1_carregar_estado(p_ticket_id bigint)
returns jsonb language sql stable
set search_path = senhor_smart_at, public as $$
  select estado from conversa_estado where ticket_id = p_ticket_id
$$;

create or replace function senhor_smart_at.v1_catalogo_extrator()
returns jsonb language sql stable
set search_path = senhor_smart_at, public as $$
  select jsonb_build_object(
    'categorias', (select jsonb_agg(id order by id) from categorias),
    'servicos', (select jsonb_agg(id order by id) from servicos),
    'catalogo_texto', (
      select string_agg(c.id || ': ' || coalesce(
               (select string_agg(s.id || ' (' || s.nome || ')', ', ' order by s.id) from servicos s where s.categoria = c.id),
               'não atendemos'), E'\n' order by c.id)
      from categorias c)
  )
$$;

-- Tudo cabe em ~15 KB e vai só para a máquina (não para o LLM), então não recorta por categoria.
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
                                                     'observacao', observacao)) from servicos),
    'precos', (select jsonb_agg(jsonb_build_object('servico_id', servico_id, 'linha', linha, 'min', preco_min,
                                                   'max', preco_max, 'validado', validado)) from preco_referencia),
    'origem_regra', (select jsonb_agg(jsonb_build_object('prioridade', prioridade, 'campo', campo, 'padrao', padrao,
                                                         'canal', canal, 'campanha', campanha) order by prioridade)
                     from origem_regra)
  )
$$;

create or replace function senhor_smart_at.v1_atualizar_estado(p_ticket_id bigint, p_estado jsonb, p_agora timestamptz default now())
returns void language sql
set search_path = senhor_smart_at, public as $$
  insert into conversa_estado (ticket_id, estado, ultima_msg_cliente_em, atualizado_em)
  values (p_ticket_id, p_estado, p_agora, now())
  on conflict (ticket_id) do update
    set estado = excluded.estado, ultima_msg_cliente_em = excluded.ultima_msg_cliente_em, atualizado_em = now()
$$;

-- p = { metricas: {...saída da máquina...}, telefone, nome_whatsapp, agora,
--       turno: {entrada, saida, latencia_ms, modelo_ia, tokens, custo_usd} }
create or replace function senhor_smart_at.v1_registrar_turno(p jsonb)
returns void language plpgsql
set search_path = senhor_smart_at, public as $$
declare
  m jsonb := p->'metricas';
  t jsonb := coalesce(p->'turno', '{}');
  v_ticket bigint := (m->>'ticket_id')::bigint;
  v_agora timestamptz := coalesce(nullif(p->>'agora', '')::timestamptz, now());
begin
  if v_ticket is null or coalesce((m->>'duplicata')::boolean, false) then
    return;
  end if;

  insert into atendimento as a (
    ticket_id, telefone, nome_whatsapp, nome_cliente, canal, campanha, primeira_msg_em, primeira_resposta_em,
    fora_horario, categoria, marca, modelo, linha, defeito, servico_id, faixa_min, faixa_max, preco_validado,
    etapa, etapa_max, orcamento_enviado_em, agendado_em, visita_combinada, transferido, fila_transferencia,
    motivo_transferencia, pediu_humano, reclamacao, pediu_preco, objecao_preco, turnos, fotos,
    sentimento_final, custo_usd, tokens, ultima_msg_cliente_em, atualizado_em)
  values (
    v_ticket, p->>'telefone', p->>'nome_whatsapp', m->>'nome_cliente', coalesce(m->>'canal', 'organico'), m->>'campanha',
    coalesce((m->>'primeira_msg_em')::timestamptz, v_agora), now(),
    coalesce((m->>'fora_horario')::boolean, false), m->>'categoria', m->>'marca', m->>'modelo', m->>'linha',
    m->>'defeito', m->>'servico_id', (m->>'faixa_min')::numeric, (m->>'faixa_max')::numeric,
    (m->>'preco_validado')::boolean, m->>'etapa', m->>'etapa_max',
    case when m->'eventos_funil' ? 'orcamento' then now() end,
    case when m->'eventos_funil' ? 'agendado' then now() end,
    m->>'visita_texto', coalesce((m->>'transferido')::boolean, false), m->>'fila', m->>'motivo_transferencia',
    coalesce((m->>'pediu_humano')::boolean, false), coalesce((m->>'reclamacao')::boolean, false),
    coalesce((m->>'pediu_preco')::boolean, false), coalesce((m->>'objecao_preco')::boolean, false),
    1, case when (m->>'foto')::boolean then 1 else 0 end, m->>'sentimento',
    coalesce((t->>'custo_usd')::numeric, 0), coalesce((t->>'tokens')::int, 0), v_agora, now())
  on conflict (ticket_id) do update set
    telefone = coalesce(a.telefone, excluded.telefone),
    nome_cliente = coalesce(excluded.nome_cliente, a.nome_cliente),
    categoria = excluded.categoria, marca = excluded.marca, modelo = excluded.modelo, linha = excluded.linha,
    defeito = excluded.defeito, servico_id = excluded.servico_id, faixa_min = excluded.faixa_min,
    faixa_max = excluded.faixa_max, preco_validado = excluded.preco_validado,
    etapa = case when a.etapa in ('na_loja', 'os_aberta', 'fechado', 'perdido') then a.etapa else excluded.etapa end,
    etapa_max = case when a.etapa_max in ('na_loja', 'os_aberta', 'fechado') then a.etapa_max else excluded.etapa_max end,
    orcamento_enviado_em = coalesce(a.orcamento_enviado_em, excluded.orcamento_enviado_em),
    agendado_em = coalesce(a.agendado_em, excluded.agendado_em),
    visita_combinada = coalesce(excluded.visita_combinada, a.visita_combinada),
    transferido = a.transferido or excluded.transferido,
    fila_transferencia = coalesce(excluded.fila_transferencia, a.fila_transferencia),
    motivo_transferencia = coalesce(excluded.motivo_transferencia, a.motivo_transferencia),
    pediu_humano = a.pediu_humano or excluded.pediu_humano,
    reclamacao = a.reclamacao or excluded.reclamacao,
    pediu_preco = a.pediu_preco or excluded.pediu_preco,
    objecao_preco = a.objecao_preco or excluded.objecao_preco,
    turnos = a.turnos + 1, fotos = a.fotos + excluded.fotos,
    sentimento_final = coalesce(excluded.sentimento_final, a.sentimento_final),
    custo_usd = a.custo_usd + excluded.custo_usd, tokens = a.tokens + excluded.tokens,
    recuperado_por_followup = a.recuperado_por_followup or a.followups_enviados > 0,
    ultima_msg_cliente_em = excluded.ultima_msg_cliente_em, atualizado_em = now();

  insert into evento_funil (ticket_id, etapa, origem, em)
  select v_ticket, e, 'ia', now() from jsonb_array_elements_text(coalesce(m->'eventos_funil', '[]')) e;

  insert into turno_log (ticket_id, entrada, saida, intent, estrategia, sentimento, tinha_foto, latencia_ms,
                         modelo_ia, tokens, custo_usd)
  values (v_ticket, t->>'entrada', t->>'saida', m->>'intencao', m->>'movimento' || ':' || coalesce(m->>'objetivo', ''),
          m->>'sentimento', coalesce((m->>'foto')::boolean, false), (t->>'latencia_ms')::int, t->>'modelo_ia',
          (t->>'tokens')::int, (t->>'custo_usd')::numeric);
end $$;

-- Follow-up: só entrega os candidatos. Quem decide se manda e o quê é a máquina (/followup).
create or replace function senhor_smart_at.v1_followup_candidatos(p_limite int default 50)
returns table (ticket_id bigint, telefone text, estado jsonb, ultima_msg_cliente_em timestamptz, followups_enviados int)
language sql stable
set search_path = senhor_smart_at, public as $$
  select a.ticket_id, a.telefone, ce.estado, a.ultima_msg_cliente_em, a.followups_enviados
  from atendimento a join conversa_estado ce using (ticket_id)
  where a.etapa in ('triagem', 'diagnostico', 'orcamento') and not a.transferido
    and a.ultima_msg_cliente_em < now() - interval '20 hours'
    and a.followups_enviados < 2
  order by a.ultima_msg_cliente_em
  limit p_limite
$$;

create or replace function senhor_smart_at.v1_registrar_followup(p_ticket_id bigint, p_tipo text)
returns void language sql
set search_path = senhor_smart_at, public as $$
  insert into followup (ticket_id, tipo, agendado_para, status, enviado_em)
  values (p_ticket_id, p_tipo, now(), 'enviado', now())
  on conflict (ticket_id, tipo) do update set status = 'enviado', enviado_em = now();
  update atendimento set followups_enviados = followups_enviados + 1 where ticket_id = p_ticket_id;
$$;

-- Filas de transferência do DeskRio (internas, nunca ditas ao cliente). Confirmar os IDs reais.
insert into loja_info (chave, valor, confirmado) values
  ('fila_tecnico', '64000384', false), ('fila_vendas', '64000384', false), ('fila_humano', '64000384', false)
on conflict (chave) do nothing;
