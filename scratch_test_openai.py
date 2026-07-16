import os
import asyncio
from openai import AsyncOpenAI


async def test():
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        res = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say hello!"}],
            max_tokens=10
        )
        print("SUCCESS:", res.choices[0].message.content)
    except Exception as e:
        print("ERROR:", type(e), e)

asyncio.run(test())
