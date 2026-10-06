from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from maquina import VERSAO, decidir_followup, processar

app = FastAPI(title="senhor-smart-estado", version=VERSAO)


class Entrada(BaseModel):
    ticket_id: Optional[int] = None
    estado: Optional[dict] = None             # None no 1o turno
    leitura: dict                             # saida do extrator (schema leitura_assistencia)
    foto: Optional[dict] = None               # saida do no de visao, quando houve imagem
    contexto_dados: Optional[dict] = None     # recorte do Carregar Contexto
    agora: Optional[str] = None               # ISO8601
    mensagem_texto: Optional[str] = None      # body.lastMessage — duplicata
    mensagem_data: Optional[str] = None       # body.lastMessageDate — duplicata
    anuncio: Optional[str] = None             # titulo do anuncio (click-to-WhatsApp)
    primeira_mensagem: Optional[str] = None   # texto cru do 1o turno — origem


class EntradaFollowup(BaseModel):
    estado: dict
    contexto_dados: Optional[dict] = None
    agora: Optional[str] = None
    ultima_msg_cliente_em: Optional[str] = None
    followups_enviados: int = 0


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "servico": "senhor-smart-estado", "versao": VERSAO}


@app.post("/processar")
def processar_endpoint(body: Entrada) -> dict[str, Any]:
    return processar(body.model_dump())


@app.post("/followup")
def followup_endpoint(body: EntradaFollowup) -> dict[str, Any]:
    return decidir_followup(body.model_dump())
