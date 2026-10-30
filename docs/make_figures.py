"""生成技术文档配图 (Pillow 手绘, 与产品视觉统一)。"""
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig")
os.makedirs(OUT, exist_ok=True)

NAVY = (31, 78, 216)
NAVY_D = (23, 55, 150)
INK = (24, 32, 51)
GRAY = (92, 107, 133)
GRAY_L = (233, 237, 245)
BG = (246, 248, 252)
WHITE = (255, 255, 255)
GREEN = (39, 174, 96)
AMBER = (243, 156, 18)
RED = (231, 76, 60)
TEAL = (47, 151, 176)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def font(size, bold=False):
    for p in ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def canvas(w, h, bg=BG):
    img = Image.new("RGB", (w, h), bg)
    return img, ImageDraw.Draw(img)


def box(d, xy, fill=WHITE, outline=GRAY_L, r=16, width=2):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def text(d, xy, s, size=24, color=INK, bold=False, anchor="la"):
    d.text(xy, s, font=font(size, bold), fill=color, anchor=anchor)


def arrow(d, p1, p2, color=NAVY, width=3, head=12):
    d.line([p1, p2], fill=color, width=width)
    (x1, y1), (x2, y2) = p1, p2
    if abs(x2 - x1) > abs(y2 - y1):
        sign = 1 if x2 > x1 else -1
        d.polygon([(x2, y2), (x2 - head * sign, y2 - head // 2), (x2 - head * sign, y2 + head // 2)], fill=color)
    else:
        sign = 1 if y2 > y1 else -1
        d.polygon([(x2, y2), (x2 - head // 2, y2 - head * sign), (x2 + head // 2, y2 - head * sign)], fill=color)


# ---------------------------------------------------------------- 图1 分层架构
def fig_architecture():
    W, H = 1680, 1040
    img, d = canvas(W, H)
    layers = [
        ("接入层", "Web 控制台 · APP · IM 渠道（纯文本确认）", "统一归一化: 文本输入 / 身份上下文 / 会话", (79, 138, 230)),
        ("智能体层", "意图理解 → 任务规划(DAG) → 权限分级 → 执行引擎", "支持模糊表达、省略指代、中断 / 回退 / 人工接管", NAVY),
        ("能力层", "工具注册表 24+ 能力，唯一可触达账本的入口", "每个工具返回结构化「事实集」，供幻觉防护校验", TEAL),
        ("数据层", "模拟银行账本：账户 / 流水 / 卡片 / 订阅 / 理财 / 日历", "生产环境替换为银行核心系统适配层", (100, 116, 139)),
    ]
    top, lh, gap = 70, 190, 26
    for i, (name, desc, sub, color) in enumerate(layers):
        y = top + i * (lh + gap)
        box(d, (70, y, 1210, y + lh), fill=WHITE, outline=GRAY_L, r=18, width=2)
        d.rounded_rectangle((70, y, 82, y + lh), radius=6, fill=color)
        d.ellipse((110, y + 22, 150, y + 62), fill=color)
        text(d, (130, y + 42), str(i + 1), size=22, color=WHITE, bold=True, anchor="mm")
        text(d, (176, y + 30), name, size=34, color=INK, bold=True)
        text(d, (176, y + 86), desc, size=22, color=GRAY)
        text(d, (176, y + 128), sub, size=19, color=(148, 163, 184))
        if i < len(layers) - 1:
            arrow(d, (640, y + lh + 4), (640, y + lh + gap - 4), color=(203, 213, 225), width=3, head=10)

    # 右侧: 安全底座
    sx1, sx2 = 1250, 1610
    box(d, (sx1, top, sx2, top + 4 * lh + 3 * gap), fill=(240, 245, 255), outline=(199, 216, 250), r=18, width=2)
    text(d, ((sx1 + sx2) // 2, top + 40), "安全底座", size=30, color=NAVY_D, bold=True, anchor="mm")
    text(d, ((sx1 + sx2) // 2, top + 74), "横切所有层", size=17, color=GRAY, anchor="mm")
    items = [("注入防御", "归一化 + 规则拦截"), ("幻觉防护", "回复金额比对事实集"),
             ("操作审计", "哈希链存证"), ("异常熔断", "连续失败即锁定"),
             ("代码沙箱", "AST 白名单")]
    y = top + 108
    for name, sub in items:
        box(d, (sx1 + 24, y, sx2 - 24, y + 86), fill=WHITE, outline=(214, 226, 250), r=12, width=1)
        d.ellipse((sx1 + 40, y + 32, sx1 + 56, y + 48), fill=NAVY)
        text(d, (sx1 + 68, y + 22), name, size=22, color=INK, bold=True)
        text(d, (sx1 + 68, y + 54), sub, size=15, color=GRAY)
        y += 100
    img.save(os.path.join(OUT, "fig1_architecture.png"), dpi=(200, 200))


# ---------------------------------------------------------------- 图2 请求链路
def fig_pipeline():
    W, H = 1680, 720
    img, d = canvas(W, H)
    steps = [
        ("① 注入检测", "归一化 + 11 条规则\n先于任何模型调用", RED),
        ("② 意图理解", "规则引擎 / LLM 增强\n槽位补全 · 指代消解", NAVY),
        ("③ 任务规划", "编译为 DAG\n节点=工具调用", NAVY),
        ("④ 权限分级", "绿 / 黄 / 红\n确定性代码判定", AMBER),
        ("⑤ 分级执行", "自动 · 确认 · 强验证\n失败逆序回滚", (79, 138, 230)),
        ("⑥ 事实校验", "金额/尾号\n比对工具返回", TEAL),
        ("⑦ 审计落盘", "哈希链\n全链路可追溯", (100, 116, 139)),
    ]
    bw, bh, gap = 200, 190, 26
    x0 = (W - (bw * 7 + gap * 6)) // 2
    y0 = 130
    for i, (title, sub, color) in enumerate(steps):
        x = x0 + i * (bw + gap)
        box(d, (x, y0, x + bw, y0 + bh), fill=WHITE, outline=GRAY_L, r=16, width=2)
        d.rounded_rectangle((x, y0, x + bw, y0 + 56), radius=16, fill=color)
        d.rectangle((x, y0 + 40, x + bw, y0 + 56), fill=color)
        text(d, (x + bw // 2, y0 + 28), title, size=21, color=WHITE, bold=True, anchor="mm")
        text(d, (x + bw // 2, y0 + 92), sub.split("\n")[0], size=16, color=GRAY, anchor="mm")
        if len(sub.split("\n")) > 1:
            text(d, (x + bw // 2, y0 + 120), sub.split("\n")[1], size=16, color=GRAY, anchor="mm")
        if i < 6:
            arrow(d, (x + bw + 3, y0 + bh // 2), (x + bw + gap - 3, y0 + bh // 2), color=(203, 213, 225), width=3, head=10)
    # 关键拦截说明
    marks = [(0, "拒绝执行并计数", RED), (3, "确认卡 / 多因子", AMBER), (5, "不通过则重写回复", TEAL)]
    for idx, label, color in marks:
        x = x0 + idx * (bw + gap) + bw // 2
        text(d, (x, y0 + bh + 34), label, size=17, color=color, bold=True, anchor="ma")
    text(d, (W // 2, y0 + bh + 92), "绿色=自动执行   黄色=用户确认   红色=强验证（人脸/短信/U盾）", size=18, color=GRAY, anchor="ma")
    img.save(os.path.join(OUT, "fig2_pipeline.png"), dpi=(200, 200))


# ---------------------------------------------------------------- 图3 权限矩阵
def fig_tiers():
    W, H = 1680, 900
    img, d = canvas(W, H)
    cards = [
        ("绿色 · 自动执行", GREEN, (236, 253, 245), "Agent 确认意图后直接执行",
         ["余额 / 流水 / 账单分析", "异常交易识别", "理财查询 · 收益试算 · 产品对比", "订阅清单 · 卡片信息 · 日历",
          "可支配资金测算"], "无需二次确认"),
        ("黄色 · 用户确认", AMBER, (255, 250, 235), "执行前展示完整操作详情",
         ["小额转账（日累计 ≤ 1000 元）", "AA 收款 · 预约下单", "取消订阅 · 虚拟卡/实体卡申请", "交易限额调整 · 理财赎回",
          "锁定活期资金"], "逐项确认后才执行"),
        ("红色 · 强验证", RED, (254, 243, 242), "多因子认证通过后才执行",
         ["大额转账（日累计 > 1000 元）", "理财产品申购", "卡片挂失 / 解挂", "信用卡额度调整", "登录密码 / 支付密码修改"],
         "人脸识别 · 短信验证码 · U 盾"),
    ]
    cw, ch, gap = 500, 700, 40
    x0 = (W - (cw * 3 + gap * 2)) // 2
    y0 = 100
    for i, (title, color, light, sub, items, foot) in enumerate(cards):
        x = x0 + i * (cw + gap)
        box(d, (x, y0, x + cw, y0 + ch), fill=WHITE, outline=GRAY_L, r=20, width=2)
        d.rounded_rectangle((x, y0, x + cw, y0 + 128), radius=20, fill=light)
        d.rectangle((x, y0 + 108, x + cw, y0 + 128), fill=light)
        d.ellipse((x + 34, y0 + 40, x + 62, y0 + 68), fill=color)
        text(d, (x + 78, y0 + 36), title, size=27, color=INK, bold=True)
        text(d, (x + 34, y0 + 82), sub, size=17, color=GRAY)
        y = y0 + 168
        for it in items:
            d.ellipse((x + 36, y + 10, x + 46, y + 20), fill=color)
            text(d, (x + 60, y), it, size=18, color=INK)
            y += 46
        d.line([(x + 34, y0 + ch - 130), (x + cw - 34, y0 + ch - 130)], fill=GRAY_L, width=2)
        text(d, (x + cw // 2, y0 + ch - 96), "执行策略", size=15, color=GRAY, anchor="ma")
        text(d, (x + cw // 2, y0 + ch - 62), foot, size=19, color=color, bold=True, anchor="ma")
    text(d, (W // 2, H - 44), "阈值写入代码常量，模型无法通过对话修改（fail-closed：未登记动作按红色处理）",
         size=19, color=GRAY, anchor="ma")
    img.save(os.path.join(OUT, "fig3_tiers.png"), dpi=(200, 200))


# ---------------------------------------------------------------- 图4 DAG
def fig_dag():
    W, H = 1680, 760
    img, d = canvas(W, H)
    nodes = [
        ("n1", "账单分析", "近 30 天支出分类", 0, 1, GREEN),
        ("n2", "异常识别", "定位重复扣款商户", 1, 1, GREEN),
        ("n3", "订阅定位", "匹配可疑自动续费", 2, 1, GREEN),
        ("n4", "取消续费", "仅停该项服务", 3, 1, AMBER),
    ]
    bw, bh = 300, 130
    gapx = (W - 160 - bw * 4) // 3
    y = 260
    pos = {}
    for nid, title, sub, col, row, color in nodes:
        x = 80 + col * (bw + gapx)
        pos[nid] = (x, y, bw, bh)
        box(d, (x, y, x + bw, y + bh), fill=WHITE, outline=GRAY_L, r=16, width=2)
        d.rounded_rectangle((x, y, x + 8, y + bh), radius=4, fill=color)
        text(d, (x + 30, y + 30), title, size=25, color=INK, bold=True)
        text(d, (x + 30, y + 76), sub, size=17, color=GRAY)
        text(d, (x + bw - 20, y + 20), "绿" if color == GREEN else "黄", size=17, color=color, bold=True, anchor="ra")
    for a, b in (("n1", "n2"), ("n2", "n3"), ("n3", "n4")):
        x1, y1, w1, h1 = pos[a]
        x2, y2, w2, h2 = pos[b]
        arrow(d, (x1 + w1 + 4, y1 + h1 // 2), (x2 - 4, y2 + h2 // 2), color=(203, 213, 225), width=3, head=10)
    text(d, (W // 2, 90), "任务 DAG：节点 = 一次工具调用，边 = 数据依赖", size=27, color=INK, bold=True, anchor="ma")
    text(d, (W // 2, 136), "引擎按拓扑序执行；前置失败则后继跳过，已执行动作逆序回滚", size=18, color=GRAY, anchor="ma")
    # 说明块
    box(d, (80, 470, W - 80, 660), fill=(248, 250, 253), outline=GRAY_L, r=14, width=1)
    notes = [
        "· 支持并行分支：无依赖的节点可同时展开（如生日方案中的订鲜花 / 订蛋糕）",
        "· 支持中断与回退：暂停保留计划；失败或用户撤销时执行补偿动作（冲正 / 恢复订阅）",
        "· 支持人工接管：接管期间连绿色动作也需坐席逐笔确认",
    ]
    yy = 500
    for n in notes:
        text(d, (110, yy), n, size=19, color=GRAY)
        yy += 46
    img.save(os.path.join(OUT, "fig4_dag.png"), dpi=(200, 200))


# ---------------------------------------------------------------- 图5 五道防线
def fig_defense():
    W, H = 1680, 760
    img, d = canvas(W, H)
    rows = [
        ("注入防御", "全角/零宽归一化 → 11 条注入模式匹配 → 命中即拒绝并计入熔断", RED, "96%"),
        ("幻觉防护", "回复后置校验：金额、卡号尾号必须存在于工具返回的事实集", (192, 132, 252), "100%"),
        ("操作审计", "input→nlu→plan→policy→tool→mfa→guard 全链路，逐条哈希链接", NAVY, "全量"),
        ("异常熔断", "连续 3 次失败或 2 次注入尝试 → 锁定 5 分钟，期间拒绝办理", AMBER, "5min"),
        ("代码沙箱", "AST 白名单：禁属性访问/导入/赋值，仅允许算术与内置纯函数", TEAL, "0 逃逸"),
    ]
    y = 90
    for name, desc, color, tag in rows:
        box(d, (80, y, W - 80, y + 108), fill=WHITE, outline=GRAY_L, r=14, width=2)
        d.rounded_rectangle((80, y, 90, y + 108), radius=4, fill=color)
        d.ellipse((116, y + 34, 156, y + 74), fill=color)
        text(d, (136, y + 54), "✓", size=22, color=WHITE, bold=True, anchor="mm")
        text(d, (176, y + 26), name, size=26, color=INK, bold=True)
        text(d, (176, y + 66), desc, size=18, color=GRAY)
        box(d, (W - 240, y + 34, W - 110, y + 74), fill=(248, 250, 253), outline=GRAY_L, r=20, width=1)
        text(d, (W - 175, y + 54), tag, size=19, color=color, bold=True, anchor="mm")
        y += 126
    text(d, (W // 2, H - 40), "五道防线均为独立于模型的确定性代码：模型输出被当作不可信输入处理",
         size=19, color=GRAY, anchor="ma")
    img.save(os.path.join(OUT, "fig5_defense.png"), dpi=(200, 200))


if __name__ == "__main__":
    fig_architecture()
    fig_pipeline()
    fig_tiers()
    fig_dag()
    fig_defense()
    for f in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, f)
        print(f"{f}: {os.path.getsize(p)//1024} KB")
