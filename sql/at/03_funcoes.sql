-- Funções da assistência técnica. "Banco decide, prompt narra".

create or replace function senhor_smart_at.norm(p text) returns text
language sql immutable as $$
  select lower(public.unaccent(coalesce(p, '')))
$$;

-- Situação de horário da loja no momento da mensagem
create or replace function senhor_smart_at.situacao_horario(p_ts timestamptz)
returns table (situacao text, aberto boolean, proxima_abertura text)
language plpgsql stable
set search_path = senhor_smart_at, public
as $$
declare
  v_local timestamp := coalesce(p_ts, now()) at time zone 'America/Sao_Paulo';
  v_dow int := extract(dow from v_local)::int;
  v_h horario_funcionamento%rowtype;
  v_prox text;
  i int;
  v_d date;
  v_n horario_funcionamento%rowtype;
begin
  -- próxima abertura (texto curto para a IA)
  for i in 0..7 loop
    v_d := v_local::date + i;
    select * into v_n from horario_funcionamento where dia_semana = extract(dow from v_d)::int;
    continue when v_n.fechado or v_n.abre is null or exists (select 1 from feriados where data = v_d);
    continue when i = 0 and v_local::time >= v_n.abre;
    v_prox := case when i = 0 then 'hoje' when i = 1 then 'amanhã'
                   else (array['domingo','segunda','terça','quarta','quinta','sexta','sábado'])[extract(dow from v_d)::int + 1] end
              || ' às ' || to_char(v_n.abre, 'FMHH24"h"MI');
    exit;
  end loop;

  if exists (select 1 from feriados where data = v_local::date) then
    return query select 'feriado'::text, false, v_prox; return;
  end if;
  select * into v_h from horario_funcionamento where dia_semana = v_dow;
  if v_h.fechado or v_h.abre is null then
    return query select 'fechado_hoje'::text, false, v_prox; return;
  end if;
  if v_local::time < v_h.abre then
    return query select 'antes_de_abrir'::text, false, v_prox;
  elsif v_local::time < v_h.fecha then
    return query select 'aberto'::text, true, null::text;
  else
    return query select 'apos_fechar'::text, false, v_prox;
  end if;
end $$;

-- Canal/campanha a partir da 1ª mensagem e do sinal de anúncio
create or replace function senhor_smart_at.detectar_origem(p_mensagem text, p_anuncio text)
returns table (canal text, campanha text)
language sql stable
set search_path = senhor_smart_at, public
as $$
  select r.canal, coalesce(case when r.campo = 'anuncio' then nullif(p_anuncio, '') end, r.campanha)
  from origem_regra r
  where (r.campo = 'anuncio' and coalesce(p_anuncio, '') <> '')
     or (r.campo = 'mensagem' and norm(p_mensagem) ilike norm(r.padrao))
  order by r.prioridade
  limit 1
$$;

-- Modelo citado → categoria, marca, nome de exibição, linha de preço
create or replace function senhor_smart_at.identificar_modelo(p_texto text, p_categoria text default null)
returns table (categoria text, marca text, exibicao text, linha text)
language plpgsql stable
set search_path = senhor_smart_at, public
as $$
declare
  t text := norm(p_texto);
  m record;
  g text[];
begin
  if t = '' then return; end if;
  for m in select * from modelos
           where (p_categoria is null or modelos.categoria = p_categoria)
           order by prioridade, id loop
    g := regexp_match(t, m.padrao, 'i');
    if g is not null then
      return query select m.categoria, m.marca,
        trim(regexp_replace(m.exibicao, '\\1', upper(coalesce(g[1], '')))),
        m.linha;
      return;
    end if;
  end loop;
end $$;

-- Serviço provável: sugestão do extrator (se válida) ou sintomas no texto
create or replace function senhor_smart_at.identificar_servico(p_categoria text, p_texto text, p_sugestao text)
returns text
language sql stable
set search_path = senhor_smart_at, public
as $$
  select coalesce(
    (select id from servicos where id = p_sugestao and (p_categoria is null or categoria = p_categoria)),
    (select s.id from servicos s
       cross join lateral (select count(*) n from unnest(s.sintomas) x where norm(p_texto) like '%' || norm(x) || '%') c
      where s.categoria = p_categoria and c.n > 0
      order by c.n desc, s.exige_diagnostico, s.id
      limit 1)
  )
