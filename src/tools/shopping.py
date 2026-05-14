"""Shopping search using Gemini Search Grounding (free, no SerpAPI)."""

from __future__ import annotations

import logging
import os

from google import genai
from google.genai import types

log = logging.getLogger("tara-bot.shopping")


def search_shopping(query: str) -> str:
    """Search and compare product prices online.

    Args:
        query: product name to search, e.g. "iPhone 16 256GB" or "laptop gaming 20 triệu"

    Returns:
        Formatted product listing with prices and sources
    """
    # Get API key directly from env to avoid any import issues
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.error("GEMINI_API_KEY not found in environment")
        return "⚠️ Không thể tìm kiếm: thiếu API key."

    log.info(f"search_shopping called with query: {query}")

    client = genai.Client(api_key=api_key)

    prompt = f"""Tìm giá sản phẩm "{query}" tại thị trường Việt Nam.

Yêu cầu:
- Liệt kê 5-8 kết quả từ các nguồn khác nhau (Thế Giới Di Động, CellphoneS, Shopee, Lazada, Tiki, FPT Shop, v.v.)
- Mỗi kết quả ghi rõ: tên sản phẩm, giá (VND), nguồn bán
- Sắp xếp từ rẻ nhất đến đắt nhất
- Ghi chú khuyến mãi nếu có
- Dùng emoji cho dễ đọc
- Cuối cùng đưa ra nhận xét ngắn gọn nên mua ở đâu
- KHÔNG dùng markdown formatting (không dùng *, **, _, [])"""

    try:
        log.info("Calling Gemini with google_search grounding...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
            ),
        )
        result = response.text or "Không tìm thấy kết quả."
        log.info(f"search_shopping result length: {len(result)}")
        return result
    except Exception as e:
        log.exception(f"Error in shopping search: {e}")
        return f"⚠️ Lỗi tìm kiếm giá: {e}"
