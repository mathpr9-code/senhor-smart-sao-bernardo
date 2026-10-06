"""Gera o código SDK do fluxo de TESTE da Sofia (harness), a partir dos mesmos prompts e scripts do fluxo real.

Sem buffer, sem envio ao cliente e sem transferência: o webhook de teste responde com o resultado do turno
(bolhas, conducao, nota interna). Use ticket NEGATIVO: o painel e o resumo do dia ignoram ticket_id <= 0.
"""
import json
import build_ops as B

def J(v):
    return json.dumps(v, ensure_ascii=False)

PG = {"id": "O9soLH536pVD9my1", "name": "Postgres account"}
OR = {"id": "r8UA8KIXE9HGOwuj", "name": "OR Teste"}
op = {o.get("nodeName") or o.get("node", {}).get("name"): o for o in B.lote1 + B.lote2 + B.lote4 if o["type"] in ("updateNodeParameters", "addNode")}
ext = next(o for o in B.lote1 if o.get("path") == "/jsonBody")["value"]
maq = next(o for o in B.lote4 if o.get("nodeName") == "Máquina de Estado")["value"]

def p(nome):
    o = op[nome]
    return o["parameters"] if o["type"] == "updateNodeParameters" else o["node"]["parameters"]

def cond(left, operacao):
    return B.cond(left, operacao)

nodes = {
  "Webhook": ("trigger", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "POST", "path": "teste-senhor-smart", "responseMode": "lastNode", "options": {}}, None, {}),
  "Interpretar Foto": ("node", "n8n-nodes-base.code", 2, {"jsCode": "// Simula a saída do Ler Foto: mande body.foto = {tipo, categoria, marca, modelo, danos, descricao, confianca} para testar foto.\nconst f = $('Webhook').first().json.body?.foto || { tipo: 'nenhuma' };\nreturn [{ json: { ...f, descricao_texto: f.descricao || '' } }];"}, None, {}),
  "Filtra webhook": ("node", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
      {"id": "t-nome", "name": "Nome", "value": "={{ $('Webhook').first().json.body.contact?.name || '' }}", "type": "string"},
      {"id": "t-ticket", "name": "Ticketid", "value": "={{ $('Webhook').first().json.body.ticketId }}", "type": "number"},
      {"id": "t-anuncio", "name": "vemDeAnuncio", "value": "={{ !!$('Webhook').first().json.body.title }}", "type": "boolean"}]}, "options": {}}, None, {}),
  "Mensagem": ("node", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
      {"id": "t-msg", "name": "messagem", "value": "={{ $('Webhook').first().json.body.lastMessage }}", "type": "string"}]}, "options": {}}, None, {}),
  "Carregar Estado + Catálogo": ("node", "n8n-nodes-base.postgres", 2.6, p("Carregar Estado + Catálogo"), {"postgres": PG}, {}),
  "Extrair Intenção": ("node", "n8n-nodes-base.httpRequest", 4.4, {"method": "POST", "url": "https://openrouter.ai/api/v1/chat/completions",
      "authentication": "predefinedCredentialType", "nodeCredentialType": "openRouterApi", "sendBody": True, "specifyBody": "json",
      "jsonBody": ext, "options": {}}, {"openRouterApi": OR}, {}),
  "Carregar Contexto": ("node", "n8n-nodes-base.postgres", 2.6, p("Carregar Contexto"), {"postgres": PG}, {}),
  "Máquina de Estado": ("node", "n8n-nodes-base.httpRequest", 4.4, {**p("Máquina de Estado"), "jsonBody": maq}, None, {}),
  "Dedup OK?": ("if", "n8n-nodes-base.if", 2.3, p("Dedup OK?"), None, {}),
  "Sofia": ("node", "@n8n/n8n-nodes-langchain.agent", 1.7, {**p("Sofia"), "options": {"systemMessage": B.sys_sofia}}, None, {}),
  "Montar Log do Turno": ("node", "n8n-nodes-base.code", 2, p("Montar Log do Turno"), None, {}),
  "Registrar Turno e Métricas": ("node", "n8n-nodes-base.postgres", 2.6, p("Registrar Turno e Métricas"), {"postgres": PG}, {"executeOnce": True}),
  "Pós-processador": ("node", "n8n-nodes-base.code", 2, p("Pós-processador"), None, {}),
  "Atualizar Estado": ("node", "n8n-nodes-base.postgres", 2.6, p("Atualizar Estado"), {"postgres": PG}, {"executeOnce": True}),
  "If": ("if", "n8n-nodes-base.if", 2.3, p("If"), None, {}),
  "Montar Nota Interna": ("node", "n8n-nodes-base.code", 2, p("Montar Nota Interna"), None, {}),
  "Resultado": ("node", "n8n-nodes-base.code", 2, {"jsCode": "// Resultado do turno de teste (o que iria para o cliente e para a equipe)\nconst m = $('Máquina de Estado').first().json;\nconst bolhas = $('Pós-processador').all().map((i) => i.json.resposta_final);\nlet nota = null;\ntry { nota = $('Montar Nota Interna').first().json.nota_interna; } catch (_) {}\nlet leitura = null;\ntry { leitura = JSON.parse($('Extrair Intenção').first().json.choices[0].message.content); } catch (_) {}\nreturn [{ json: { bolhas, transferir: $('Pós-processador').first().json.precisa_transferir, fila: $('Pós-processador').first().json.queueId, nota_interna: nota, leitura, conducao: m.conducao, etapa: m.metricas.etapa, eventos_funil: m.metricas.eventos_funil } }];"}, None, {}),
  "Duplicata": ("node", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
      {"id": "t-dup", "name": "duplicata", "value": True, "type": "boolean"}]}, "options": {}}, None, {}),
}

