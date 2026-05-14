"""Gemini agent with tool-calling for flight and shopping search."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import google.generativeai as genai
from google.generativeai.types import RequestOptions

from .config import Config
from .tools.serpapi import search_flights, search_shopping

log = logging.getLogger("tara-bot.agent")

TODAY = date.today()

SYSTEM_PROMPT = f"""Bạn là Tara Bot — một agent thông minh chuyên tìm kiếm chuyến bay và săn giá đồ.

NGUYÊN TẮC:
- Trả lời bằng tiếng Việt tự nhiên, thân thiện.
- Khi user hỏi vé máy bay, hãy gọi hàm search_flights.
- Khi user hỏi giá sản phẩm, hãy gọi hàm search_shopping.
- Sau khi hàm trả kết quả, chuyển tiếp NGUYÊN VĂN kết quả đó cho user, chỉ thêm 1-2 câu ngắn ở đầu hoặc cuối.
- KHÔNG reformat lại kết quả từ hàm — giữ nguyên định dạng.
- Có thể nói chuyện thông thường (chào hỏi, tạm biệt) — không cần gọi hàm.

Hôm nay là {TODAY.strftime("%A, %d/%m/%Y")} — ĐÂY LÀ MỐC THỜI GIAN HIỆN TẠI.
Mặc định cho các câu hỏi mơ hồ về thời gian:
- "cuối tuần" → thứ Sáu tuần gần nhất (không quá khứ)
- "tuần sau" → tuần tiếp theo
- Nếu không rõ, lấy ngày đi và ngày về hợp lý."""

class Agent:
    def __init__(self):
        api_key = Config.gemini_api_key or Config.anthropic_api_key # Fallback if user mislabelled
        if not api_key or "(tôi sẽ cung cấp sau)" in api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please update your .env file.")
            
        genai.configure(api_key=api_key)
        
        # Use gemini-3-flash-preview - latest Gemini 3
        self.model = genai.GenerativeModel(
            model_name='gemini-3-flash-preview',
            tools=[search_flights, search_shopping],
            system_instruction=SYSTEM_PROMPT
        )
        self.chat_session = self.model.start_chat(enable_automatic_function_calling=True)

    def chat(self, user_message: str) -> str:
        """Send user message, handle tools automatically, return response."""
        try:
            # We use a timeout to avoid hanging
            response = self.chat_session.send_message(
                user_message,
                request_options=RequestOptions(timeout=60)
            )
            return response.text
        except Exception as e:
            log.exception("Error in Gemini chat")
            return f"😵 Có lỗi xảy ra khi gọi Gemini: {e}\nThử lại sau nhé!"
