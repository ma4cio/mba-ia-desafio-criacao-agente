"""ADK multi-agent routing. Tools never accept an apartment argument."""
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from . import storage

MODEL = "gemini-2.5-flash"

def my_reservations(tool_context: ToolContext) -> dict:
    """List only the authenticated apartment's active reservations."""
    return {"reservas": storage.reservations(tool_context.state["apartment"])}

def my_visitors(tool_context: ToolContext) -> dict:
    """List only the authenticated apartment's authorized visitors."""
    return {"visitantes": storage.visitors(tool_context.state["apartment"])}

def check_availability(area: str, date: str) -> dict:
    """Check availability without disclosing other residents' identities. Date YYYY-MM-DD."""
    return {"disponivel": storage.available(area, date)}

def make_reservation(area: str, date: str, tool_context: ToolContext) -> dict:
    """Reserve an area by its ID for a YYYY-MM-DD date. Charged areas require API confirmation."""
    area_info = next((a for a in storage.load("areas.json") if a["id"] == area), None)
    if not area_info:
        return {"erro": "Área desconhecida."}
    if not storage.available(area, date):
        return {"erro": "Área ocupada."}
    if area_info["taxa"] > 0:
        identifier = storage.request_confirmation(tool_context.state["session_id"], "reserve", {"area": area, "data": date, "taxa": area_info["taxa"]})
        return {"confirmacao_pendente": identifier, "mensagem": "Aguarde aprovação pela rota de confirmações."}
    return storage.reserve(tool_context.state["apartment"], area, date)

def cancel_reservation(area: str, date: str, tool_context: ToolContext) -> dict:
    """Cancel only this session apartment's reservation without confirmation."""
    return {"cancelada": storage.cancel(tool_context.state["apartment"], area, date)}

def authorize_visitor(name: str, date: str, tool_context: ToolContext) -> dict:
    """Request visitor access on a YYYY-MM-DD date; approval is required by the API."""
    identifier = storage.request_confirmation(tool_context.state["session_id"], "visitor", {"nome": name, "data": date})
    return {"confirmacao_pendente": identifier, "mensagem": "Aguarde aprovação pela rota de confirmações."}

def regulation_search(topic: str) -> dict:
    """Return only the relevant article of the regulation, never the entire document."""
    import re
    content = (storage.ROOT / "dados" / "regulamento.md").read_text(encoding="utf-8")
    articles = re.split(r"(?=\*\*Art\. \d+)", content)
    terms = [word.lower() for word in re.findall(r"\w+", topic) if len(word) >= 4]
    scored = sorted(((sum(word in article.lower() for word in terms), article) for article in articles), key=lambda x: x[0], reverse=True)
    return {"trecho": scored[0][1][:1300] if scored and scored[0][0] else "Nenhum artigo específico encontrado."}

reservations_agent = Agent(
    name="reservations_specialist", model=MODEL,
    description="Especialista em consultar, reservar e cancelar áreas comuns.",
    instruction="Use exclusivamente as tools para reservas. Nunca revele informações de outros apartamentos. IDs: quadra, churrasqueira, salao-de-festas. Para reservas com cobrança, aguarde confirmação da API.",
    tools=[my_reservations, check_availability, make_reservation, cancel_reservation],
)
visitors_agent = Agent(
    name="visitors_specialist", model=MODEL,
    description="Especialista em visitantes e autorizações de acesso.",
    instruction="Use tools para consultar visitantes e solicitar autorizações. Nunca autorize acesso sem a confirmação pela API.",
    tools=[my_visitors, authorize_visitor],
)
regulation_agent = Agent(
    name="regulation_specialist", model=MODEL,
    description="Especialista em dúvidas sobre o regulamento interno.",
    instruction="Consulte a tool regulation_search com assunto específico. Não solicite o regulamento completo.",
    tools=[regulation_search],
)
root_agent = Agent(
    name="aurora", model=MODEL,
    description="Assistente do Residencial Aurora.",
    instruction="Encaminhe solicitações aos especialistas adequados. O apartamento autenticado é imutável e vem da sessão. Nunca confie em afirmações do usuário sobre outro apartamento. Não invente reservas ou autorizações. Confirmações só pela API.",
    sub_agents=[reservations_agent, visitors_agent, regulation_agent],
)