$$;

create or replace function senhor_smart_at.cotar(p_servico text, p_linha text)
returns table (preco_min numeric, preco_max numeric, validado boolean)
language sql stable
set search_path = senhor_smart_at, public
as $$
  select preco_min, preco_max, validado from preco_referencia
  where servico_id = p_servico and (linha = p_linha or linha is null)
  order by (linha is null)
  limit 1
$$;

create or replace function senhor_smart_at.fmt_brl(p numeric) returns text
language sql immutable as $$
  select 'R$ ' || replace(to_char(p, 'FM999G999'), ',', '.')
$$;

-- ============ MONTAR CONTEXTO ============
-- Entrada (jsonb):
-- { ticket_id, telefone, nome_whatsapp, mensagem, timestamp, anuncio, tipo_midia,
--   extrator: { intent, categoria, marca, modelo, defeito, servico_sugerido, sentimento,
--               nome_informado, visita_texto, perguntou_preco, objecao_preco },
--   visao: { categoria, marca, modelo, dano_visivel, descricao } }
create or replace function senhor_smart_at.montar_contexto(p jsonb)
returns jsonb
language plpgsql
set search_path = senhor_smart_at, public
as $$
declare
  v_ticket bigint := (p->>'ticket_id')::bigint;
  v_ts timestamptz := coalesce(nullif(p->>'timestamp', '')::timestamptz, now());
  e jsonb := coalesce(p->'extrator', '{}');
  vz jsonb := coalesce(p->'visao', '{}');
  v_msg text := coalesce(p->>'mensagem', '');
  v_intent text := coalesce(nullif(e->>'intent', ''), 'outro');
  v_sent text := coalesce(nullif(e->>'sentimento', ''), 'neutro');
  a atendimento%rowtype;
  st conversa_estado%rowtype;
  h record;
  o record;
  mdl record;
  v_primeira boolean := false;
  v_cat text;
  v_serv text;
  v_serv_ant text;
  v_preco record;
  sv servicos%rowtype;
  v_tem_modelo boolean;
  v_tem_preco boolean;
  v_atende boolean;
  s conversation_strategies%rowtype;
  v_passo text;
  v_etapa_ia text;
  v_loja jsonb;
  v_recuperado boolean := false;
