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

## 3. n8n — fluxo de teste primeiro (núcleo isolado, padrão Lívia)

`Webhook → Filtra → Mensagem → Carregar Estado + Catálogo → Extrair Intenção → Carregar Contexto → Máquina de Estado → Atualizar Estado`
sem buffer, sem envio. Testar com tickets forjados (99xxxxxx) antes de plugar os blocos de narrador, envio e transferência.

Payload do node **Máquina de Estado**:

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

## 4. Fluxos agendados

| fluxo | gatilho | nós |
|---|---|---|
| Follow-up | a cada 30 min, horário comercial | `v1_followup_candidatos()` → Carregar Contexto → HTTP `/followup` → se `enviar`: narrador (lembrete) ou template Meta (reengajar) → `v1_registrar_followup(ticket, tipo)`; no `lembrete_visita`, gravar `estado_novo` com `v1_atualizar_estado` |
| Resumo do dia | seg a sáb, 19:05 | `select senhor_smart_at.v1_resumo_dia() as r` → Code `n8n/resumo_dia.js` → envio para o WhatsApp do Denis |

## 5. Pendências que dependem da loja

1. **Preços reais.** As 43 faixas são estimativa de mercado (`preco_referencia.validado = false`). Trocar pelas da loja.
2. **Fatos a confirmar** (a IA não afirma enquanto `confirmado = false`): avaliação sem custo, cliente aprova antes do conserto,
   a faixa inclui peça e mão de obra, troca de tela/bateria/conector não apaga dados, conserto acompanhado na loja,
   formas de pagamento, prazo padrão, leva e traz. Cada um confirmado vira argumento nas objeções.
3. **Filas do DeskRio** para técnico, vendas e humano (hoje as três apontam para 64000384, a fila do bot antigo).
4. **Mensagens prontas por campanha** no Google Ads (ex.: "Olá! Vim pelo Google e quero um orçamento"), para separar Google de Meta no painel, como a TX faz.
5. **Template Meta** aprovado para o reengajamento de 72h.
6. **Registro de fechamento** pelo vendedor (`registrar_desfecho`: na_loja / os_aberta / fechado com valor / perdido com motivo). Sem isso não há receita no resumo.

## 6. Limitações conhecidas (v1.1)

- Um trabalho por tipo de aparelho na conversa: dois celulares diferentes do mesmo cliente viram um só (o segundo exige humano).
- Um serviço por aparelho: "tela trincada e não carrega" cota a tela; o conector aparece na avaliação.
- O narrador não foi rodado contra o modelo real nesta sessão (sem chave do OpenRouter aqui). Os exemplos do prompt usam conducao real da máquina; a bateria E2E é no fluxo de teste.
