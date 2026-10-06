-- Padrões que reconhecem só a marca do celular (Samsung, iPhone, Motorola, Xiaomi).
-- O preço muda muito dentro da marca, então a máquina registra a marca e continua perguntando o modelo.
-- Só dado: a decisão de perguntar fica na máquina.
alter table senhor_smart_at.modelos add column if not exists so_marca boolean not null default false;
update senhor_smart_at.modelos set so_marca = true
 where categoria = 'celular' and padrao in ('samsung|galaxy', 'iphone', 'motorola|\mmoto\M', 'xiaomi|\mmi\s*[0-9]');

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
                                                    'exibicao', exibicao, 'linha', linha, 'prioridade', prioridade,
                                                    'so_marca', so_marca)
                                 order by prioridade, id) from modelos),
    'servicos', (select jsonb_agg(jsonb_build_object('id', id, 'categoria', categoria, 'nome', nome, 'sintomas', sintomas,
                                                     'prazo', prazo_texto, 'exige_diagnostico', exige_diagnostico,
                                                     'detalhes', detalhes)) from servicos),
    'precos', (select jsonb_agg(jsonb_build_object('servico_id', servico_id, 'linha', linha, 'preco', preco, 'min', preco_min,
                                                   'max', preco_max, 'validado', validado)) from preco_referencia),
    'origem_regra', (select jsonb_agg(jsonb_build_object('prioridade', prioridade, 'campo', campo, 'padrao', padrao,
                                                         'canal', canal, 'campanha', campanha) order by prioridade)
                     from origem_regra),
    'objecoes', (select jsonb_agg(to_jsonb(o) - 'fonte') from objecoes o)
  )
$$;