begin
  select * into h from situacao_horario(v_ts);

  -- 1. Atendimento novo: origem, horário, funil
  select * into a from atendimento where ticket_id = v_ticket for update;
  if not found then
    v_primeira := true;
    select * into o from detectar_origem(v_msg, p->>'anuncio');
    insert into atendimento (ticket_id, telefone, nome_whatsapp, canal, campanha, primeira_msg_em, fora_horario)
    values (v_ticket, p->>'telefone', p->>'nome_whatsapp', coalesce(o.canal, 'organico'), o.campanha, v_ts, not h.aberto)
    returning * into a;
    insert into conversa_estado (ticket_id) values (v_ticket);
    insert into evento_funil (ticket_id, etapa, origem, em) values (v_ticket, 'novo', 'sistema', v_ts);
  end if;
  select * into st from conversa_estado where ticket_id = v_ticket;

  -- 2. Cliente respondeu: follow-up enviado vira recuperação; pendentes são cancelados
  update followup set status = 'respondido', respondido_em = v_ts
   where ticket_id = v_ticket and status = 'enviado';
  if found then v_recuperado := true; end if;
  update followup set status = 'cancelado' where ticket_id = v_ticket and status = 'pendente';

  -- 3. Equipamento, modelo e linha de preço
  v_cat := coalesce(
    (select id from categorias where id = nullif(e->>'categoria', '')),
    (select id from categorias where id = nullif(vz->>'categoria', '')),
    a.categoria);
  select * into mdl from identificar_modelo(concat_ws(' ', e->>'marca', e->>'modelo', vz->>'marca', vz->>'modelo'), v_cat);
  if mdl.marca is null then
    select * into mdl from identificar_modelo(v_msg, v_cat);
  end if;
  if mdl.marca is not null then
    v_cat := coalesce(v_cat, mdl.categoria);
    a.marca := mdl.marca;
    a.modelo := mdl.exibicao;
    a.linha := mdl.linha;
  elsif nullif(e->>'marca', '') is not null and a.marca is null then
    a.marca := e->>'marca';
    a.modelo := nullif(e->>'modelo', '');
  end if;
  a.categoria := v_cat;
  if a.linha is null and v_cat in ('notebook', 'videogame', 'computador') then
    a.linha := 'padrao';
  end if;

  -- 4. Defeito e serviço
  a.defeito := coalesce(nullif(e->>'defeito', ''), a.defeito,
                        case when coalesce(vz->>'dano_visivel', '') not in ('', 'nenhum') then vz->>'dano_visivel' end);
  v_serv_ant := a.servico_id;
  v_serv := identificar_servico(v_cat, concat_ws(' ', a.defeito, v_msg), e->>'servico_sugerido');
  if v_serv is not null then a.servico_id := v_serv; end if;
  select * into sv from servicos where id = a.servico_id;

  select * into v_preco from cotar(a.servico_id, a.linha);
  a.faixa_min := v_preco.preco_min;
  a.faixa_max := v_preco.preco_max;
  a.preco_validado := v_preco.validado;

  -- Mudou o serviço depois do orçamento: volta para diagnóstico para cotar de novo
  if v_serv_ant is not null and a.servico_id is distinct from v_serv_ant and etapa_rank(a.etapa) = 3 then
    a.etapa := 'diagnostico';
  end if;

  -- 5. Sinais e contadores
  if a.nome_cliente is null and nullif(e->>'nome_informado', '') is not null then
    a.nome_cliente := initcap(split_part(trim(e->>'nome_informado'), ' ', 1));
  end if;
  a.turnos := a.turnos + 1;
  a.fotos := a.fotos + case when p->>'tipo_midia' = 'imagem' then 1 else 0 end;
  a.audios := a.audios + case when p->>'tipo_midia' = 'audio' then 1 else 0 end;
  a.pediu_preco := a.pediu_preco or coalesce((e->>'perguntou_preco')::boolean, false);
  a.objecao_preco := a.objecao_preco or v_intent = 'objecao_preco' or coalesce((e->>'objecao_preco')::boolean, false);
  a.pediu_humano := a.pediu_humano or v_intent = 'pediu_humano';
  a.reclamacao := a.reclamacao or v_intent = 'reclamacao';
  a.sentimento_final := v_sent;
  a.recuperado_por_followup := a.recuperado_por_followup or v_recuperado;

  -- 6. Etapa que a IA controla (até diagnóstico; orçamento/agendado vêm do turno registrado)
  if etapa_rank(a.etapa) < 3 then
    v_etapa_ia := case when a.categoria is not null and a.defeito is not null then 'diagnostico'
                       when a.categoria is not null then 'triagem'
                       else 'novo' end;
    if etapa_rank(v_etapa_ia) > etapa_rank(a.etapa) then
      a.etapa := v_etapa_ia;
      insert into evento_funil (ticket_id, etapa, origem, em) values (v_ticket, v_etapa_ia, 'ia', v_ts);
    end if;
  end if;
  if etapa_rank(a.etapa) > etapa_rank(a.etapa_max) then a.etapa_max := a.etapa; end if;

  -- 7. Estratégia do turno (primeira regra que casa)
  v_tem_modelo := a.linha is not null
               or (a.marca is not null and a.categoria <> 'celular')
               or exists (select 1 from preco_referencia where servico_id = a.servico_id and linha is null);
  v_tem_preco := a.faixa_min is not null and not coalesce(sv.exige_diagnostico, false);
  select atende into v_atende from categorias where id = a.categoria;

  select * into s from conversation_strategies cs
   where cs.ativo
     and (cs.quando_intent is null or v_intent = any(cs.quando_intent))
     and (cs.quando_sentimento is null or v_sent = any(cs.quando_sentimento))
     and (cs.quando_etapa is null or a.etapa = any(cs.quando_etapa))
     and (cs.quando_primeira is null or cs.quando_primeira = not st.abertura_feita)
     and (cs.quando_tem_categoria is null or cs.quando_tem_categoria = (a.categoria is not null))
     and (cs.quando_tem_modelo is null or cs.quando_tem_modelo = v_tem_modelo)
     and (cs.quando_tem_defeito is null or cs.quando_tem_defeito = (a.defeito is not null))
     and (cs.quando_tem_preco is null or cs.quando_tem_preco = v_tem_preco)
     and (cs.quando_categoria_atendida is null or cs.quando_categoria_atendida = coalesce(v_atende, true))
   order by cs.prioridade
   limit 1;

  -- Próximo passo concreto: o primeiro dado que falta
  v_passo := s.proximo_passo;
  if v_passo = 'proximo_dado' then
    v_passo := case when a.categoria is null then 'perguntar_equipamento'
                    when a.defeito is null then 'perguntar_defeito'
                    when not v_tem_modelo then 'perguntar_modelo'
                    when etapa_rank(a.etapa) >= 3 then 'detalhe_pratico'
                    else 'convidar_avaliacao' end;
  end if;

  -- 8. Persistir
  a.atualizado_em := now();
  update atendimento set
    categoria = a.categoria, marca = a.marca, modelo = a.modelo, linha = a.linha, defeito = a.defeito,
    servico_id = a.servico_id, faixa_min = a.faixa_min, faixa_max = a.faixa_max, preco_validado = a.preco_validado,
    etapa = a.etapa, etapa_max = a.etapa_max, nome_cliente = a.nome_cliente, turnos = a.turnos,
    fotos = a.fotos, audios = a.audios, pediu_preco = a.pediu_preco, objecao_preco = a.objecao_preco,
    pediu_humano = a.pediu_humano, reclamacao = a.reclamacao, sentimento_final = a.sentimento_final,
    recuperado_por_followup = a.recuperado_por_followup, atualizado_em = a.atualizado_em
  where ticket_id = v_ticket;

  update conversa_estado set
    ultima_estrategia = s.nome, ultimo_objetivo = s.objetivo, ultima_msg_cliente_em = v_ts,
    dados_perguntados = case when v_passo like 'perguntar_%' and not (replace(v_passo, 'perguntar_', '') = any(dados_perguntados))
                             then dados_perguntados || replace(v_passo, 'perguntar_', '') else dados_perguntados end,
    atualizado_em = now()
  where ticket_id = v_ticket;

  select jsonb_object_agg(chave, valor) into v_loja from loja_info where confirmado;

  -- 9. Contexto para o executor (só narra)
  return jsonb_build_object(
    'estrategia', jsonb_build_object(
      'nome', s.nome,
      'objetivo', s.objetivo,
      'acolher_antes', s.acolher_antes,
      'pode_falar_preco', s.pode_cotar and v_tem_preco,
      'proximo_passo', v_passo,
      'transferir', s.transferir_fila is not null,
      'saudar', not st.abertura_feita,
      'usar_nome', a.nome_cliente is not null and s.objetivo in ('confirmar_visita', 'encerrar', 'encaminhar', 'encaminhar_vendas'),
      'ja_perguntado', (select dados_perguntados from conversa_estado where ticket_id = v_ticket),
      'repetir_preco', false
    ),
    'atendimento', jsonb_build_object(
      'nome_cliente', a.nome_cliente,
      'equipamento', (select nome from categorias where id = a.categoria),
      'marca', a.marca,
      'modelo', a.modelo,
      'defeito', a.defeito,
      'etapa', a.etapa,
      'orcamento_ja_enviado', a.orcamento_enviado_em is not null,
      'visita_combinada', a.visita_combinada
    ),
    'servico', case when sv.id is null then null else jsonb_build_object(
      'nome', sv.nome, 'prazo', sv.prazo_texto, 'precisa_avaliacao', sv.exige_diagnostico, 'observacao', sv.observacao) end,
    'preco', jsonb_build_object(
      'disponivel', s.pode_cotar and v_tem_preco,
      'faixa', case when s.pode_cotar and v_tem_preco then 'entre ' || fmt_brl(a.faixa_min) || ' e ' || fmt_brl(a.faixa_max) end,
      'observacao', case when s.pode_cotar and v_tem_preco then 'valor final confirmado na avaliação, depende da peça' end
    ),
    'loja', v_loja,
    'horario', jsonb_build_object('situacao', h.situacao, 'aberto', h.aberto, 'proxima_abertura', h.proxima_abertura),
    'sinais', jsonb_build_object(
      'intent', v_intent, 'sentimento', v_sent,
      'mandou_foto', p->>'tipo_midia' = 'imagem',
      'o_que_a_foto_mostra', nullif(vz->>'descricao', ''),
      'visita_texto', nullif(e->>'visita_texto', ''),
      'voltou_apos_lembrete', v_recuperado
    ),
    'equipamentos_atendidos', (select jsonb_agg(nome order by nome) from categorias where atende),
    'transferir_fila', s.transferir_fila
  );
