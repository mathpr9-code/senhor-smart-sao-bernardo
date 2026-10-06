-- Senhor Smart · Assistência técnica
-- Schema próprio, separado da operação de venda (senhor_smart).
-- Conhecimento (do cliente) → tabelas de base; estratégia (do sistema) → conversation_strategies;
-- métricas → atendimento + evento_funil + turno_log.

create schema if not exists senhor_smart_at;

-- ============ BASE DE CONHECIMENTO (dado do cliente) ============

create table senhor_smart_at.loja_info (
  chave text primary key,
  valor text,
  confirmado boolean not null default false   -- false = placeholder, a IA não afirma
);

create table senhor_smart_at.horario_funcionamento (
  dia_semana smallint primary key check (dia_semana between 0 and 6),  -- 0 = domingo
  abre time,
  fecha time,
  fechado boolean not null default false
);

create table senhor_smart_at.feriados (
  data date primary key,
  nome text
);

create table senhor_smart_at.categorias (
  id text primary key,                 -- celular, notebook, videogame...
  nome text not null,
  atende boolean not null default true,
  fila_transferencia text               -- fila DeskRio para este tipo
);

-- Modelo citado pelo cliente → marca + linha de preço
create table senhor_smart_at.modelos (
  id serial primary key,
  categoria text not null references senhor_smart_at.categorias(id),
  marca text not null,
  padrao text not null,                 -- regex (case-insensitive) aplicada ao texto normalizado
  exibicao text not null,
  linha text not null,                  -- entrada | intermediario | premium | apple_antigo | apple_medio | apple_recente | padrao
  prioridade int not null default 100   -- menor ganha (padrões específicos antes dos genéricos)
);

create table senhor_smart_at.servicos (
  id text primary key,
  categoria text not null references senhor_smart_at.categorias(id),
  nome text not null,
  sintomas text[] not null default '{}',   -- palavras que o cliente usa
  prazo_texto text,
  exige_diagnostico boolean not null default false,
  observacao text
);

create table senhor_smart_at.preco_referencia (
  id serial primary key,
  servico_id text not null references senhor_smart_at.servicos(id),
  linha text,                           -- null = qualquer linha
  preco_min numeric(10,2) not null,
  preco_max numeric(10,2) not null,
  fonte text not null default 'estimativa_mercado',
  validado boolean not null default false,
  unique (servico_id, linha)
);

-- Origem do lead: mensagem pré-preenchida por campanha, clique de anúncio etc.
create table senhor_smart_at.origem_regra (
  id serial primary key,
  prioridade int not null default 100,
  campo text not null check (campo in ('mensagem', 'anuncio')),
  padrao text not null,                 -- ilike
  canal text not null check (canal in ('google', 'meta', 'organico', 'indicacao', 'site', 'retorno')),
  campanha text
);

-- ============ ESTRATÉGIA (do sistema) ============

create table senhor_smart_at.conversation_strategies (
  id serial primary key,
  nome text unique not null,
  prioridade int not null,
  -- condições (null = não importa)
  quando_intent text[],
  quando_sentimento text[],
  quando_etapa text[],
  quando_primeira boolean,
  quando_tem_categoria boolean,
  quando_tem_modelo boolean,
  quando_tem_defeito boolean,
  quando_tem_preco boolean,
  quando_categoria_atendida boolean,
  -- saída
  objetivo text not null,
  acolher_antes boolean not null default false,
  pode_cotar boolean not null default false,
  proximo_passo text,
  transferir_fila text,                 -- 'humano', 'vendas', 'tecnico' ou null
  ativo boolean not null default true
);

-- ============ ESTADO E MÉTRICAS ============

