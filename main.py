import random
from dataclasses import dataclass, field

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# 管理员 QQ —— 只有这个号能用 /rnrig 控制骰子
ADMIN_QQ = "1412219758"

USAGE = """🎲 骰子控制台用法(/rnrig):

【确定性控制】
  /rnrig <0-6>                       下一掷(任何人)固定为该数,一次性
  /rnrig keep <0-6> [times <N>]      持续固定,可限定 N 次后自动恢复
  /rnrig target <qq> <0-6>           指定 qq 的下一掷固定,一次性
  /rnrig target <qq> keep <0-6> [times <N>]   针对 qq 持续固定
  /rnrig target <qq> off             取消对 qq 的所有作弊

【随机约束】(未被上面命中时才生效)
  /rnrig range <min> <max>           随机只落在 [min, max]
  /rnrig norange                     清除范围限制
  /rnrig block <0-6> [<0-6>...]      永远不出这些数
  /rnrig unblock <0-6> [<0-6>...]    解除屏蔽
  /rnrig noblock                     清除所有屏蔽
  /rnrig bias <0-6> <1-100>          该数有指定百分比概率出现
  /rnrig nobias                      清除概率偏置

【管理】
  /rnrig status                      查看当前全部状态
  /rnrig off                         一键清空所有控制
  /rnrig help                        显示本帮助"""


@register(
    "random_number",
    "LuLu",
    "随机数插件,/rn 抽 0-6;管理员可用 /rnrig 细粒度控制骰子。",
    "1.2.0",
    "https://github.com/LuoH-AN/random_number",
)
class RandomNumberPlugin(Star):
    """发送 /rn 返回 0-6 的随机整数(含两端)。

    管理员(ADMIN_QQ)可用 /rnrig 全方位控制:
    定向受害者、数值范围、屏蔽数字、概率偏置、次数限制等。
    """

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.cfg = RigConfig()

    @filter.command("rn", alias={"随机数", "roll"})
    async def random_number(self, event: AstrMessageEvent):
        num = self.cfg.resolve(event.get_sender_id())
        yield event.plain_result(f"🎲 你抽到了:{num}")

    @filter.command("rnrig")
    async def rig(self, event: AstrMessageEvent):
        if event.get_sender_id() != ADMIN_QQ:
            yield event.plain_result("⛔ 此功能仅限管理员使用。")
            return
        args = _parse_args(event.message_str, "rnrig")
        yield event.plain_result(self.cfg.dispatch(args))


