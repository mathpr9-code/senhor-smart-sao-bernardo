"""
Testes da maquina da Senhor Smart. Fixture = dados reais do schema senhor_smart_at.
Cada bug ou risco conhecido vira um teste (padrao livia-estado).
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from maquina import decidir_followup, processar, resolver_modelo

CTX = json.loads((Path(__file__).parent / "fixtures" / "contexto_dados.json").read_text())
TERCA_10H = "2026-10-06T10:00:00-03:00"
DOMINGO_22H = "2026-10-04T22:00:00-03:00"


def turno(leitura, estado=None, agora=TERCA_10H, **extra):
    extra.setdefault("nome_whatsapp", "Michele Souza")
    return processar({"ticket_id": 1, "estado": estado, "leitura": leitura, "contexto_dados": CTX,
                      "agora": agora, **extra})


def conversa(*leituras, agora=TERCA_10H):
    estado, saidas = None, []
    for lt in leituras:
        r = turno(lt, estado, agora=agora)
        estado = r["estado_novo"]
        saidas.append(r)
    return saidas


def eq(**kw):
    base = {"categoria": None, "marca": None, "modelo": None, "defeito": None, "servico_sugerido": None}
    return {**base, **kw}


# --- Resolvedor -----------------------------------------------------------------

@pytest.mark.parametrize("texto,cat,linha,modelo", [
    ("Samsung Galaxy A52s 5G", "celular", "intermediario", "Galaxy A52S"),
    ("meu a15", "celular", "entrada", "Galaxy A15"),
    ("iphone 13 pro max", "celular", "apple_medio", "iPhone 13"),
    ("iPhone XR", "celular", "apple_antigo", "iPhone XR"),
    ("moto g54", "celular", "intermediario", "Moto G54"),
    ("PS5", "videogame", "premium", "PlayStation 5"),
    ("controle do ps5", "videogame", "padrao", "Controle DualSense"),
    ("notebook dell inspiron", "notebook", "padrao", "Dell"),
    ("MacBook Air", "notebook", "premium", "MacBook"),
])
def test_resolver_modelo(texto, cat, linha, modelo):
    r = resolver_modelo(CTX, texto, None)
    assert (r["categoria"], r["linha"], r["modelo"]) == (cat, linha, modelo)


def test_resolver_modelo_sem_evidencia_nao_chuta():
    assert resolver_modelo(CTX, "meu celular", None) is None


# --- O caso que perdemos para a TX: Galaxy A52s, caiu, tela nao acende ------------

def test_caso_michele_a52s_cota_no_segundo_turno():
    t1, t2 = conversa(
        {"intencao": "saudacao", "equipamentos": [eq(categoria="celular")], "sentimento": "neutro"},
        {"intencao": "pedir_orcamento", "perguntas": ["preco"], "equipamentos": [eq(
            categoria="celular", marca="Samsung", modelo="Galaxy A52s 5G",
            defeito="caiu e a tela nao acende mais, mas continua funcionando", servico_sugerido="cel_tela")]},
    )
    c1 = t1["conducao"]
    assert c1["saudar"] and c1["apresentar_ia"] == "Sofia"
    assert c1["periodo"] == "bom_dia" and c1["usar_nome"] == "Michele"
    assert c1["coletar"]["dado"] == "defeito"
    c2 = t2["conducao"]
    assert c2["movimento"] == "recommend_next" and c2["objetivo"] == "orcamento"
    assert c2["orientacao"]["preco"] == 650
    assert c2["orientacao"]["detalhes"]["pode_ser"] == ["tela", "placa"]
    assert c2["orientacao"]["condicao_pagamento"] == {"entrada": 240.0, "parcelas_max": 18, "meio": "boleto"}
    assert "sem custo" in c2["orientacao"]["avaliacao_sem_custo"]
    assert c2["convidar_visita"] and "endereco" in c2["visita"]
    assert not c2["saudar"]
    assert t2["metricas"]["etapa"] == "orcamento"
    assert t2["metricas"]["eventos_funil"] == ["diagnostico", "orcamento"]


def test_cliente_pede_preco_quatro_vezes_nao_fica_preso():
    """Bug real da Sofia (ticket 67555740): insistiu na mesma pergunta ate o cliente desistir."""
    pedido = {"intencao": "pedir_orcamento", "perguntas": ["preco"],
              "equipamentos": [eq(categoria="celular", defeito="tela quebrada")]}
    saidas = conversa(pedido, pedido, pedido)
    dados = [s["conducao"]["coletar"]["dado"] if s["conducao"]["coletar"] else s["conducao"]["objetivo"]
             for s in saidas]
    assert dados[0] == "modelo" and dados[1] == "modelo"
    assert dados[2] == "avaliacao"            # desistiu de perguntar o modelo e orientou mesmo assim
    assert saidas[1]["conducao"]["coletar"]["re_perguntando"] is True


def test_pergunta_direta_e_respondida_antes_de_conduzir():
    """Bug real (ticket 67568313): perguntou o endereco e recebeu 'como voce se chama?'."""
    c = turno({"intencao": "perguntar", "perguntas": ["endereco"], "equipamentos": []})["conducao"]
    assert c["responder"][0]["pergunta"] == "endereco"
    assert "João Firmino" in c["responder"][0]["dado"]
    assert c["coletar"]["dado"] == "equipamento"


def test_endereco_nao_e_repetido_no_convite_de_visita():
    t1, t2 = conversa(
        {"intencao": "perguntar", "perguntas": ["endereco"], "equipamentos": []},
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="moto g54", defeito="bateria descarrega rapido")]},
    )
    assert "endereco" not in t2["conducao"]["visita"]


def test_fato_nao_confirmado_nao_e_afirmado():
    c = turno({"intencao": "perguntar", "perguntas": ["pagamento"], "equipamentos": []})["conducao"]
    assert c["responder"][0]["sem_informacao"] is True
    assert "formas_pagamento" in c["nao_afirmar"]


# --- Multi-equipamento e categorias ---------------------------------------------

def test_dois_equipamentos_no_mesmo_turno_nenhum_some():
    r = turno({"intencao": "pedir_orcamento", "equipamentos": [
        eq(categoria="celular", modelo="iphone 11", defeito="bateria estufada"),
        eq(categoria="videogame", modelo="ps4", defeito="sem imagem na tv, hdmi"),
    ]})
    trabalhos = r["estado_novo"]["trabalhos"]
    assert {t["categoria"] for t in trabalhos} == {"celular", "videogame"}
    assert r["conducao"]["orientacao"]["equipamento"] == "Celular"
    assert r["conducao"]["proximo_equipamento"]["equipamento"] == "Videogame"
    assert r["conducao"]["convidar_visita"] is False   # convida so quando o ultimo for orientado


def test_equipamento_nao_atendido_avisa_uma_vez():
    t1, t2 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="tv", defeito="nao liga")]},
        {"intencao": "outro", "equipamentos": []},
    )
    assert t1["conducao"]["nao_atende"]["equipamentos"] == ["Televisão"]
    assert "Notebook" in t1["conducao"]["nao_atende"]["atendemos"]
    assert t2["conducao"]["nao_atende"] is None


def test_notebook_dispensa_modelo():
    c = turno({"intencao": "pedir_orcamento",
               "equipamentos": [eq(categoria="notebook", defeito="teclado com teclas falhando")]})["conducao"]
    assert c["orientacao"]["preco"] == 450


def test_servico_que_exige_avaliacao_nao_recebe_preco():
    c = turno({"intencao": "pedir_orcamento",
               "equipamentos": [eq(categoria="celular", modelo="a15", defeito="caiu na agua e nao liga")]})["conducao"]
    assert c["objetivo"] == "avaliacao" and c["orientacao"]["preco"] is None


def test_empate_entre_servicos_de_avaliacao_nao_pergunta_ao_cliente():
    c = turno({"intencao": "pedir_orcamento",
               "equipamentos": [eq(categoria="celular", modelo="iphone 12", defeito="caiu na piscina e nao liga")]})["conducao"]
    assert c["objetivo"] == "avaliacao" and c["coletar"] is None
    assert "Limpeza química (contato com água)" in c["orientacao"]["possibilidades"]
    assert "nao colocar para carregar" in c["orientacao"]["detalhes"]["cuidados"]
    assert "pode_ser" not in c["orientacao"]["detalhes"]


def test_sintoma_casa_palavra_inteira_nao_pedaco():
    r = turno({"intencao": "pedir_orcamento", "equipamentos": [
        eq(categoria="celular", modelo="a15", defeito="quero marcar pra trocar a tela")]})
    assert r["estado_novo"]["trabalhos"][0]["servico_id"] == "cel_tela"   # 'mar' (agua) nao casou em 'marcar'


def test_sintomas_empatados_viram_esclarecimento():
    c = turno({"intencao": "pedir_orcamento",
               "equipamentos": [eq(categoria="notebook", defeito="esta lento demais")]})["conducao"]
    assert c["coletar"]["dado"] == "servico"
    assert set(c["coletar"]["opcoes"]) == {"Upgrade para SSD (com peça)", "Formatação com backup"}


def test_extrator_desempata_quando_sintoma_concorda():
    c = turno({"intencao": "pedir_orcamento", "equipamentos": [
        eq(categoria="notebook", defeito="esta lento demais", servico_sugerido="nb_ssd")]})["conducao"]
    assert c["orientacao"]["servico"] == "Upgrade para SSD (com peça)"


def test_extrator_nao_sobrescreve_sintoma_deterministico():
    """Framework 5.2.3: evidencia deterministica vence a sugestao do LLM."""
    r = turno({"intencao": "pedir_orcamento", "equipamentos": [
        eq(categoria="celular", modelo="a52", defeito="a bateria esta estufada", servico_sugerido="cel_tela")]})
    assert r["estado_novo"]["trabalhos"][0]["servico_id"] == "cel_bateria"


def test_foto_completa_modelo_e_defeito():
    r = turno({"intencao": "informar", "equipamentos": []},
              foto={"categoria": "celular", "marca": "Samsung", "modelo": "Galaxy A32",
                    "danos": ["tela trincada"], "descricao": "Celular com a tela trincada no canto"})
    c = r["conducao"]
    assert c["orientacao"]["modelo"] == "Galaxy A32"
    assert c["orientacao"]["preco"] == 650
    assert r["metricas"]["foto"] is True


def test_cliente_corrige_modelo_depois_do_orcamento_recota():
    t1, t2 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="a15", defeito="tela quebrada")]},
        {"intencao": "informar", "equipamentos": [eq(categoria="celular", modelo="iphone 14")]},
    )
    assert t1["conducao"]["orientacao"]["preco"] == 350
    assert t2["conducao"]["orientacao"]["preco"] == 2400


# --- Conducao: visita, objecao, despedida, transferencias -----------------------

def test_visita_combinada_transfere_com_resumo():
    t1, t2 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="a52s", defeito="tela nao acende")]},
        {"intencao": "confirmar_visita", "nome_informado": "Michele Souza", "visita_texto": "amanhã de manhã"},
    )
    c = t2["conducao"]
    assert c["movimento"] == "confirm" and c["usar_nome"] == "Michele"
    assert c["deve_transferir"] and c["transferir_para"] == "64000523"
    assert c["resumo_encaminhamento"]["equipamentos"][0]["modelo"] == "Galaxy A52S"
    assert t2["metricas"]["etapa"] == "agendado" and t2["metricas"]["visita_texto"] == "amanhã de manhã"


def test_objecao_de_preco_acolhe_sem_insistir():
    t1, t2, t3 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="g54", defeito="bateria descarrega")]},
        {"intencao": "objecao_preco", "sentimento": "frustrado"},
        {"intencao": "objecao_preco"},
    )
    assert t2["conducao"]["movimento"] == "explain" and t2["conducao"]["acolher"]
    assert t2["conducao"]["objecao"]["primeira_vez"] is True
    assert t2["conducao"]["objecao"]["orcamento"]["preco"] == 280
    chaves = {a["chave"] for a in t2["conducao"]["objecao"]["argumentos"]}
    assert "faixa_inclui_peca_e_mao_de_obra" not in chaves     # ainda nao confirmado: nunca vira argumento
    assert t3["conducao"]["objecao"]["primeira_vez"] is False
    assert t3["conducao"]["objecao"]["proximo_passo"] == "deixar_porta_aberta"
    assert t3["conducao"]["convidar_visita"] is False


def test_despedida_encerra_sem_empurrar_visita():
    t1, t2 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="g54", defeito="bateria descarrega")]},
        {"intencao": "despedida", "encerrar_conversa": True},
    )
    c = t2["conducao"]
    assert c["movimento"] == "close" and c["deve_transferir"] is False
    assert c["visita"] is None and c["porta_aberta"] is True


@pytest.mark.parametrize("intencao,fila", [
    ("reclamacao", "humano"), ("status_servico", "humano"), ("pediu_humano", "humano"), ("comprar_aparelho", "vendas"),
])
def test_fora_do_contrato_da_ia_transfere(intencao, fila):
    c = turno({"intencao": intencao})["conducao"]
    assert c["movimento"] == "transfer" and c["fila"] == fila and c["deve_transferir"]


def test_saudacao_so_uma_vez():
    t1, t2 = conversa({"intencao": "saudacao"}, {"intencao": "saudacao"})
    assert t1["conducao"]["saudar"] is True and t2["conducao"]["saudar"] is False


def test_nome_so_em_confirmacao_e_despedida():
    t1, t2 = conversa(
        {"intencao": "informar", "nome_informado": "Jossemar", "equipamentos": [eq(categoria="celular")]},
        {"intencao": "informar", "equipamentos": [eq(categoria="celular", defeito="nao carrega")]},
    )
    assert t1["conducao"]["usar_nome"] == "Jossemar" and t1["conducao"]["nome_recem_informado"]
    assert t2["conducao"]["usar_nome"] is None
    assert t2["estado_novo"]["cliente"]["nome"] == "Jossemar"


# --- Metricas, origem, horario, duplicata ---------------------------------------

def test_origem_google_por_mensagem_pronta():
    r = turno({"intencao": "saudacao"}, primeira_mensagem="Olá! Vim pelo Google e quero um orçamento")
    assert r["metricas"]["canal"] == "google"


def test_origem_meta_por_anuncio():
    r = turno({"intencao": "saudacao"}, anuncio="Conserto de tela em 1 hora")
    assert (r["metricas"]["canal"], r["metricas"]["campanha"]) == ("meta", "Conserto de tela em 1 hora")


def test_lead_de_domingo_a_noite_e_fora_do_horario():
    r = turno({"intencao": "saudacao"}, agora=DOMINGO_22H)
    assert r["metricas"]["fora_horario"] is True


def test_visita_fora_do_horario_informa_proxima_abertura():
    t1, t2 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="a15", defeito="tela quebrada")]},
        {"intencao": "confirmar_visita", "visita_texto": "amanhã cedo"},
        agora=DOMINGO_22H,
    )
    assert t2["conducao"]["visita"]["loja_aberta_agora"] is False
    assert t2["conducao"]["visita"]["proxima_abertura"] == {"dia": "amanha", "hora": "08:30"}


def test_duplicata_por_texto_e_data_crus():
    r1 = turno({"intencao": "saudacao"}, mensagem_texto="oi", mensagem_data="06/10/2026, 10:00:00")
    r2 = turno({"intencao": "saudacao"}, r1["estado_novo"], mensagem_texto="oi", mensagem_data="06/10/2026, 10:00:00")
    r3 = turno({"intencao": "saudacao"}, r1["estado_novo"], mensagem_texto="oi", mensagem_data="06/10/2026, 10:05:00")
    assert r2["conducao"]["duplicata"] is True and r2["estado_novo"]["turnos"] == 1
    assert r3["conducao"]["duplicata"] is False


# --- Follow-up ------------------------------------------------------------------

def _estado_orcado():
    return turno({"intencao": "pedir_orcamento",
                  "equipamentos": [eq(categoria="celular", modelo="a15", defeito="tela quebrada")]})["estado_novo"]


def test_followup_lembrete_dentro_da_janela_de_24h():
    r = decidir_followup({"estado": _estado_orcado(), "contexto_dados": CTX, "agora": "2026-10-07T10:00:00-03:00",
                          "ultima_msg_cliente_em": "2026-10-06T13:00:00-03:00", "followups_enviados": 0})
    assert r["enviar"] and r["tipo"] == "lembrete"


def test_followup_nao_dispara_fora_do_horario_nem_depois_de_agendar():
    fora = decidir_followup({"estado": _estado_orcado(), "contexto_dados": CTX, "agora": DOMINGO_22H,
                             "ultima_msg_cliente_em": "2026-10-04T01:00:00-03:00"})
    assert fora["enviar"] is False
    agendado = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="a15", defeito="tela quebrada")]},
        {"intencao": "confirmar_visita", "visita_texto": "sábado"})[-1]["estado_novo"]
    r = decidir_followup({"estado": agendado, "contexto_dados": CTX, "agora": "2026-10-07T10:00:00-03:00",
                          "ultima_msg_cliente_em": "2026-10-06T13:00:00-03:00"})
    assert r["tipo"] == "lembrete_visita"                     # agendado: so o lembrete da visita, nunca reengajar
    r2 = decidir_followup({"estado": r["estado_novo"], "contexto_dados": CTX, "agora": "2026-10-10T10:00:00-03:00",
                           "ultima_msg_cliente_em": "2026-10-06T13:00:00-03:00"})
    assert r2["enviar"] is False


# --- HTTP -----------------------------------------------------------------------

def test_endpoints_http():
    cli = TestClient(app)
    assert cli.get("/health").json()["status"] == "ok"
    r = cli.post("/processar", json={"ticket_id": 7, "leitura": {"intencao": "saudacao"}, "contexto_dados": CTX,
                                     "agora": TERCA_10H})
    assert r.status_code == 200 and set(r.json()) == {"estado_novo", "conducao", "metricas"}


# --- v1.1: nome, objecoes, so dado ---------------------------------------------

@pytest.mark.parametrize("nome", ["😎", "5511999990000", "~", ".", "Cliente", None])
def test_nome_do_whatsapp_invalido_pergunta_o_nome_antes(nome):
    c = turno({"intencao": "pedir_orcamento", "perguntas": ["endereco"],
               "equipamentos": [eq(categoria="celular", defeito="tela quebrada")]}, nome_whatsapp=nome)["conducao"]
    assert c["objetivo"] == "perguntar_nome" and c["coletar"]["dado"] == "nome"
    assert c["usar_nome"] is None
    assert c["responder"][0]["pergunta"] == "endereco"          # pergunta direta respondida no mesmo turno
    assert c["equipamento_ja_citado"]["equipamento"] == "Celular"  # o que o cliente contou nao se perde


def test_depois_do_nome_segue_de_onde_parou():
    t1, t2 = (turno({"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", defeito="tela quebrada")]},
                    nome_whatsapp="🔥"),) * 2
    t2 = turno({"intencao": "informar", "nome_informado": "Michele"}, t1["estado_novo"], nome_whatsapp="🔥")
    c = t2["conducao"]
    assert c["usar_nome"] == "Michele" and c["nome_recem_informado"] is True
    assert c["coletar"]["dado"] == "modelo" and not c["saudar"]


def test_nome_so_e_perguntado_uma_vez():
    t1 = turno({"intencao": "saudacao"}, nome_whatsapp="😎")
    t2 = turno({"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="notebook", defeito="teclado falhando")]},
               t1["estado_novo"], nome_whatsapp="😎")
    assert t2["conducao"]["objetivo"] == "orcamento"


def test_vou_pesquisar_deixa_porta_aberta_sem_afirmar_fato_nao_confirmado():
    t1, t2 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="a15", defeito="tela quebrada")]},
        {"intencao": "objecao", "objecao": "vou_pesquisar"},
    )
    o = t2["conducao"]["objecao"]
    chaves = {a["chave"] for a in o["argumentos"]}
    assert o["proximo_passo"] == "deixar_porta_aberta" and o["explorar"] == "o_que_falta_saber"
    assert "avaliacao_sem_custo" in chaves                     # confirmado pelo dono em 06/10
    assert "condicao_pagamento" in chaves


def test_nao_vale_a_pena_oferece_compra_na_propria_loja():
    t1, t2 = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="iphone 11", defeito="tela quebrada")]},
        {"intencao": "objecao", "objecao": "nao_vale_a_pena", "impacto": "é o celular que uso pra trabalhar"},
    )
    c = t2["conducao"]
    assert c["objecao"]["proximo_passo"] == "oferecer_compra"
    assert "boleto" in c["oferecer_compra"]["venda_aparelhos"]
    assert c["objecao"]["desejo"]["impacto_relatado"] == "é o celular que uso pra trabalhar"
    assert c["deve_transferir"] is False


def test_impacto_relatado_vira_desejo_na_orientacao():
    c = turno({"intencao": "pedir_orcamento", "impacto": "estou sem falar com meus clientes",
               "equipamentos": [eq(categoria="celular", modelo="g54", defeito="nao carrega")]})["conducao"]
    assert c["orientacao"]["desejo"]["impacto_relatado"] == "estou sem falar com meus clientes"


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def test_conducao_nao_carrega_frase_pronta_de_preco_nem_de_horario():
    """ADR-0013: o narrador e literal; a maquina entrega dado, nao frase."""
    saidas = conversa(
        {"intencao": "pedir_orcamento", "perguntas": ["preco", "horario"],
         "equipamentos": [eq(categoria="celular", modelo="a52s", defeito="tela nao acende")]},
        {"intencao": "objecao", "objecao": "preco_alto"},
        {"intencao": "confirmar_visita", "visita_texto": "amanhã cedo"},
        agora=DOMINGO_22H,
    )
    for s in saidas:
        for txt in _strings(s["conducao"]):
            assert "R$" not in txt and " às " not in txt, txt


def test_lembrete_de_visita_no_dia_seguinte():
    agendado = conversa(
        {"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", modelo="a15", defeito="tela quebrada")]},
        {"intencao": "confirmar_visita", "visita_texto": "amanhã de manhã"})[-1]["estado_novo"]
    r = decidir_followup({"estado": agendado, "contexto_dados": CTX, "agora": "2026-10-07T09:00:00-03:00"})
    assert r["enviar"] and r["tipo"] == "lembrete_visita" and r["estado_novo"]["lembrete_visita_enviado"]
    r2 = decidir_followup({"estado": r["estado_novo"], "contexto_dados": CTX, "agora": "2026-10-07T15:00:00-03:00"})
    assert r2["enviar"] is False


def test_servico_mais_barato_que_a_entrada_nao_leva_condicao_de_parcelamento():
    c = turno({"intencao": "pedir_orcamento", "equipamentos": [eq(categoria="celular", defeito="esta muito lento, travando")]})["conducao"]
    assert c["orientacao"]["preco"] == 120 and c["orientacao"]["condicao_pagamento"] is None
