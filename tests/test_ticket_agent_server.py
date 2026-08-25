import asyncio
import uuid

from python_a2a import A2AClient, Message, TextContent, MessageRole, Task
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.config import Config
from core.create_logger import logger

conf = Config()

# 初始化 LLM
llm = ChatOpenAI(
            model=conf.model_name,
            api_key=conf.api_key,
            base_url=conf.base_url,
            temperature=0.1
        )


# 票务总结提示模板
ticket_prompt = ChatPromptTemplate.from_template(
    """
    您是一位票务解说员，以生动、引人入胜的风格为用户介绍票务查询结果。基于以下查询结果，生成一段总结：
    - 突出出发/到达城市、时间、类型、价格和剩余票数，提及关键亮点。
    - 使用解说员的语气，例如“欢迎来到票务宝库！今天我们为您精选了...”。
    - 如果结果为空，建议用户尝试其他查询条件。
    - 保持中文叙述，字数控制在 100-150 字。

    查询结果：
    {tickets}

    总结：
    """
)

def main() -> None:
    # 初始化票务客户端
    ticket_client = A2AClient("http://localhost:5006")

    # 获取票务代理信息
    try:
        logger.info("获取票务助手信息")
        logger.info(f"名称: {ticket_client.agent_card.name}")
        logger.info(f"描述: {ticket_client.agent_card.description}")
        logger.info(f"版本: {ticket_client.agent_card.version}")
        if ticket_client.agent_card.skills:
            logger.info("支持技能:")
            for skill in ticket_client.agent_card.skills:
                logger.info(f"- {skill.name}: {skill.description}")
                if skill.examples:
                    logger.info(f"  示例: {', '.join(skill.examples)}")
    except Exception as e:
        logger.error(f"无法获取票务助手信息: {str(e)}")

    # 交互循环
    while True:
        user_input = input("输入您的票务查询（输入 'exit' 退出）：")
        if user_input.lower() == 'exit':
            break

        try:
            query = user_input.strip()
            logger.info(f"用户查询 (票务): {query}")

            # 发送查询
            logger.info("正在查询数据...")
            message_ticket = Message(content=TextContent(text=query), role=MessageRole.USER)
            task_ticket = Task(id="task-" + str(uuid.uuid4()), message=message_ticket.to_dict())

            # 发送任务并获取最终结果
            ticket_result_task = asyncio.run(ticket_client.send_task_async(task_ticket))
            logger.info(f"原始响应: {ticket_result_task}")

            # 生成 LLM 总结
            if ticket_result_task.status.state == 'completed':
                try:
                    summary_chain = ticket_prompt | llm
                    ticket_result = ticket_result_task.artifacts[0]["parts"][0]["text"]
                    summary = summary_chain.invoke({"tickets": ticket_result}).content.strip()
                    logger.info(f"**票务解说员总结**:\n{summary}")
                except Exception as e:
                    error_message = f"生成总结失败: {str(e)}"
                    logger.error(error_message)
            else:
                logger.info(ticket_result_task.status.message['content']['text'])
        except Exception as e:
            error_message = f"查询失败: {str(e)}"
            logger.error(error_message)


if __name__ == "__main__":
    logger.info("票务agent server查询客户端测试脚本")
    main()
