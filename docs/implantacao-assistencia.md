# Senhor Smart · Assistência técnica — implantação

Padrão: Framework Universal de Agentes v1.2 + máquina de estado no Droplet (mesmo desenho da `livia-estado`).
Banco = dado. Máquina = decisão. LLM = fala.

```
DeskRio ──webhook──▶ n8n (borda fina)
   Filtra webhook → buffer/lock (Redis, já existe) → mídia (áudio/foto) → Mensagem
   Carregar Estado + Catálogo   SQL  v1_carregar_estado(ticket), v1_catalogo_extrator()
   Extrair Intenção             GPT-5.4-mini, reasoning none, json_schema strict
   Ler Foto (se imagem)         GPT-5.4-mini visão, json_schema strict
   Carregar Contexto            SQL  v1_carregar_contexto(agora)   ← nunca lê o estado
   Máquina de Estado            HTTP POST https://senhor-smart-estado.mpstudio.ia.br/processar
   Duplicada?                   conducao.duplicata → solta o lock e para
   Sofia (narrador)             GPT-4.1-mini, lê só a conducao limpa
   Pós-processador              só bolhas (|||) e limpeza mecânica
   Envio (loop + wait)          DeskRio /ia-messages/send
   Atualizar Estado             SQL  v1_atualizar_estado(ticket, estado_novo, agora)
   Registrar Turno              SQL  v1_registrar_turno({metricas, turno, telefone, agora})
   If deve_transferir → Transferência (queueId = conducao.transferir_para) → Nota interna
```

## 1. Banco (já aplicado no Supabase, schema `senhor_smart_at`)

| arquivo | conteúdo |
|---|---|
| `sql/at/01_schema.sql` | tabelas (RLS ligado, anon sem acesso) |
| `sql/at/02_seed.sql` | loja, horário, 26 serviços, 43 faixas de preço (estimativa), 40 padrões de modelo, origem |
| `sql/at/04_painel.sql` | `painel(inicio, fim)` para o dashboard (só agrega) |
| `sql/at/05_v1_leitura_escrita.sql` | funções v1 de leitura e escrita da máquina |
| `sql/at/06_objecoes_e_detalhes.sql` | biblioteca de 8 objeções como dado; detalhes técnicos por serviço |
| `sql/at/07_resumo_dia_followup.sql` | `v1_resumo_dia()`, candidatos de follow-up com lembrete de visita |
| `sql/at/08_preco_fixo_condicoes.sql` | preço fixo, entrada R$ 240 + até 18x no boleto, fatos confirmados, filas 64000523 |
| `sql/at/09_memoria_sofia.sql` | tabela da memória da Sofia (Postgres Chat Memory), com RLS |

`sql/at/03_funcoes.sql` são as funções de decisão em SQL da primeira tentativa (`montar_contexto`, `registrar_turno`, …).
**Não usar.** Ficaram no banco sem uso; remover quando autorizado:

```sql
drop function if exists senhor_smart_at.montar_contexto(jsonb), senhor_smart_at.registrar_turno(jsonb),
  senhor_smart_at.identificar_modelo(text, text), senhor_smart_at.identificar_servico(text, text, text),
  senhor_smart_at.cotar(text, text), senhor_smart_at.detectar_origem(text, text),
  senhor_smart_at.situacao_horario(timestamptz), senhor_smart_at.followups_devidos(int),
  senhor_smart_at.marcar_followup_enviado(bigint);
-- dados de teste (tickets negativos)
delete from senhor_smart_at.turno_log where ticket_id < 0;
delete from senhor_smart_at.conversa_estado where ticket_id < 0;
delete from senhor_smart_at.atendimento where ticket_id < 0;
```

## 2. Máquina no Droplet (receita "subir uma IA nova sem derrubar as outras")

```bash
ssh -i ~/.ssh/livia_droplet root@192.241.144.247
free -h        # precisa de ~100 MB livres; abaixo de 200 MB, pare e faça resize
docker builder prune -f && docker image prune -f

# DNS: registro A  senhor-smart-estado.mpstudio.ia.br → 192.241.144.247
mkdir -p /opt/senhor-smart-estado
# no PC: scp -i ~/.ssh/livia_droplet senhor-smart-estado.zip root@192.241.144.247:/opt/senhor-smart-estado/
cd /opt/senhor-smart-estado && unzip -o senhor-smart-estado.zip
docker compose build maquina && docker compose up -d maquina
docker compose logs --tail 30 maquina
docker ps --format '{{.Names}} | {{.Status}}'      # livia-maquina segue Up

# Caddy: backup e acrescentar o bloco (nunca apagar os outros, nunca restart, nunca compose down nessa pasta)
cp /opt/agnes-estado/Caddyfile /opt/agnes-estado/Caddyfile.bak
cat >> /opt/agnes-estado/Caddyfile <<'EOF'

senhor-smart-estado.mpstudio.ia.br {
    reverse_proxy senhor-smart-maquina:8000
}
EOF
docker exec agnes-estado-caddy-1 caddy validate --config /etc/caddy/Caddyfile
docker exec agnes-estado-caddy-1 caddy reload  --config /etc/caddy/Caddyfile

curl -s https://senhor-smart-estado.mpstudio.ia.br/health
curl -s https://livia-estado.mpstudio.ia.br/health     # a Lívia continua de pé
```

