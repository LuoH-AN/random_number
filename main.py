import random

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# 管理员 QQ —— 只有这个号能用 /rnrig 控制骰子
ADMIN_QQ = "1412219758"


@register(
    "random_number",
    "LuLu",
    "随机数插件,发送 /rn 生成一个 0-6 的随机整数(管理员可用 /rnrig 控制结果)",
    "1.1.0",
    "https://github.com/LuoH-AN/random_number",
)
class RandomNumberPlugin(Star):
    """发送 /rn 返回一个 0 到 6 之间的随机整数(含 0 和 6)。

    管理员(ADMIN_QQ)可用 /rnrig 控制:
      /rnrig <0-6>      下一掷固定为该数(用一次后自动恢复随机)
      /rnrig keep <0-6> 持续固定为该数,直到关闭
      /rnrig off        取消所有控制,恢复随机
      /rnrig status     查看当前控制状态
    """

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self._force_next: int | None = None   # 一次性作弊(下一掷)
        self._force_keep: int | None = None   # 持续作弊(关掉前一直生效)

    @filter.command("rn", alias={"随机数", "roll"})
    async def random_number(self, event: AstrMessageEvent):
        # 一次性作弊优先消耗,其次看持续作弊,否则随机
        if self._force_next is not None:
            num = self._force_next
            self._force_next = None
        elif self._force_keep is not None:
            num = self._force_keep
        else:
            num = random.randint(0, 6)
        yield event.plain_result(f"🎲 你抽到了:{num}")

    @filter.command("rnrig")
    async def rig_roll(self, event: AstrMessageEvent):
        # 仅管理员可用
        if event.get_sender_id() != ADMIN_QQ:
            yield event.plain_result("⛔ 此功能仅限管理员使用。")
            return

        # 解析参数:去掉命令名(兼容带 / 和不带 /)
        raw = event.message_str.strip()
        low = raw.lower()
        for prefix in ("/rnrig", "rnrig"):
            if low.startswith(prefix):
                raw = raw[len(prefix):].strip()
                break
        args = raw.split()

        # /rnrig status  或无参数 → 查看状态
        if not args or args[0].lower() in ("status", "状态"):
            parts = ["📊 当前骰子状态:"]
            parts.append(
                f"  • 一次性作弊:{'第 ' + str(self._force_next) + ' 签' if self._force_next is not None else '无'}"
            )
            parts.append(
                f"  • 持续作弊:{'固定 ' + str(self._force_keep) if self._force_keep is not None else '无(正常随机)'}"
            )
            yield event.plain_result("\n".join(parts))
            return

        # /rnrig off → 关闭所有控制
        if args[0].lower() in ("off", "关", "取消"):
            self._force_next = None
            self._force_keep = None
            yield event.plain_result("✅ 已取消所有作弊,骰子恢复随机。")
            return

        # /rnrig keep <n> → 持续作弊
        if args[0].lower() == "keep":
            if len(args) < 2 or not _is_valid(args[1]):
                yield event.plain_result("用法:/rnrig keep <0-6>")
                return
            self._force_keep = int(args[1])
            yield event.plain_result(f"🎯 已持续作弊:接下来每一掷都是 {self._force_keep}。")
            return

        # /rnrig <n> → 一次性作弊
        if _is_valid(args[0]):
            self._force_next = int(args[0])
            yield event.plain_result(f"🎯 已作弊:下一掷将是 {self._force_next}(仅一次)。")
            return

        # 参数不合法
        yield event.plain_result(
            "用法:\n"
            "  /rnrig <0-6>      下一掷固定为该数\n"
            "  /rnrig keep <0-6> 持续固定为该数\n"
            "  /rnrig off        取消控制\n"
            "  /rnrig status     查看状态"
        )


def _is_valid(value: str) -> bool:
    """判断是否是 0-6 的整数。"""
    return value.isdigit() and 0 <= int(value) <= 6
