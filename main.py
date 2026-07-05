import random

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register


@register(
    "random_number",
    "LuLu",
    "随机数插件,发送 /rn 生成一个 0-6 的随机整数",
    "1.0.0",
    "https://github.com/LuLu/random_number",
)
class RandomNumberPlugin(Star):
    """发送 /rn 返回一个 0 到 6 之间的随机整数(含 0 和 6)。"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)

    @filter.command("rn", alias={"随机数", "roll"})
    async def random_number(self, event: AstrMessageEvent):
        num = random.randint(0, 6)
        yield event.plain_result(f"🎲 你抽到了:{num}")