# --------------------------------------------------------------------------- #
#  控制台状态机
# --------------------------------------------------------------------------- #
@dataclass
class RigConfig:
    # 确定性控制
    force_next: int | None = None            # 全局一次性:下一掷 = n
    force_keep: int | None = None            # 全局持续:每一掷 = n
    keep_remaining: int | None = None        # 全局持续剩余次数,None = 无限
    target_next: dict = field(default_factory=dict)   # qq -> int (一次性)
    target_keep: dict = field(default_factory=dict)   # qq -> [int, remaining|None]
    # 随机约束
    blocked: set = field(default_factory=set)
    range_min: int | None = None
    range_max: int | None = None
    bias_num: int | None = None
    bias_pct: int = 0                        # 1-100

    # ----------------------------- 掷骰子 ----------------------------- #
    def resolve(self, sender_id: str) -> int:
        """按优先级解析本次掷骰结果,并消耗/递减一次性或计数控制。"""
        # 1. 定向一次性(最高优先级)
        if sender_id in self.target_next:
            return self.target_next.pop(sender_id)
        # 2. 全局一次性
        if self.force_next is not None:
            v, self.force_next = self.force_next, None
            return v
        # 3. 定向持续
        if sender_id in self.target_keep:
            entry = self.target_keep[sender_id]  # [val, remaining]
            val = entry[0]
            if entry[1] is not None:
                entry[1] -= 1
                if entry[1] <= 0:
                    del self.target_keep[sender_id]
            return val
        # 4. 全局持续
        if self.force_keep is not None:
            v = self.force_keep
            if self.keep_remaining is not None:
                self.keep_remaining -= 1
                if self.keep_remaining <= 0:
                    self.force_keep = None
                    self.keep_remaining = None
            return v
        # 5. 约束随机
        return self._random()

    def _random(self) -> int:
        # 概率偏置优先:命中则直接返回
        if self.bias_num is not None and self._in_scope(self.bias_num):
            if random.randint(1, 100) <= self.bias_pct:
                return self.bias_num
        candidates = [n for n in range(0, 7) if self._in_scope(n)]
        if not candidates:  # 全被屏蔽/超范围,降级为全域随机
            return random.randint(0, 6)
        return random.choice(candidates)

    def _in_scope(self, n: int) -> bool:
        if n in self.blocked:
            return False
        if self.range_min is not None and n < self.range_min:
            return False
        if self.range_max is not None and n > self.range_max:
            return False
        return True

    # ----------------------------- 命令分发 ----------------------------- #
    def dispatch(self, args: list[str]) -> str:
        if not args or args[0].lower() in ("status", "状态"):
            return self._status()

        cmd = args[0].lower()
        rest = args[1:]

        if cmd in ("off", "关", "reset", "清空"):
            return self._off()
        if cmd in ("help", "帮助", "?", "？"):
            return USAGE
        if cmd == "keep":
            return self._keep(rest)
        if cmd == "target":
            return self._target(rest)
        if cmd == "range":
            return self._range(rest)
        if cmd == "norange":
            self.range_min = self.range_max = None
            return "✅ 已清除范围限制,恢复 0-6 全域随机。"
        if cmd == "block":
            return self._block(rest)
        if cmd == "unblock":
            return self._unblock(rest)
        if cmd == "noblock":
            self.blocked.clear()
            return "✅ 已清除所有屏蔽数字。"
        if cmd == "bias":
            return self._bias(rest)
        if cmd == "nobias":
            self.bias_num = None
            self.bias_pct = 0
            return "✅ 已清除概率偏置。"
        if _is_num(cmd):
            self.force_next = int(cmd)
            return f"🎯 下一掷(任何人)= {self.force_next}(一次性)。"
        return USAGE

    # ----------------------------- 子命令实现 ----------------------------- #
    def _keep(self, rest: list[str]) -> str:
        if not rest or not _is_num(rest[0]):
            return "用法:/rnrig keep <0-6> [times <N>]"
        n = int(rest[0])
        times = _parse_times(rest, 1)
        if times == -1:
            return "用法:/rnrig keep <0-6> [times <N>](N 须为正整数)"
        self.force_keep = n
        self.keep_remaining = times  # None = 无限
        if times is not None:
            return f"🎯 接下来 {times} 掷(任何人)= {n},之后自动恢复随机。"
        return f"🎯 接下来每一掷(任何人)= {n},直到 /rnrig off。"

    def _target(self, rest: list[str]) -> str:
        if len(rest) < 2:
            return "用法:/rnrig target <qq> <0-6 | keep <0-6> [times <N>] | off>"
        qq = rest[0]
        if not qq.isdigit():
            return "QQ 号必须是数字。"
        sub = rest[1].lower()

        if sub in ("off", "取消"):
            self.target_next.pop(qq, None)
            self.target_keep.pop(qq, None)
            return f"✅ 已清除对 {qq} 的所有定向作弊。"

        if sub == "keep":
            if len(rest) < 3 or not _is_num(rest[2]):
                return "用法:/rnrig target <qq> keep <0-6> [times <N>]"
            n = int(rest[2])
            times = _parse_times(rest, 3)
            if times == -1:
                return "用法:/rnrig target <qq> keep <0-6> [times <N>](N 须为正整数)"
            self.target_keep[qq] = [n, times]
            if times is not None:
                return f"🎯 {qq} 接下来 {times} 掷 = {n}。"
            return f"🎯 {qq} 每一掷 = {n},直到 /rnrig target {qq} off。"

        if _is_num(sub):
            self.target_next[qq] = int(sub)
            return f"🎯 {qq} 的下一掷 = {sub}(一次性)。"
        return "用法:/rnrig target <qq> <0-6 | keep <0-6> | off>"

    def _range(self, rest: list[str]) -> str:
        if len(rest) < 2 or not _is_num(rest[0]) or not _is_num(rest[1]):
            return "用法:/rnrig range <min 0-6> <max 0-6>"
        lo, hi = int(rest[0]), int(rest[1])
        if lo > hi:
            lo, hi = hi, lo
        self.range_min, self.range_max = lo, hi
        return f"📊 随机范围已限制为 [{lo}, {hi}]。"

    def _block(self, rest: list[str]) -> str:
        added = []
        for a in rest:
            if _is_num(a) and int(a) not in self.blocked:
                self.blocked.add(int(a))
                added.append(a)
        if not added:
            return "未添加新屏蔽(参数需为 0-6 的整数)。"
        cur = " ".join(str(x) for x in sorted(self.blocked))
        return f"🚫 已屏蔽:{' '.join(added)}(当前屏蔽:{cur})"

    def _unblock(self, rest: list[str]) -> str:
        removed = []
        for a in rest:
            if _is_num(a) and int(a) in self.blocked:
                self.blocked.discard(int(a))
                removed.append(a)
        if not removed:
            return "未移除任何屏蔽。"
        return f"✅ 已解除屏蔽:{' '.join(removed)}"

    def _bias(self, rest: list[str]) -> str:
        if len(rest) < 2 or not _is_num(rest[0]) or not rest[1].isdigit():
            return "用法:/rnrig bias <0-6> <1-100>"
        n = int(rest[0])
        pct = max(1, min(100, int(rest[1])))
        self.bias_num = n
        self.bias_pct = pct
        return f"⚖️ {n} 的出现概率提升至 {pct}%(其余情况在范围内均匀随机)。"

    # ----------------------------- 状态/清空 ----------------------------- #
    def _status(self) -> str:
        lines = ["📊 当前骰子控制台状态:"]

        def fmt_target(qq, val, rem):
            return f"{qq} = {val}" + (f"(还剩 {rem} 次)" if rem is not None else "(持续)")

        if self.force_next is not None:
            lines.append(f"  • 全局一次性:下一掷 = {self.force_next}")
        if self.force_keep is not None:
            tail = f",还剩 {self.keep_remaining} 次" if self.keep_remaining is not None else ",持续"
            lines.append(f"  • 全局持续:每一掷 = {self.force_keep}{tail}")
        for qq, v in self.target_next.items():
            lines.append(f"  • 定向一次性:{qq} 下一掷 = {v}")
        for qq, entry in self.target_keep.items():
            lines.append(f"  • 定向持续:{fmt_target(qq, entry[0], entry[1])}")
        if self.range_min is not None:
            lines.append(f"  • 随机范围:[{self.range_min}, {self.range_max}]")
        if self.blocked:
            lines.append(f"  • 屏蔽数字:{sorted(self.blocked)}")
        if self.bias_num is not None:
            lines.append(f"  • 概率偏置:{self.bias_num} = {self.bias_pct}%")

        active = (
            self.force_next is not None
            or self.force_keep is not None
            or bool(self.target_next)
            or bool(self.target_keep)
            or self.range_min is not None
            or bool(self.blocked)
            or self.bias_num is not None
        )
        if not active:
            lines.append("  • (无任何控制,纯随机 0-6)")
        return "\n".join(lines)

    def _off(self) -> str:
        self.force_next = None
        self.force_keep = None
        self.keep_remaining = None
        self.target_next.clear()
        self.target_keep.clear()
        self.blocked.clear()
        self.range_min = self.range_max = None
        self.bias_num = None
        self.bias_pct = 0
        return "✅ 已清空全部控制,骰子恢复纯随机。"


# --------------------------------------------------------------------------- #
#  解析辅助
# --------------------------------------------------------------------------- #
def _parse_args(message_str: str, cmd_name: str) -> list[str]:
    """从消息文本中剥离命令名,返回参数列表。兼容带 / 和已剥离两种情况。"""
    raw = message_str.strip()
    low = raw.lower()
    for prefix in ("/" + cmd_name, cmd_name):
        if low.startswith(prefix):
            raw = raw[len(prefix):].strip()
            break
    return raw.split()


def _parse_times(rest: list[str], idx: int) -> int | None:
    """从 rest[idx] 起解析 'times <N>'。返回 None=未指定,-1=格式错误,正整数=次数。"""
    if len(rest) <= idx:
        return None
    if rest[idx].lower() != "times":
        return -1
    if idx + 1 >= len(rest) or not rest[idx + 1].isdigit() or int(rest[idx + 1]) <= 0:
        return -1
    return int(rest[idx + 1])


def _is_num(s: str) -> bool:
    """判断是否是 0-6 的整数。"""
    return s.isdigit() and 0 <= int(s) <= 6
