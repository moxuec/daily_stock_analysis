# -*- coding: utf-8 -*-
"""
Chat command for free-form conversation with the Agent.
"""

import logging

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse
from src.config import get_config
import threading

logger = logging.getLogger(__name__)

_session_locks = {}
_session_locks_lock = threading.Lock()

class ChatCommand(BotCommand):
    """
    Chat command handler.
    
    Usage: /chat <message>
    Example: /chat 帮我分析一下茅台最近的走势
    """
    
    @property
    def name(self) -> str:
        return "chat"
        
    @property
    def description(self) -> str:
        return "与 AI 助手进行自由对话 (需开启 Agent 模式)"
        
    @property
    def usage(self) -> str:
        return "/chat <问题>"
        
    @property
    def aliases(self) -> list[str]:
        return ["c", "问"]
        
    def execute(self, message: BotMessage, args: list[str]) -> BotResponse:
        """Execute the chat command."""
        config = get_config()
        
        if not config.agent_mode:
            return BotResponse.text_response(
                "⚠️ Agent 模式未开启，无法使用对话功能。\n请在配置中设置 `AGENT_MODE=true`。"
            )
            
        if not args:
            return BotResponse.text_response(
                "⚠️ 请提供要询问的问题。\n用法: `/chat <问题>`\n示例: `/chat 帮我分析一下茅台最近的走势`"
            )
            
        user_message = " ".join(args)
        session_id = f"{message.platform}_{message.user_id}"
        
        import uuid
        import threading
        task_id = f"chat_{uuid.uuid4()}"
        
        # 后台执行对话
        thread = threading.Thread(
            target=self._run_chat_async,
            args=(message, config, user_message, session_id),
            daemon=True
        )
        thread.start()
        
        return BotResponse.markdown_response(
            f"✅ **对话任务已提交**\n\n"
            f"• 任务 ID: `{task_id[:20]}...`\n\n"
            f"AI 思考中，完成后将自动发送回复。"
        )

    def _run_chat_async(self, message: BotMessage, config, user_message: str, session_id: str) -> None:
        """后台异步执行 Agent 聊天"""
        try:
            with _session_locks_lock:
                if session_id not in _session_locks:
                    _session_locks[session_id] = threading.Lock()
                session_lock = _session_locks[session_id]
                
            with session_lock:
                from src.agent.factory import build_agent_executor
                executor = build_agent_executor(config)
                result = executor.chat(message=user_message, session_id=session_id)
            
            if result.success:
                response_text = result.content
            else:
                response_text = f"⚠️ 对话任务执行失败: {result.error}"

            from src.notification import NotificationService
            notification_service = NotificationService(source_message=message)
            notification_service.send_to_context(response_text)
            
            logger.info(f"[ChatCommand] 后台对话完成并已推送")
                
        except Exception as e:
            logger.error(f"Chat command run async failed: {e}")
            logger.exception("Chat error details:")
            try:
                from src.notification import NotificationService
                notification_service = NotificationService(source_message=message)
                notification_service.send_to_context(f"⚠️ 对话任务执行出错: {str(e)[:100]}")
            except Exception:
                pass