create table senhor_smart_at.atendimento (
  ticket_id bigint primary key,
  telefone text,
  nome_whatsapp text,
  nome_cliente text,                    -- primeiro nome informado pelo próprio cliente
  canal text not null default 'organico',
  campanha text,
  primeira_msg_em timestamptz not null default now(),
  primeira_resposta_em timestamptz,
  fora_horario boolean not null default false,
  categoria text,
  marca text,
  modelo text,
  linha text,
  defeito text,
  servico_id text,
  faixa_min numeric(10,2),
  faixa_max numeric(10,2),
  preco_validado boolean,
  etapa text not null default 'novo',
  etapa_max text not null default 'novo',
  orcamento_enviado_em timestamptz,
  agendado_em timestamptz,
  visita_combinada text,                -- "amanhã de manhã", "sábado"
  motivo_perda text,
  valor_fechado numeric(10,2),
  fechado_em timestamptz,
  transferido boolean not null default false,
  fila_transferencia text,
  motivo_transferencia text,
  pediu_humano boolean not null default false,
  reclamacao boolean not null default false,
  pediu_preco boolean not null default false,
  objecao_preco boolean not null default false,
  turnos int not null default 0,
  fotos int not null default 0,
  audios int not null default 0,
  followups_enviados int not null default 0,
  recuperado_por_followup boolean not null default false,
  sentimento_final text,
  custo_usd numeric(12,6) not null default 0,
  tokens int not null default 0,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table senhor_smart_at.conversa_estado (
  ticket_id bigint primary key references senhor_smart_at.atendimento(ticket_id) on delete cascade,
  abertura_feita boolean not null default false,
  dados_perguntados text[] not null default '{}',   -- equipamento, modelo, defeito, nome… (não repetir)
  ultima_estrategia text,
  ultimo_objetivo text,
  resumo text,
  ultima_msg_cliente_em timestamptz,
  ultima_msg_ia_em timestamptz,
  atualizado_em timestamptz not null default now()
);

create table senhor_smart_at.evento_funil (
  id bigserial primary key,
  ticket_id bigint not null references senhor_smart_at.atendimento(ticket_id) on delete cascade,
  etapa text not null,
  origem text not null default 'ia',    -- ia | vendedor | sistema
  dados jsonb,
  em timestamptz not null default now()
);
create index on senhor_smart_at.evento_funil (ticket_id, em);

create table senhor_smart_at.turno_log (
  id bigserial primary key,
  ticket_id bigint not null,
  entrada text,
  saida text,
  intent text,
  estrategia text,
  sentimento text,
  tinha_foto boolean not null default false,
  latencia_ms int,
  modelo_ia text,
  tokens int,
  custo_usd numeric(12,6),
  criado_em timestamptz not null default now()
);
create index on senhor_smart_at.turno_log (ticket_id, criado_em);

create table senhor_smart_at.followup (
  id bigserial primary key,
  ticket_id bigint not null references senhor_smart_at.atendimento(ticket_id) on delete cascade,
  tipo text not null,                   -- 24h | 72h
  agendado_para timestamptz not null,
  status text not null default 'pendente' check (status in ('pendente', 'enviado', 'respondido', 'cancelado')),
  enviado_em timestamptz,
  respondido_em timestamptz,
  unique (ticket_id, tipo)
);
create index on senhor_smart_at.followup (status, agendado_para);

create index on senhor_smart_at.atendimento (primeira_msg_em);

-- Ordem das etapas do funil (para etapa_max e para o painel)
create or replace function senhor_smart_at.etapa_rank(p text) returns int
language sql immutable as $$
  select case p
    when 'novo' then 0 when 'triagem' then 1 when 'diagnostico' then 2 when 'orcamento' then 3
    when 'agendado' then 4 when 'na_loja' then 5 when 'os_aberta' then 6 when 'fechado' then 7
    else -1 end
$$;

-- ============ SEGURANÇA ============
-- Só o backend (n8n via Postgres e a Edge Function via service_role) acessa.
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'senhor_smart_at' loop
    execute format('alter table senhor_smart_at.%I enable row level security', t.tablename);
  end loop;
end $$;
revoke all on all tables in schema senhor_smart_at from anon, authenticated;
revoke all on schema senhor_smart_at from anon, authenticated;
alter default privileges in schema senhor_smart_at revoke all on tables from anon, authenticated;
