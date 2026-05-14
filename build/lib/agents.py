"""Claude agent with tool-calling for flight and shopping search."""

from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic
from anthropic.types import ToolUseBlock, TextBlock

from .config import Config
from .tools.serpapi import search_flights, search_shopping


from datetime import date

TODAY = date.today()  # 2026-05-12

SYSTEM_PROMPT = f"""Bạn là Tara Bot — một agent thông minh chuyên tìm kiếm chuyến bay và săn giá đồ.

NGUYÊN TẮC:
- Trả lời bằng tiếng Việt tự nhiên, thân thiện.
- Khi user hỏi vé máy bay, gọi tool search_flights.
- Khi user hỏi giá sản phẩm, gọi tool search_shopping.
- Sau khi tool trả kết quả, chuyển tiếp NGUYÊN VĂN kết quả đó cho user, chỉ thêm 1-2 câu ngắn ở đầu hoặc cuối.
- KHÔNG reformat lại kết quả từ tool — giữ nguyên định dạng.
- Có thể nói chuyện thông thường (chào hỏi, tạm biệt) — không cần gọi tool.

Hôm nay là {TODAY.strftime("%A, %d/%m/%Y")} — ĐÂY LÀ MỐC THỜI GIAN HIỆN TẠI.
Mặc định cho các câu hỏi mơ hồ về thời gian:
- "cuối tuần" → thứ Sáu tuần gần nhất (không quá khứ)
- "tuần sau" → tuần tiếp theo
- Nếu không rõ, lấy ngày đi và ngày về hợp lý."""

# ── Tool definitions (Anthropic format) ──────────────────────────────

FLIGHT_TOOL: dict = {
    "name": "search_flights",
    "description": "Tìm chuyến bay. Trả về giá, hãng, giờ bay.",
    "input_schema": {
        "type": "object",
        "properties": {
            "departure_id": {
                "type": "string",
                "description": "Mã sân bay đi (IATA). Mặc định SGN",
            },
            "arrival_id": {
                "type": "string",
                "description": "Mã sân bay đến (IATA)",
            },
            "outbound_date": {
                "type": "string",
                "description": "Ngày đi (YYYY-MM-DD). Mặc định thứ 6 tuần sau.",
            },
            "return_date": {
                "type": "string",
                "description": "Ngày về (YYYY-MM-DD). Mặc định đi + 5 ngày.",
            },
            "adults": {
                "type": "integer",
                "description": "Số người lớn. Mặc định 1.",
            },
        },
        "required": ["arrival_id"],
    },
}

SHOPPING_TOOL: dict = {
    "name": "search_shopping",
    "description": "Tìm sản phẩm, so sánh giá. Hữu ích khi user hỏi về giá đồ.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Tên sản phẩm cần tìm (VD: iPhone 16, máy lọc không khí)",
            },
        },
        "required": ["query"],
    },
}

ALL_TOOLS = [FLIGHT_TOOL, SHOPPING_TOOL]

# ── Tool dispatch ────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict[str, Any] = {
    "search_flights": search_flights,
    "search_shopping": search_shopping,
}


class Agent:
    def __init__(self):
        self.client = Anthropic(api_key=Config.anthropic_api_key)
        self.model = "claude-sonnet-4-6"
        self.system = SYSTEM_PROMPT
        self.history: list[dict] = []

    def chat(self, user_message: str) -> str:
        """Send user message, execute tool calls if needed, return response."""
        messages = list(self.history)
        messages.append({"role": "user", "content": user_message})

        for iteration in range(5):  # max 5 tool call loops
            response = self._call_claude(messages)

            content_blocks = response.content
            reply_text = ""
            tool_use_blocks = []
            text_blocks = []

            for block in content_blocks:
                if isinstance(block, TextBlock):
                    text_blocks.append(block)
                    reply_text += block.text
                elif isinstance(block, ToolUseBlock):
                    tool_use_blocks.append(block)

            if not tool_use_blocks:
                # Done — save to history and return
                self.history.append({"role": "user", "content": user_message})
                self.history.append({"role": "assistant", "content": reply_text})
                return reply_text

            # Execute all tools, then append ONE assistant + ONE user with all results
            tool_results = []
            for block in tool_use_blocks:
                result = self._execute_tool(block)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

            messages.append({"role": "assistant", "content": content_blocks})
            messages.append({"role": "user", "content": tool_results})

        # Exceeded loop limit
        return "Xin lỗi, em không thể xử lý yêu cầu này ngay bây giờ. Thử lại với câu hỏi đơn giản hơn nhé!"

    def _call_claude(self, messages: list) -> Any:
        """Make Claude API call with retry on 429."""
        import time

        for attempt in range(3):
            try:
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    system=self.system,
                    messages=messages,
                    tools=ALL_TOOLS,
                )
            except Exception as exc:
                err = str(exc)
                if "429" in err or "rate_limit" in err.lower():
                    wait = 30 * (attempt + 1)
                    time.sleep(wait)
                    continue
                raise
        raise Exception("Claude API: rate limit exceeded after 3 retries")

    def _execute_tool(self, block: ToolUseBlock) -> str:
        """Execute a tool and return the result string."""
        fn = TOOL_FUNCTIONS.get(block.name)
        if not fn:
            return f"Unknown tool: {block.name}"
        args = {k: v for k, v in block.input.items()}
        try:
            return fn(**args)
        except Exception as e:
            return f"Lỗi khi chạy {block.name}: {e}"
