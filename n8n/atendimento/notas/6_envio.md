# Zona 6 — Envio para DeskRio + Estado + Transferência + Nota Interna

Envia as bolhas ao cliente, salva o estado e, quando a máquina decidiu, transfere o ticket e deixa uma nota interna para a equipe, sem o cliente ver.

**Loop Mensagens** — percorre as bolhas uma a uma. **Enviar resposta da IA** (DeskRio POST /v1/api/ia-messages/send) envia cada uma no número e na conexão do ticket; **Wait entre mensagens** (2 s) dá ritmo de digitação.

**Atualizar Estado** (Postgres) — `v1_atualizar_estado(ticket, estado_novo, agora)` grava o estado que a máquina devolveu. Roda **antes** de soltar o lock, para a próxima mensagem já carregar o estado novo.

**Liberar Lock** — apaga lock:ticket:{id}; o ticket fica livre para o próximo turno.

**If** — lê precisa_transferir do Pós-processador (= conducao.deve_transferir, ou fallback da resposta vazia).

**Transferencia** (DeskRio PUT /v1/api/ticket/update/{ticketId}) — muda a fila para conducao.transferir_para, que a máquina lê das chaves fila_* do banco (`loja_info`): técnico (visita combinada), vendas (quer comprar aparelho) e humano (pediu pessoa, reclamação, status de serviço). Hoje as três apontam para **64000523 (base de teste)**; trocar de fila é um UPDATE no banco, sem mexer no fluxo. Retry 3x e continueRegularOutput: se a DeskRio oscilar, a nota ainda sai.

**Montar Nota Interna** (Code, sem IA) — monta a nota a partir de conducao.resumo_encaminhamento: motivo, cliente, origem (canal e campanha), cada aparelho com modelo, defeito, serviço e valor passado, o que pesa para o cliente e a visita combinada. Evita a equipe perguntar tudo de novo.

**Enviar Nota Interna** (DeskRio /ia-messages/send, messageType comment) — grava a nota no ticket, visível só para a equipe.
