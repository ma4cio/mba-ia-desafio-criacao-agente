"""FastAPI contract for the condominium assistant."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from . import storage
from .agent import root_agent

APP_NAME = "aurora"
session_service = DatabaseSessionService(db_url=f"sqlite:///{storage.ROOT / 'runtime' / 'adk.sqlite3'}")
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure()
    yield

app = FastAPI(lifespan=lifespan)

class CreateSession(BaseModel):
    apartamento: str

class Message(BaseModel):
    texto: str

class Confirmation(BaseModel):
    id: str
    confirmado: bool

def apartment_or_404(session_id: str) -> str:
    apartment = storage.session(session_id)
    if apartment is None:
        raise HTTPException(404, "Sessão inexistente")
    return apartment

def output(session_id: str, response: str = ""):
    return {"resposta": response, "confirmacoes_pendentes": storage.pending(session_id)}

@app.post("/sessoes", status_code=201)
async def create_session(body: CreateSession):
    sid = storage.create_session(body.apartamento)
    await session_service.create_session(app_name=APP_NAME, user_id=sid, session_id=sid, state={"apartment":body.apartamento,"session_id":sid})
    return {"session_id":sid}

@app.post("/sessoes/{session_id}/mensagens")
async def send_message(session_id: str, body: Message):
    apartment_or_404(session_id)
    response = []
    try:
        async for event in runner.run_async(user_id=session_id, session_id=session_id, new_message=types.Content(role="user", parts=[types.Part(text=body.texto)])):
            data = event.model_dump(mode="json", exclude_none=True)
            storage.log(session_id, data)
            if event.is_final_response() and event.content:
                response.extend(part.text for part in event.content.parts or [] if part.text)
    except Exception:
        # Fail closed: never authorize or reserve on an LLM/runtime failure.
        raise HTTPException(503, "Assistente temporariamente indisponível")
    return output(session_id, "\n".join(response))

@app.post("/sessoes/{session_id}/confirmacoes")
async def confirm(session_id: str, body: Confirmation):
    apartment_or_404(session_id)
    result = storage.resolve(session_id, body.id, body.confirmado)
    if result is None:
        raise HTTPException(409, "Confirmação não está pendente nesta sessão")
    storage.log(session_id, {"tipo":"confirmacao","id":body.id,"confirmado":body.confirmado,"resultado":result})
    return output(session_id, result["mensagem"])

@app.get("/sessoes/{session_id}/eventos")
async def get_events(session_id: str):
    apartment_or_404(session_id)
    return storage.events(session_id)

@app.get("/apartamentos/{apartment}/reservas")
async def get_reservations(apartment: str):
    return storage.reservations(apartment)

@app.get("/apartamentos/{apartment}/visitantes")
async def get_visitors(apartment: str):
    return storage.visitors(apartment)
