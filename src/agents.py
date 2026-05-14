"""Gemini agent with tool-calling for flight search and shopping search."""

from __future__ import annotations

import logging
from datetime import date

from google import genai
from google.genai import types

from .config import Config
from .tools.serpapi import search_flights
from .tools.shopping import search_shopping

log = logging.getLogger("tara-bot.agent")

TODAY = date.today()

SYSTEM_PROMPT = f"""Bạn là Tara Bot — một agent thông minh chuyên tìm kiếm chuyến bay và săn giá đồ.

NGUYÊN TẮC:
- Trả lời bằng tiếng Việt tự nhiên, thân thiện.
- Khi user hỏi vé máy bay, hãy gọi hàm search_flights.
- Khi user hỏi giá sản phẩm / so sánh giá / mua hàng, hãy gọi hàm search_shopping.
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
        api_key = Config.gemini_api_key
        if not api_key or "(tôi sẽ cung cấp sau)" in api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please update your .env file.")

        self.client = genai.Client(api_key=api_key)

        # Both are custom functions — no conflict with built-in tools
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[
                search_flights,    # SerpAPI flights (structured data)
                search_shopping,   # Gemini Search Grounding (free)
            ],
        )

        self.chat_session = self.client.chats.create(
            model="gemini-2.5-flash",
            config=self.config,
        )

    def chat(self, user_message: str) -> str:
        """Send user message, handle tools automatically, return response."""
        try:
            response = self.chat_session.send_message(user_message)
            return response.text
        except Exception as e:
            log.exception("Error in Gemini chat")
            return f"😵 Có lỗi xảy ra khi gọi Gemini: {e}\nThử lại sau nhé!"
