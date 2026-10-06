-- Memória de conversa da Sofia (Postgres Chat Memory do n8n, janela de 12, chave = ticketId).
-- Mesma estrutura que o n8n cria sozinho; criada antes para já nascer com RLS ligado e sem acesso anon.
create table if not exists senhor_smart_at.sofia_memoria (
  id serial primary key,
  session_id varchar(255) not null,
  message jsonb not null
);
create index if not exists sofia_memoria_session_idx on senhor_smart_at.sofia_memoria (session_id, id);
alter table senhor_smart_at.sofia_memoria enable row level security;
revoke all on senhor_smart_at.sofia_memoria from anon, authenticated;