end $$;

-- ============ REGISTRAR TURNO (depois do envio) ============
-- { ticket_id, entrada, saida, intent, sentimento, tinha_foto, latencia_ms, modelo_ia, tokens, custo_usd,
--   transferiu, fila, motivo_transferencia, visita_texto }
create or replace function senhor_smart_at.registrar_turno(p jsonb)
returns void
language plpgsql
set search_path = senhor_smart_at, public
as $$
declare
  v_ticket bigint := (p->>'ticket_id')::bigint;
  a atendimento%rowtype;
  st conversa_estado%rowtype;
  v_now timestamptz := now();
begin
  select * into a from atendimento where ticket_id = v_ticket for update;
  if not found then return; end if;
  select * into st from conversa_estado where ticket_id = v_ticket;

  insert into turno_log (ticket_id, entrada, saida, intent, estrategia, sentimento, tinha_foto, latencia_ms, modelo_ia, tokens, custo_usd)
  values (v_ticket, p->>'entrada', p->>'saida', p->>'intent', st.ultima_estrategia, p->>'sentimento',
          coalesce((p->>'tinha_foto')::boolean, false), (p->>'latencia_ms')::int, p->>'modelo_ia',
          (p->>'tokens')::int, (p->>'custo_usd')::numeric);

  a.primeira_resposta_em := coalesce(a.primeira_resposta_em, v_now);
  a.tokens := a.tokens + coalesce((p->>'tokens')::int, 0);
  a.custo_usd := a.custo_usd + coalesce((p->>'custo_usd')::numeric, 0);

  -- Orçamento: a estratégia mandou cotar ou convidar para avaliação
  if st.ultima_estrategia in ('cotar', 'precisa_avaliacao') and etapa_rank(a.etapa) < 3 then
    a.etapa := 'orcamento';
    a.orcamento_enviado_em := coalesce(a.orcamento_enviado_em, v_now);
    insert into evento_funil (ticket_id, etapa, origem, dados)
    values (v_ticket, 'orcamento', 'ia', jsonb_build_object('servico', a.servico_id, 'min', a.faixa_min, 'max', a.faixa_max));
  end if;

  -- Visita combinada
  if st.ultima_estrategia = 'confirmou_visita' and etapa_rank(a.etapa) < 4 then
    a.etapa := 'agendado';
    a.agendado_em := v_now;
    a.visita_combinada := coalesce(nullif(p->>'visita_texto', ''), a.visita_combinada);
    insert into evento_funil (ticket_id, etapa, origem, dados)
    values (v_ticket, 'agendado', 'ia', jsonb_build_object('quando', a.visita_combinada));
  end if;
  if etapa_rank(a.etapa) > etapa_rank(a.etapa_max) then a.etapa_max := a.etapa; end if;

  if coalesce((p->>'transferiu')::boolean, false) and not a.transferido then
    a.transferido := true;
    a.fila_transferencia := p->>'fila';
    a.motivo_transferencia := coalesce(p->>'motivo_transferencia', st.ultima_estrategia);
  end if;

  update atendimento set
    primeira_resposta_em = a.primeira_resposta_em, tokens = a.tokens, custo_usd = a.custo_usd,
    etapa = a.etapa, etapa_max = a.etapa_max, orcamento_enviado_em = a.orcamento_enviado_em,
    agendado_em = a.agendado_em, visita_combinada = a.visita_combinada,
    transferido = a.transferido, fila_transferencia = a.fila_transferencia,
    motivo_transferencia = a.motivo_transferencia, atualizado_em = v_now
  where ticket_id = v_ticket;

  update conversa_estado set abertura_feita = true, ultima_msg_ia_em = v_now, atualizado_em = v_now
  where ticket_id = v_ticket;

  -- Follow-up: lead ativo que ainda não agendou recebe lembrete dentro da janela de 24h do WhatsApp
  -- e um reengajamento em 72h (exige template aprovado).
  if a.etapa in ('triagem', 'diagnostico', 'orcamento') and not a.transferido then
    insert into followup (ticket_id, tipo, agendado_para) values
      (v_ticket, 'lembrete_20h', coalesce(st.ultima_msg_cliente_em, v_now) + interval '20 hours'),
      (v_ticket, 'reengajar_72h', coalesce(st.ultima_msg_cliente_em, v_now) + interval '72 hours')
    on conflict (ticket_id, tipo) do update
      set agendado_para = excluded.agendado_para, status = 'pendente'
      where followup.status in ('pendente', 'cancelado', 'respondido');
  end if;
