-- v1.1: resumo do dia para o dono (WhatsApp) e follow-up que inclui o lembrete de visita.
-- Só agregação e filtro de dado. Quem decide mandar follow-up é a máquina (/followup).

insert into senhor_smart_at.loja_info (chave, valor, confirmado) values
  ('faixa_inclui_peca_e_mao_de_obra', 'a faixa de preço já inclui a peça e a mão de obra', false)
on conflict (chave) do nothing;

create or replace function senhor_smart_at.v1_followup_candidatos(p_limite int default 50)
returns table (ticket_id bigint, telefone text, estado jsonb, ultima_msg_cliente_em timestamptz, followups_enviados int)
language sql stable
set search_path = senhor_smart_at, public as $$
  select a.ticket_id, a.telefone, ce.estado, a.ultima_msg_cliente_em, a.followups_enviados
  from atendimento a join conversa_estado ce using (ticket_id)
  where (a.etapa in ('triagem', 'diagnostico', 'orcamento') and not a.transferido
         and a.ultima_msg_cliente_em < now() - interval '20 hours' and a.followups_enviados < 2)
     or (a.etapa = 'agendado' and a.agendado_em < now() - interval '12 hours'
         and not coalesce((ce.estado->>'lembrete_visita_enviado')::boolean, false))
  order by a.ultima_msg_cliente_em
  limit p_limite
$$;

-- Resumo de um dia (padrão: hoje em São Paulo). Comparação com a média dos 7 dias anteriores.
create or replace function senhor_smart_at.v1_resumo_dia(p_dia date default (now() at time zone 'America/Sao_Paulo')::date)
returns jsonb language sql stable
set search_path = senhor_smart_at, public as $$
with dia as (
  select * from atendimento where ticket_id > 0
    and (primeira_msg_em at time zone 'America/Sao_Paulo')::date = p_dia
),
semana as (
  select (primeira_msg_em at time zone 'America/Sao_Paulo')::date d, count(*) n,
         count(*) filter (where etapa_rank(etapa_max) >= 4) ag
  from atendimento where ticket_id > 0
    and (primeira_msg_em at time zone 'America/Sao_Paulo')::date between p_dia - 7 and p_dia - 1
  group by 1
)
select jsonb_build_object(
  'dia', p_dia,
  'leads', (select count(*) from dia),
  'fora_do_horario', (select count(*) from dia where fora_horario),
  'orcamentos', (select count(*) from dia where etapa_rank(etapa_max) >= 3),
  'agendados', (select count(*) from dia where etapa_rank(etapa_max) >= 4),
  'fechados_hoje', (select count(*) from atendimento where ticket_id > 0 and (fechado_em at time zone 'America/Sao_Paulo')::date = p_dia),
  'receita_hoje', (select coalesce(sum(valor_fechado), 0) from atendimento where ticket_id > 0 and (fechado_em at time zone 'America/Sao_Paulo')::date = p_dia),
  'tempo_primeira_resposta_s', (select round(percentile_cont(0.5) within group (order by extract(epoch from primeira_resposta_em - primeira_msg_em))::numeric)
                                from dia where primeira_resposta_em is not null),
  'por_canal', (select coalesce(jsonb_object_agg(canal, n), '{}') from (select canal, count(*) n from dia group by 1) x),
  'top_servicos', (select coalesce(jsonb_agg(jsonb_build_array(nome, n) order by n desc), '[]') from (
                    select s.nome, count(*) n from dia join servicos s on s.id = dia.servico_id group by 1 order by 2 desc limit 3) x),
  'objecoes', (select count(*) from dia where objecao_preco),
  'parados_com_orcamento', (select count(*) from atendimento where etapa = 'orcamento' and ticket_id > 0
                            and atualizado_em < now() - interval '24 hours'),
  'visitas_combinadas_para_amanha', (select count(*) from atendimento where ticket_id > 0
                                     and etapa = 'agendado' and visita_combinada ilike '%amanh%'
                                     and (agendado_em at time zone 'America/Sao_Paulo')::date = p_dia),
  'media_7_dias', (select jsonb_build_object('leads', round(avg(n), 1), 'agendados', round(avg(ag), 1)) from semana)
)
$$;