O pacote: `senhor-smart-estado/` (`app.py`, `maquina.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`).
A máquina não acessa banco nem LLM, então não tem `.env`. Usa `mem_limit: 128m`, log rotacionado e healthcheck.
Toda mudança na máquina: `pytest`, reempacotar, `docker compose build maquina && docker compose up -d maquina`
(o `COPY` embute o código na imagem; trocar o arquivo no disco não basta).

## 3. n8n — fluxo "Senhor smart - novo" (dLwpCiaonSWavJLj)

O Python do Code node não roda nesta instância (sem task runner externo), então a máquina fica no droplet e o n8n chama por HTTP.

Religado do buffer em diante (rascunho; a versão publicada só muda com **Publish**):

```
Mensagem → Carregar Estado + Catálogo → Extrair Intenção → Carregar Contexto → Máquina de Estado
  ├─ erro da máquina → Liberar próxima mensagem do cliente (solta o lock)
  └─ Dedup OK? ─ duplicata → Liberar próxima mensagem do cliente
               └─ Sofia (+ GPT 4.1 mini, Memória Sofia) → Montar Log do Turno → Registrar Turno e Métricas
                  → Pós-processador → Loop Mensagens → Enviar resposta da IA (já existia)
                  → (fim do loop) Atualizar Estado → Liberar Lock → If → Transferencia → Montar Nota Interna → Enviar Nota Interna
```

- O código de cada nó está em `n8n/atendimento/` e as operações saem de `n8n/atendimento/build_ops.py`
  (lê `prompts/*.md` e os `.js`). Mudou prompt ou script: regerar e aplicar, nunca editar só no n8n.
- `Registrar Turno e Métricas` substitui os dois logs antigos (`log_interacao` e `upsert_atendimento_log`):
  uma chamada a `v1_registrar_turno` grava `atendimento`, `evento_funil` e `turno_log`.
- O estado é gravado **antes** de soltar o lock, para a próxima mensagem já ler o estado novo.
- Transferência e nota interna usam `conducao.transferir_para` (64000523 na base de teste). A nota sai de
  `conducao.resumo_encaminhamento`, sem IA.
- Rollback: restaurar a versão `339bd8c3-1b5e-4ddb-a605-2bc77aa5bdbc` no histórico do fluxo.
- O começo do fluxo também foi atualizado: saiu o caminho de documento do bot de vendas (RG/CNH → Storage) e a foto
  passa por **Ler Foto** (`prompts/visao.md`, GPT-5.4-mini, JSON estrito) → **Interpretar Foto**. As notas de cada zona
  seguem o padrão Lívia/Nexfar e saem de `n8n/atendimento/notas/*.md`.
- Cuidado ao gerar expressão: `}}` dentro de `={{ … }}` fecha a expressão e o n8n acusa "invalid syntax".
  O `build_ops.py` separa as chaves do schema e barra qualquer expressão com `{{`/`}}` no meio.

### Fluxo de teste: "TESTE Senhor Smart - Sofia (sem envio)" (y2nXDUShrwLeZ8YJ)

Mesmo núcleo do fluxo real, gerado por `n8n/atendimento/build_teste.py`, **sem buffer, sem envio e sem transferência**
(tickets forjados dão 403 na DeskRio). O webhook responde com bolhas, transferir, fila, nota interna, leitura do
extrator, conducao, etapa e eventos do funil. Use **ticketId negativo** (painel e resumo do dia ignoram ticket ≤ 0) e
mude `lastMessageDate` a cada turno.

```json
POST /webhook-test/teste-senhor-smart
{ "ticketId": -5001, "lastMessage": "meu A52s caiu e a tela não acende", "lastMessageDate": "1001",
  "contact": { "name": "😎", "number": "5511900000000" } }
```

Payload do node **Máquina de Estado** (o mesmo de `n8n/atendimento/expr_maquina.js`):

```json
{
  "ticket_id": "={{ $('Filtra webhook').first().json.Ticketid }}",
  "estado": "={{ $('Carregar Estado + Catálogo').first().json.estado }}",
  "leitura": "={{ JSON.parse($('Extrair Intenção').first().json.choices[0].message.content) }}",
  "foto": "={{ $('Ler Foto').isExecuted && $('Ler Foto').first().json.tipo === 'aparelho' ? $('Ler Foto').first().json : null }}",
  "contexto_dados": "={{ $('Carregar Contexto').first().json.contexto }}",
  "agora": "={{ $now.setZone('America/Sao_Paulo').toISO() }}",
  "nome_whatsapp": "={{ $('Webhook').first().json.body.contact.name }}",
  "mensagem_texto": "={{ $('Webhook').first().json.body.lastMessage }}",
  "mensagem_data": "={{ $('Webhook').first().json.body.lastMessageDate }}",
  "anuncio": "={{ $('Filtra webhook').first().json.vemDeAnuncio ? ($('Webhook').first().json.body.title || 'Anúncio Meta') : null }}",
  "primeira_mensagem": "={{ $('Mensagem').first().json.messagem }}"
}
```