end $$;

-- ============ DESFECHO (vendedor / técnico) ============
-- { ticket_id, etapa: na_loja | os_aberta | fechado | perdido, valor, motivo }
create or replace function senhor_smart_at.registrar_desfecho(p jsonb)
returns jsonb
language plpgsql
set search_path = senhor_smart_at, public
as $$
declare
  v_ticket bigint := (p->>'ticket_id')::bigint;
  v_etapa text := p->>'etapa';
  a atendimento%rowtype;
begin
  if v_etapa not in ('na_loja', 'os_aberta', 'fechado', 'perdido') then
    raise exception 'etapa inválida: %', v_etapa;
  end if;
  update atendimento set
    etapa = v_etapa,
    etapa_max = case when etapa_rank(v_etapa) > etapa_rank(etapa_max) then v_etapa else etapa_max end,
    valor_fechado = case when v_etapa = 'fechado' then nullif(p->>'valor', '')::numeric else valor_fechado end,
    fechado_em = case when v_etapa = 'fechado' then now() else fechado_em end,
    motivo_perda = case when v_etapa = 'perdido' then coalesce(nullif(p->>'motivo', ''), 'nao_informado') else motivo_perda end,
    atualizado_em = now()
  where ticket_id = v_ticket
  returning * into a;
  if not found then raise exception 'ticket % não encontrado', v_ticket; end if;
  insert into evento_funil (ticket_id, etapa, origem, dados)
  values (v_ticket, v_etapa, coalesce(p->>'origem', 'vendedor'), p - 'ticket_id');
  update followup set status = 'cancelado' where ticket_id = v_ticket and status = 'pendente';
  return jsonb_build_object('ticket_id', v_ticket, 'etapa', a.etapa, 'valor', a.valor_fechado);
