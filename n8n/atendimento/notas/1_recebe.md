# Zona 1 — Recebe Mensagens + Tratamento

Porta de entrada do fluxo. Toda mensagem que chega no WhatsApp da Senhor Smart passa por aqui antes de qualquer decisão. A zona faz três coisas: (1) recebe o webhook da DeskRio, (2) desvia os erros conhecidos da plataforma, e (3) transforma texto, áudio ou foto em um texto único, porque tudo daqui para frente (extrator, máquina, Sofia) só entende texto.

**Webhook** (POST `/senhorsmartnovo`) — a DeskRio dispara um POST a cada mensagem do cliente. O body traz ticketId, connectionId, contact (name e number), lastMessage, lastMediaMessage, lastMessageDate e mediaType (chat, audio, image). Em anúncio click-to-WhatsApp vêm também title e ctwaclid.

**Tem mensagem de erro ou null?** — a DeskRio às vezes manda "Erro ao carregar mensagem", "null" ou "Essa mensagem não pode ser exibida". Nesses casos o fluxo espera (**Wait1**, 3 min) e confere de novo (**If1**). Se o erro continuar, **Enviar resposta de Fallback** pede para o cliente reenviar.

**É texto? / Audio Permite / Permite Image?** — leem o mediaType e escolhem o caminho.

**Texto** — caminho de texto puro, segue direto para o Filtra webhook.

**Áudio:** **Code in JavaScript2** escolhe a URL do áudio → **Tem áudio?** → **Baixando Media** → **Code in JavaScript** (troca .oga por .ogg, exigido pela Azure) → **Transcrever áudio - Azure1** (gpt-4o-transcribe). Falhou em qualquer etapa: **Fallback audio** pede reenvio.

**Foto:** **Code in JavaScript1** escolhe a URL da imagem → **Tem imagem?** → **Ler Foto** (OpenRouter, GPT-5.4-mini com visão, JSON estrito; prompt em `prompts/visao.md`) descreve só o que é visível: tipo (aparelho, documento, outro), categoria, marca, modelo, danos (tela trincada, bateria estufada…), descrição e confiança. Não diagnostica e não dá preço. → **Interpretar Foto** (Code) monta o texto curto que entra no buffer como [FOTO_DO_CLIENTE: …] e guarda os campos estruturados para a Máquina de Estado. Sem URL: **Fallback imagem** pede reenvio.

**Filtra webhook** — ponto de encontro dos três caminhos. Monta o payload padrão do buffer: message, Nome (nome do WhatsApp, que pode vir emoji; quem decide se serve é a máquina), Ticketid, Audiomessage, telefone, imagem (texto da foto), legenda e vemDeAnuncio.
