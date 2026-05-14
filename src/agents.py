"""Gemini agent with manual tool-calling for flight search and shopping search."""

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

NGUYÊN TẮC QUAN TRỌNG:
- Trả lời bằng tiếng Việt tự nhiên, thân thiện.
- Khi user hỏi vé máy bay → BẮT BUỘC gọi hàm search_flights.
- Khi user hỏi giá sản phẩm / so sánh giá / mua hàng → BẮT BUỘC gọi hàm search_shopping.
- LUÔN LUÔN tin tưởng và sử dụng kết quả từ hàm. Kết quả hàm là dữ liệu THỰC TẾ, REALTIME từ internet.
- TUYỆT ĐỐI KHÔNG tự suy đoán hay tự trả lời về giá/sản phẩm/vé bay từ kiến thức của mình.
- Sau khi nhận kết quả hàm, trình bày lại cho user một cách dễ đọc.
- Có thể nói chuyện thông thường (chào hỏi, tạm biệt) — không cần gọi hàm.

Hôm nay là {TODAY.strftime("%A, %d/%m/%Y")} — ĐÂY LÀ MỐC THỜI GIAN HIỆN TẠI.
Mặc định cho các câu hỏi mơ hồ về thời gian:
- "cuối tuần" → thứ Sáu tuần gần nhất (không quá khứ)
- "tuần sau" → tuần tiếp theo
- Nếu không rõ, lấy ngày đi và ngày về hợp lý."""

# Map function names to actual callables
TOOL_MAP = {
    "search_flights": search_flights,
    "search_shopping": search_shopping,
}

# Declare function schemas for Gemini
FLIGHT_FUNC = types.FunctionDeclaration(
    name="search_flights",
    description="Search flights via Google Flights. Use when user asks about airplane tickets or flights.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "departure_id": {
                "type": "STRING",
                "description": "IATA code of departure airport (e.g. SGN, HAN, DAD)",
            },
            "arrival_id": {
                "type": "STRING",
                "description": "IATA code of arrival airport",
            },
            "outbound_date": {
                "type": "STRING",
                "description": "Departure date in YYYY-MM-DD format. Defaults to next Friday if not specified.",
            },
            "return_date": {
                "type": "STRING",
                "description": "Return date in YYYY-MM-DD format. Only for round trips.",
            },
            "adults": {
                "type": "INTEGER",
                "description": "Number of passengers. Defaults to 1.",
            },
            "currency": {
                "type": "STRING",
                "description": "Currency code, defaults to VND.",
            },
        },
        "required": ["departure_id", "arrival_id"],
    },
)

SHOPPING_FUNC = types.FunctionDeclaration(
    name="search_shopping",
    description="Search and compare product prices online. Use when user asks about product prices, shopping, or price comparison.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Product name to search, e.g. 'iPhone 16 256GB' or 'laptop gaming 20 triệu'",
            },
        },
        "required": ["query"],
    },
)


class Agent:
    def __init__(self):
        api_key = Config.gemini_api_key
        if not api_key or "(tôi sẽ cung cấp sau)" in api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please update your .env file.")

        self.client = genai.Client(api_key=api_key)

        self.tool_config = types.Tool(
            function_declarations=[FLIGHT_FUNC, SHOPPING_FUNC],
        )

        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[self.tool_config],
        )

        self.chat_session = self.client.chats.create(
            model="gemini-2.5-flash",
            config=self.config,
        )

    def _execute_function_call(self, function_call) -> str:
        """Execute a function call from Gemini and return the result."""
        name = function_call.name
        args = dict(function_call.args) if function_call.args else {}

        log.info(f"Executing tool: {name}({args})")

        func = TOOL_MAP.get(name)
        if not func:
            return f"Unknown function: {name}"

        try:
            result = func(**args)
            log.info(f"Tool {name} returned {len(result)} chars")
            return result
        except Exception as e:
            log.exception(f"Error executing {name}")
            return f"⚠️ Lỗi khi gọi {name}: {e}"

    def chat(self, user_message: str) -> str:
        """Send user message, handle tool calls manually, return response."""
        try:
            response = self.chat_session.send_message(user_message)

            # Check if model wants to call a function
            while response.candidates:
                candidate = response.candidates[0]
                parts = candidate.content.parts

                # Look for function calls
                function_calls = [p.function_call for p in parts if p.function_call]

                if not function_calls:
                    # No function calls, return text
                    break

                # Execute each function call and collect results
                function_responses = []
                for fc in function_calls:
                    result = self._execute_function_call(fc)
                    log.info(f"Function {fc.name} response preview: {result[:200]}")
                    function_responses.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"output": result},
                        )
                    )

                # Send function results back to model
                response = self.chat_session.send_message(function_responses)

            return response.text or "Không có phản hồi."

        except Exception as e:
            log.exception("Error in Gemini chat")
            return f"😵 Có lỗi xảy ra khi gọi Gemini: {e}\nThử lại sau nhé!"
