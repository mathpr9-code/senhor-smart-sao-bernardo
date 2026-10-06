-- Painel do cliente: todos os agregados em um JSON. Sem telefone, nome ou texto de conversa.
-- Chamado pela Edge Function com service_role.

create or replace function senhor_smart_at.painel(p_inicio date, p_fim date, p_canal text default null)
returns jsonb
language sql stable
security definer
set search_path = senhor_smart_at, public
as $$
with a as (
  select *, (primeira_msg_em at time zone 'America/Sao_Paulo') as local_em,
         extract(epoch from (primeira_resposta_em - primeira_msg_em)) as resp_s
  from atendimento
  where (primeira_msg_em at time zone 'America/Sao_Paulo')::date between p_inicio and p_fim
    and (p_canal is null or canal = p_canal)
),
tot as (
  select count(*) leads,
         count(*) filter (where etapa_rank(etapa_max) >= 3) orcamentos,
         count(*) filter (where etapa_rank(etapa_max) >= 4) agendados,
         count(*) filter (where etapa = 'fechado') fechados,
         count(*) filter (where etapa = 'perdido') perdidos,
         coalesce(sum(valor_fechado) filter (where etapa = 'fechado'), 0) receita,
         count(*) filter (where fora_horario) fora_horario,
         count(*) filter (where recuperado_por_followup) recuperados,
         percentile_cont(0.5) within group (order by resp_s) filter (where resp_s is not null) resp_mediana_s,
         percentile_cont(0.5) within group (order by extract(epoch from (agendado_em - primeira_msg_em)) / 3600)
           filter (where agendado_em is not null) horas_ate_agendar,
         coalesce(sum(custo_usd), 0) custo_usd
  from a
)
select jsonb_build_object(
  'periodo', jsonb_build_object('inicio', p_inicio, 'fim', p_fim, 'canal', p_canal),
  'kpis', (select jsonb_build_object(
      'leads', leads, 'orcamentos', orcamentos, 'agendados', agendados, 'fechados', fechados, 'perdidos', perdidos,
      'receita', receita, 'ticket_medio', case when fechados > 0 then round(receita / fechados, 2) end,
      'conversao_agendamento', case when leads > 0 then round(100.0 * agendados / leads, 1) end,
      'conversao_fechamento', case when leads > 0 then round(100.0 * fechados / leads, 1) end,
      'fora_horario', fora_horario, 'recuperados_followup', recuperados,
      'tempo_primeira_resposta_s', round(resp_mediana_s::numeric, 0),
      'horas_ate_agendar', round(horas_ate_agendar::numeric, 1),
      'custo_ia_usd', round(custo_usd, 2)) from tot),
  'funil', (select jsonb_agg(jsonb_build_array(rot, n) order by ord) from (
      select 1 ord, 'Leads' rot, count(*) n from a
      union all select 2, 'Equipamento identificado', count(*) filter (where etapa_rank(etapa_max) >= 1) from a
      union all select 3, 'Defeito entendido', count(*) filter (where etapa_rank(etapa_max) >= 2) from a
      union all select 4, 'Orçamento enviado', count(*) filter (where etapa_rank(etapa_max) >= 3) from a
      union all select 5, 'Visita agendada', count(*) filter (where etapa_rank(etapa_max) >= 4) from a
      union all select 6, 'Aparelho na loja', count(*) filter (where etapa_rank(etapa_max) >= 5) from a
      union all select 7, 'Fechado', count(*) filter (where etapa = 'fechado') from a) f),
  'canais', (select coalesce(jsonb_agg(jsonb_build_array(canal, n, ag, fe, rec) order by n desc), '[]') from (
      select canal, count(*) n, count(*) filter (where etapa_rank(etapa_max) >= 4) ag,
             count(*) filter (where etapa = 'fechado') fe, coalesce(sum(valor_fechado) filter (where etapa = 'fechado'), 0) rec
      from a group by canal) x),
  'campanhas', (select coalesce(jsonb_agg(jsonb_build_array(campanha, canal, n, fe) order by n desc), '[]') from (
      select coalesce(campanha, 'Sem campanha') campanha, canal, count(*) n, count(*) filter (where etapa = 'fechado') fe
      from a group by 1, 2) x),
  'diario', (select coalesce(jsonb_agg(jsonb_build_array(d, n, ag, fe) order by d), '[]') from (
      select local_em::date d, count(*) n, count(*) filter (where etapa_rank(etapa_max) >= 4) ag,
             count(*) filter (where etapa = 'fechado') fe
      from a group by 1) x),
  'heatmap', (select coalesce(jsonb_agg(jsonb_build_array(dow, h, n)), '[]') from (
      select extract(isodow from local_em)::int dow, extract(hour from local_em)::int h, count(*) n
      from a group by 1, 2) x),
  'equipamentos', (select coalesce(jsonb_agg(jsonb_build_array(nome, n, ag, fe) order by n desc), '[]') from (
      select coalesce(c.nome, 'Não identificado') nome, count(*) n,
             count(*) filter (where etapa_rank(etapa_max) >= 4) ag, count(*) filter (where etapa = 'fechado') fe
      from a left join categorias c on c.id = a.categoria group by 1) x),
  'servicos', (select coalesce(jsonb_agg(jsonb_build_array(nome, n, fe, ticket) order by n desc), '[]') from (
      select s.nome, count(*) n, count(*) filter (where etapa = 'fechado') fe,
             round(avg(valor_fechado) filter (where etapa = 'fechado'), 0) ticket
      from a join servicos s on s.id = a.servico_id group by 1 order by 2 desc limit 10) x),
  'modelos', (select coalesce(jsonb_agg(jsonb_build_array(modelo, n) order by n desc), '[]') from (
      select modelo, count(*) n from a where modelo is not null group by 1 order by 2 desc limit 10) x),
  'motivos_perda', (select coalesce(jsonb_agg(jsonb_build_array(motivo_perda, n) order by n desc), '[]') from (
      select motivo_perda, count(*) n from a where etapa = 'perdido' group by 1) x),
  'sentimento', (select coalesce(jsonb_agg(jsonb_build_array(sentimento_final, n) order by n desc), '[]') from (
      select coalesce(sentimento_final, 'neutro') sentimento_final, count(*) n from a group by 1) x),
  'parados', (select jsonb_build_object(
      'sem_resposta_24h', count(*) filter (where etapa in ('triagem', 'diagnostico', 'orcamento')
                                           and atualizado_em < now() - interval '24 hours'),
      'orcamento_sem_agendar', count(*) filter (where etapa = 'orcamento')) from a)
);
$$;

revoke all on function senhor_smart_at.painel(date, date, text) from public, anon, authenticated;
