# Zona 2 — Buffer de Mensagens

O cliente raramente manda uma mensagem só: "oi", depois "meu celular caiu", depois "é um A52s". Sem buffer, a Sofia responderia três vezes, fora de contexto. Esta zona junta as mensagens de um mesmo ticket que chegam em rajada e deixa só uma execução seguir com o texto consolidado. Usa Redis como memória compartilhada entre as execuções paralelas.

**Criando Buffer ticket** (Redis push) — empilha a mensagem na lista ticketId:{id}. Áudio entra como [ÁUDIO_DO_CLIENTE: …], foto como [FOTO_DO_CLIENTE: …] + legenda, texto como está. Link cru é ignorado.

**Wait** (18 s) — dá tempo de chegarem as outras mensagens da rajada.

**Puxar Mensagem Buffer Ticket** — lê a lista inteira do ticket.

**Ultima Mensagem é a Ultima Recebida?** — decide a execução vencedora: se a última da lista não é a desta execução, chegou mensagem depois e esta para (**No Operation, do nothing1**).

**Check lock / Lock Existe?** — se outra execução já está processando o ticket, esta desiste (**No Operation, do nothing**).

**Set Lock** — grava lock:ticket:{id} com TTL de 30 s (se algo travar, o lock expira sozinho).

**Apaga Buffer Ticket** — limpa a lista antes de consolidar.

**Consolidar Mensagens** (Code) — junta as mensagens, remove repetidas em sequência e devolve um texto só.

**Mensagem** (Set) — guarda o texto consolidado em messagem, usado por todo o resto do fluxo.