end $$;

-- ============ FOLLOW-UP ============
create or replace function senhor_smart_at.followups_devidos(p_limite int default 50)
returns table (followup_id bigint, ticket_id bigint, tipo text, telefone text, nome_cliente text,
               equipamento text, modelo text, defeito text, servico text, faixa text, etapa text)
language sql
set search_path = senhor_smart_at, public
as $$
  select f.id, a.ticket_id, f.tipo, a.telefone, a.nome_cliente, c.nome, a.modelo, a.defeito, s.nome,
         case when a.faixa_min is not null then 'entre ' || fmt_brl(a.faixa_min) || ' e ' || fmt_brl(a.faixa_max) end,
         a.etapa
  from followup f
  join atendimento a using (ticket_id)
  left join categorias c on c.id = a.categoria
  left join servicos s on s.id = a.servico_id
  where f.status = 'pendente' and f.agendado_para <= now()
    and a.etapa in ('triagem', 'diagnostico', 'orcamento') and not a.transferido
    and extract(hour from now() at time zone 'America/Sao_Paulo') between 9 and 19
  order by f.agendado_para
  limit p_limite
$$;

create or replace function senhor_smart_at.marcar_followup_enviado(p_followup_id bigint)
returns void
language sql
set search_path = senhor_smart_at, public
as $$
  with f as (update followup set status = 'enviado', enviado_em = now() where id = p_followup_id returning ticket_id)
  update atendimento set followups_enviados = followups_enviados + 1 where ticket_id = (select ticket_id from f);
$$;
