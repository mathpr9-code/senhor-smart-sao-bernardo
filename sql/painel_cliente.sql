-- Painel do cliente Senhor Smart: uma função que devolve todos os agregados do painel em JSON.
-- Nunca expõe nome, telefone ou texto de mensagem. É chamada pela Edge Function `painel-senhor-smart`
-- com service_role, nunca pela anon key.
-- NÃO APLICADO no banco. Revisar e aplicar via migration.

create or replace function senhor_smart.painel_cliente(p_inicio date, p_fim date)
returns jsonb
language sql
stable
security definer
set search_path = senhor_smart, pg_temp
as $$
with conv as (
  select ticket_id,
         (criado_em at time zone 'America/Sao_Paulo') as criado_local,
         coalesce(estagio_max_atingido, estagio) as est,
         perguntou_sobre_iphone,
         modelo_de_interesse,
         dor_declarada
  from conversa_estado
  where (criado_em at time zone 'America/Sao_Paulo')::date between p_inicio and p_fim
),
first_msg as (
  select distinct on (i.ticket_id) i.ticket_id, i.mensagem
  from interacao_log i join conv c using (ticket_id)
  where i.direcao = 'cliente'
  order by i.ticket_id, i.id
),
visita as (
  select * from conv where est in ('PRONTO_PRA_VISITA', 'TRANSFERIDO')
)
select jsonb_build_object(
  'periodo', jsonb_build_object('inicio', p_inicio, 'fim', p_fim),
  'kpis', jsonb_build_object(
    'leads', (select count(*) from conv),
    'visitas', (select count(*) from visita),
    'fora_horario', (select count(*) from conv
                      where extract(isodow from criado_local) = 7
                         or extract(hour from criado_local) < 8
                         or extract(hour from criado_local) >= 19),
    'pediram_iphone', (select count(*) from conv where perguntou_sobre_iphone)
  ),
  'diario', (select coalesce(jsonb_agg(jsonb_build_array(d, n, v) order by d), '[]')
             from (select criado_local::date d, count(*) n,
                          count(*) filter (where est in ('PRONTO_PRA_VISITA', 'TRANSFERIDO')) v
                   from conv group by 1) x),
  'heatmap', (select coalesce(jsonb_agg(jsonb_build_array(dow, h, n)), '[]')
              from (select extract(isodow from criado_local)::int dow,
                           extract(hour from criado_local)::int h, count(*) n
                    from conv group by 1, 2) x),
  'funil', jsonb_build_array(
    jsonb_build_array('Iniciaram conversa', (select count(*) from conv)),
    jsonb_build_array('Engajaram após a abertura', (select count(*) from conv where est <> 'EXPLORANDO')),
    jsonb_build_array('Pediram condições / localização', (select count(*) from conv where est in ('COLETANDO_DADOS', 'PRONTO_PRA_VISITA', 'TRANSFERIDO'))),
    jsonb_build_array('Chegaram à visita', (select count(*) from visita)),
    jsonb_build_array('Transferidos ao vendedor', (select count(*) from conv where est = 'TRANSFERIDO'))
  ),
  'origem', (select jsonb_build_array(
               jsonb_build_array('Anúncio Meta (mensagem pronta)', count(*) filter (where mensagem ilike '%vi o an_ncio%')),
               jsonb_build_array('Contato direto / orgânico', count(*) filter (where mensagem not ilike '%vi o an_ncio%')))
             from first_msg),
  'modelos', (select coalesce(jsonb_agg(jsonb_build_array(m, n) order by n desc), '[]')
              from (select modelo_de_interesse m, count(*) n from conv
                    where modelo_de_interesse is not null and modelo_de_interesse not in ('null', '')
                    group by 1 order by 2 desc limit 8) x),
  'dores', (select coalesce(jsonb_agg(jsonb_build_array(dor_declarada, n) order by n desc), '[]')
            from (select dor_declarada, count(*) n from conv where dor_declarada is not null group by 1) x)
);
$$;

revoke all on function senhor_smart.painel_cliente(date, date) from public, anon, authenticated;

-- Pré-requisito de segurança (hoje o papel anon tem SELECT em todas as tabelas de senhor_smart, sem RLS).
-- Rodar antes de publicar qualquer link para o cliente:
-- alter table senhor_smart.conversa_estado enable row level security;
-- alter table senhor_smart.interacao_log   enable row level security;
-- alter table senhor_smart.atendimento_log enable row level security;
-- alter table senhor_smart.visita_agendada enable row level security;
-- revoke all on all tables in schema senhor_smart from anon, authenticated;
-- (o n8n usa a conexão Postgres direta, que não é afetada por RLS/grants do anon)
