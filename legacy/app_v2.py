"""
app_v2.py：SmartVoyage 产品级前端界面。

核心功能：
    用户登录/注册（JWT 认证）。
    多会话管理（侧边栏切换历史对话）。
    完整的 A2A + MCP 旅行助手对话。
    订单管理面板。
    Agent 状态监控。
"""
from typing import Any
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import asyncio
import uuid
import json
import requests
from datetime import datetime
import pytz
import re

import streamlit as st
from python_a2a import A2AClient, AgentNetwork, Message, TextContent, MessageRole, Task
from langchain_openai import ChatOpenAI

from core.config import Config
from core.create_logger import logger
from core.main_prompts import SmartVoyagePrompts

conf = Config()

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")

# ---------- 页面配置 ----------
st.set_page_config(
    page_title="SmartVoyage 智能旅行助手",
    layout="wide",
    page_icon="?",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.stChatMessage { background-color: #1e293b !important; border-radius: 12px !important; }
.stChatMessage.user { background-color: #334155 !important; }
.stChatMessage .stMarkdown, .stChatMessage .stMarkdown * { color: #f1f5f9 !important; }
div[data-testid="stSidebar"] { background-color: #0f172a; }
div[data-testid="stSidebar"] * { color: #cbd5e1; }
.main .block-container { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)


# ---------- 初始化 ----------
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "token" not in st.session_state:
        st.session_state.token = None
    if "user" not in st.session_state:
        st.session_state.user = None
    if "agent_network" not in st.session_state:
        network = AgentNetwork(name="Travel Assistant Network")
        network.add("WeatherQueryAssistant", A2AClient("http://localhost:5005", timeout=90))
        network.add("TicketQueryAssistant", A2AClient("http://localhost:5006", timeout=90))
        network.add("TicketOrderAssistant", A2AClient("http://localhost:5007", timeout=90))
        network.add("HotelQueryAssistant", A2AClient("http://localhost:5008", timeout=90))
        network.add("ItineraryPlannerAssistant", A2AClient("http://localhost:5009", timeout=90))
        st.session_state.agent_network = network
        st.session_state.llm = ChatOpenAI(
            model=conf.fast_model_name, api_key=conf.api_key,
            base_url=conf.base_url, temperature=0.1,
            extra_body={"enable_thinking": False}
        )
        st.session_state.conversation_history = ""
        st.session_state.agent_urls = {
            "WeatherQueryAssistant": "5005",
            "TicketQueryAssistant": "5006",
            "TicketOrderAssistant": "5007",
            "HotelQueryAssistant": "5008",
            "ItineraryPlannerAssistant": "5009"
        }


init_session_state()
llm = st.session_state.llm


# ---------- 认证 ----------
def api_register(username, password, email=None, phone=None):
    try:
        resp = requests.post(f"{API_BASE}/api/register",
                             json={"username": username, "password": password,
                                   "email": email, "phone": phone}, timeout=10)
        return resp.json()
    except Exception as e:
        return {"code": -1, "message": str(e)}


def api_login(username, password):
    try:
        resp = requests.post(f"{API_BASE}/api/login",
                             json={"username": username, "password": password}, timeout=10)
        return resp.json()
    except Exception as e:
        return {"code": -1, "message": str(e)}


def show_auth_page():
    st.title("? SmartVoyage 智能旅行助手")
    st.markdown("基于 A2A 协议的多智能体旅行服务系统")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["登录", "注册"])
        with tab1:
            with st.form("login_form"):
                username = st.text_input("用户名", key="login_user")
                password = st.text_input("密码", type="password", key="login_pass")
                if st.form_submit_button("登录", use_container_width=True):
                    result = api_login(username, password)
                    if result.get("code") == 0:
                        data = result["data"]
                        st.session_state.token = data["token"]
                        st.session_state.user = data
                        st.success("登录成功！")
                        st.rerun()
                    else:
                        st.error(result.get("message", "登录失败"))
        with tab2:
            with st.form("register_form"):
                username = st.text_input("用户名（至少3位）", key="reg_user")
                password = st.text_input("密码（至少6位）", type="password", key="reg_pass")
                email = st.text_input("邮箱（可选）", key="reg_email")
                phone = st.text_input("手机号（可选）", key="reg_phone")
                if st.form_submit_button("注册", use_container_width=True):
                    result = api_register(username, password, email, phone)
                    if result.get("code") == 0:
                        data = result["data"]
                        st.session_state.token = data["token"]
                        st.session_state.user = data
                        st.success("注册成功，已自动登录！")
                        st.rerun()
                    else:
                        st.error(result.get("message", "注册失败"))


# ---------- 意图识别 + 对话处理 ----------
def intent_agent(user_input):
    chain = SmartVoyagePrompts.intent_prompt() | llm
    current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
    intent_response = chain.invoke(
        {"conversation_history": '\n'.join(st.session_state.conversation_history.split("\n")[-6:]),
         "query": user_input, "current_date": current_date}).content.strip()
    intent_response = re.sub(r'^```json\s*|\s*```$', '', intent_response).strip()
    intent_output = json.loads(intent_response)
    return (intent_output.get("intents", []),
            intent_output.get("user_queries", {}),
            intent_output.get("follow_up_message", ""))


def process_input(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.conversation_history += f"\nUser: {prompt}"

    try:
        intents, user_queries, follow_up = intent_agent(prompt)

        if "out_of_scope" in intents or follow_up:
            response = follow_up if follow_up else "抱歉，我目前只能处理旅行相关问题。"
        else:
            responses = []
            for intent in intents:
                intent_map = {
                    "weather": "WeatherQueryAssistant",
                    "flight": "TicketQueryAssistant", "train": "TicketQueryAssistant",
                    "concert": "TicketQueryAssistant",
                    "order": "TicketOrderAssistant",
                    "hotel": "HotelQueryAssistant",
                    "itinerary": "ItineraryPlannerAssistant"
                }
                agent_name = intent_map.get(intent)

                if intent == "attraction":
                    chain = SmartVoyagePrompts.attraction_prompt() | llm
                    responses.append(chain.invoke({"query": prompt}).content.strip())
                elif agent_name:
                    query_str = user_queries.get(intent, "")
                    agent = st.session_state.agent_network.get_agent(agent_name)
                    chat_history = '\n'.join(st.session_state.conversation_history.split("\n")[-7:-1]) + f'\nUser: {query_str}'
                    message = Message(content=TextContent(text=chat_history), role=MessageRole.USER)
                    task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())
                    raw = asyncio.run(agent.send_task_async(task))

                    if raw.status.state == 'completed':
                        agent_result = raw.artifacts[0]['parts'][0]['text']
                    else:
                        agent_result = raw.status.message['content']['text']

                    if agent_name == "WeatherQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_weather_prompt() | llm
                        responses.append(chain.invoke({"query": query_str, "raw_response": agent_result}).content.strip())
                    elif agent_name == "TicketQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_ticket_prompt() | llm
                        responses.append(chain.invoke({"query": query_str, "raw_response": agent_result}).content.strip())
                    elif agent_name == "HotelQueryAssistant":
                        chain = SmartVoyagePrompts.summarize_hotel_prompt() | llm
                        responses.append(chain.invoke({"query": query_str, "raw_response": agent_result}).content.strip())
                    else:
                        responses.append(agent_result)
                else:
                    responses.append("暂不支持此意图。")

            response = "\n\n".join(responses)

        st.session_state.conversation_history += f"\nAssistant: {response}"
    except json.JSONDecodeError:
        response = "意图识别异常，请重试。"
    except Exception as e:
        response = f"处理失败：{str(e)}"

    st.session_state.messages.append({"role": "assistant", "content": response})


# ---------- 主界面 ----------
if not st.session_state.token:
    show_auth_page()
else:
    # 侧边栏
    with st.sidebar:
        st.markdown(f"### ? {st.session_state.user.get('username', '用户')}")
        if st.button("退出登录", use_container_width=True):
            st.session_state.token = None
            st.session_state.user = None
            st.session_state.messages = []
            st.rerun()

        st.divider()

        # Agent 状态
        st.markdown("#### ? Agent 状态")
        agent_names = {
            "WeatherQueryAssistant": "天气查询",
            "TicketQueryAssistant": "票务查询",
            "TicketOrderAssistant": "票务预订",
            "HotelQueryAssistant": "酒店查询",
            "ItineraryPlannerAssistant": "行程规划"
        }
        for name, label in agent_names.items():
            st.markdown(f"- {label} (`:{st.session_state.agent_urls[name]}`)")

        st.divider()

        if st.button("清空对话", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_history = ""
            st.rerun()

    # 对话区
    st.title("? SmartVoyage 智能旅行助手")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("输入你的旅行需求..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.spinner("正在为你服务..."):
            process_input(prompt)
        with st.chat_message("assistant"):
            st.markdown(st.session_state.messages[-1]["content"])