def decl(nome):
    kind, tipo, ver, params, cred, extra = nodes[nome]
    var = "n_" + "".join(c if c.isalnum() else "_" for c in nome.encode("ascii", "ignore").decode())
    cfg = {"name": nome, "parameters": params, **extra}
    if cred: cfg["credentials"] = cred
    if nome == "Sofia":
        return var, f"const {var} = node({{ type: {J(tipo)}, version: {ver}, config: {{ ...{J(cfg)}, subnodes: {{ model: modelo, memory: memoria }} }} }});"
    fn = {"trigger": "trigger", "node": "node", "if": "ifElse"}[kind]
    if fn == "ifElse":
        return var, f"const {var} = ifElse({{ version: {ver}, config: {J(cfg)} }});"
    return var, f"const {var} = {fn}({{ type: {J(tipo)}, version: {ver}, config: {J(cfg)} }});"

linhas = ["import { workflow, node, trigger, ifElse, languageModel, memory } from '@n8n/workflow-sdk';", ""]
linhas.append("const modelo = languageModel({ type: '@n8n/n8n-nodes-langchain.lmChatOpenRouter', version: 1, config: { name: 'GPT 4.1 mini', parameters: "
              + J(p("GPT 4.1 mini")) + ", credentials: { openRouterApi: " + J(OR) + " } } });")
mem = dict(p("Memória Sofia"))
linhas.append("const memoria = memory({ type: '@n8n/n8n-nodes-langchain.memoryPostgresChat', version: 1.4, config: { name: 'Memória Sofia', parameters: "
              + J(mem) + ", credentials: { postgres: " + J(PG) + " } } });")
V = {}
for nome in nodes:
    var, src = decl(nome)
    V[nome] = var
    linhas.append(src)
v = V
linhas.append(f"""
export default workflow('teste-senhor-smart', 'TESTE Senhor Smart - Sofia (sem envio)')
  .add({v['Webhook']})
  .to({v['Interpretar Foto']})
  .to({v['Filtra webhook']})
  .to({v['Mensagem']})
  .to({v['Carregar Estado + Catálogo']})
  .to({v['Extrair Intenção']})
  .to({v['Carregar Contexto']})
  .to({v['Máquina de Estado']})
  .to({v['Dedup OK?']}
    .onTrue({v['Sofia']}.to({v['Montar Log do Turno']}).to({v['Registrar Turno e Métricas']}).to({v['Pós-processador']}).to({v['Atualizar Estado']})
      .to({v['If']}.onTrue({v['Montar Nota Interna']}.to({v['Resultado']})).onFalse({v['Resultado']})))
    .onFalse({v['Duplicata']}));
""")
print("\n".join(linhas))