Payload do **Registrar Turno**: `{ metricas: <saída da máquina>.metricas, telefone, nome_whatsapp, agora, turno: { entrada, saida, latencia_ms, modelo_ia, tokens, custo_usd } }`.

**Nota interna** pós-transferência (mesmo padrão da Lívia, `messageType: "comment"`): montada em Code node a partir de
`conducao.resumo_encaminhamento` (cliente, origem, impacto, aparelhos com modelo/defeito/serviço/faixa, visita). Sem LLM.
É o que evita a equipe ter que perguntar tudo de novo ao cliente.

## 4. Painel ao vivo e resumo do dia

| fluxo n8n | o que faz |
|---|---|
| **Painel Senhor Smart (link ao vivo)** (ICmnX89COToBjGBg, ativo) | `GET /webhook/painel-senhor-smart?t=<token>&dias=7\|30\|90` → `senhor_smart_at.painel()` → página HTML (`n8n/painel/montar_painel.js`). `&teste=1` inclui as conversas de teste. O token fica só no nó **Ler filtros** (não vai para o git); para trocar, edite ali. Só números agregados: sem nome, telefone ou conversa. |
| **Resumo do dia Senhor Smart (WhatsApp)** (JevxKDCarr0gVgdo) | seg a sáb 19:05 (America/Sao_Paulo) → `v1_resumo_dia()` → `n8n/resumo_dia.js` → DeskRio. Preencher **DESTINO** e **CONEXAO** (connectionId) no nó **Config** e ativar. "Testar agora" inclui as conversas de teste. |

`sql/at/11_painel_resumo_teste.sql`: `painel(…, p_incluir_teste)` e `v1_resumo_dia(dia, p_incluir_teste)`; as assinaturas antigas continuam e chamam com `false`.

## 4b. Fluxos agendados (pendentes)

| fluxo | gatilho | nós |
|---|---|---|
| Follow-up | a cada 30 min, horário comercial | `v1_followup_candidatos()` → Carregar Contexto → HTTP `/followup` → se `enviar`: narrador (lembrete) ou template Meta (reengajar) → `v1_registrar_followup(ticket, tipo)`; no `lembrete_visita`, gravar `estado_novo` com `v1_atualizar_estado` |
| Resumo do dia | seg a sáb, 19:05 | `select senhor_smart_at.v1_resumo_dia() as r` → Code `n8n/resumo_dia.js` → envio para o WhatsApp do Denis |

## 5. Pendências que dependem da loja

1. **Preços reais.** O preço é fixo (`preco_referencia.preco`), mas os valores ainda são estimativa de teste. Trocar pelos da loja.
2. **Fatos ainda a confirmar** (a IA não afirma enquanto `confirmado = false`): o valor inclui peça e mão de obra,
   troca de tela/bateria/conector não apaga dados, conserto acompanhado na loja, formas de pagamento além do boleto,
   prazo padrão, leva e traz. Já confirmados: avaliação sem custo (no horário da loja), aprovação antes do conserto,
   entrada R$ 240 + até 18x no boleto.
3. **Filas do DeskRio**: técnico, vendas e humano apontam para 64000523 (base de teste). Separar quando for para produção.
4. **Mensagens prontas por campanha** no Google Ads (ex.: "Olá! Vim pelo Google e quero um orçamento"), para separar Google de Meta no painel, como a TX faz.
5. **Template Meta** aprovado para o reengajamento de 72h.
6. **Registro de fechamento** pelo vendedor (`registrar_desfecho`: na_loja / os_aberta / fechado com valor / perdido com motivo). Sem isso não há receita no resumo.

## 6. Limitações conhecidas (v1.2)

- Um trabalho por tipo de aparelho na conversa: dois celulares diferentes do mesmo cliente viram um só (o segundo exige humano).
- Um serviço por aparelho: "tela trincada e não carrega" cota a tela; o conector aparece na avaliação.
- O narrador não foi rodado contra o modelo real nesta sessão (sem chave do OpenRouter aqui). Os exemplos do prompt usam conducao real da máquina; a bateria E2E é no fluxo de teste.
- Foto: os campos estruturados (categoria, marca, modelo, danos) só chegam à máquina quando a execução vencedora do
  buffer é a da própria foto; nas outras, a foto entra como texto [FOTO_DO_CLIENTE: …] e o extrator lê.
- Tokens e custo no `turno_log` são só do extrator; o AI Agent do n8n não expõe o uso do narrador.
