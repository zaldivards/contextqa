from typing import AsyncGenerator

from langchain import hub
from langchain.agents import AgentExecutor, create_json_chat_agent
from langchain.prompts.chat import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

from contextqa.agents.tools import searcher
from contextqa.models import PartialModelData
from contextqa.models.schemas import LLMQueryRequest
from contextqa.utils import memory
from contextqa.utils.streaming import consumer_producer


_MESSAGES = [
    ("system", "You are a helpful assistant called ContextQA that answers user inputs and questions"),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}"),
]


def get_llm_assistant(internet_access: bool, partial_model_data: PartialModelData) -> RunnableWithMessageHistory:
    """Return certain LLM assistant based on the system configuration

    Parameters
    ----------
    internet_access : bool
        flag indicating whether an assistant with internet access was requested

    Returns
    -------
    RunnableWithMessageHistory
    """
    tools = [searcher]
    llm = partial_model_data.partial_model(streaming=True)
    if internet_access:
        prompt = hub.pull("hwchase17/react-chat-json")
        agent = create_json_chat_agent(
            llm=partial_model_data.partial_model(streaming=True),
            prompt=prompt,
            tools=tools,
        )
        agent_executor = AgentExecutor(agent=agent, tools=tools)
        return RunnableWithMessageHistory(
            agent_executor,
            memory.Redis,
            input_messages_key="input",
            history_messages_key="chat_history",
        )
    prompt = ChatPromptTemplate.from_messages(_MESSAGES)
    chain = prompt | llm
    chain_with_history = RunnableWithMessageHistory(
        chain, memory.Redis, input_messages_key="input", history_messages_key="history"
    )
    return chain_with_history


def qa_service(params: LLMQueryRequest, partial_model: PartialModelData) -> AsyncGenerator:
    """Chat with the llm

    Parameters
    ----------
    params : LLMQueryRequest
        request body parameters

    Returns
    -------
    AsyncGenerator
    """

    assistant = get_llm_assistant(params.internet_access, partial_model)
    return consumer_producer(
        assistant.astream({"input": params.message}, config={"configurable": {"session_id": "default"}})
    )
