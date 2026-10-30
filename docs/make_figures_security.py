"""安全自评报告配图：分级判定流程图 + 已知风险矩阵。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_figures import (AMBER, BG, GRAY, GRAY_L, GREEN, INK, NAVY, OUT, RED, TEAL,
                          WHITE, arrow, box, canvas, font, text)

from PIL import ImageDraw


def fig_tier_flow():
    W, H = 1680, 980
    img, d = canvas(W, H)

    # 起点
    box(d, (60, 60, 420, 180), fill=WHITE, outline=GRAY_L, r=14)
    text(d, (240, 92), "输入", size=20, color=GRAY, anchor="ma")
    text(d, (240, 126), "动作 action + 参数 args", size=20, color=INK, bold=True, anchor="ma")
    arrow(d, (420, 120), (500, 120))

    # 判定 1: 是否金额类
    box(d, (500, 55, 900, 185), fill=(240, 245, 255), outline=(199, 216, 250), r=14)
    text(d, (700, 90), "① 是否金额类动作", size=21, color=NAVY, bold=True, anchor="ma")
    text(d, (700, 130), "transfer / split_aa 等", size=18, color=GRAY, anchor="ma")

    # 分支 A: 是 -> 动态判定
    arrow(d, (900, 120), (980, 120))
    text(d, (940, 92), "是", size=17, color=GREEN, bold=True, anchor="ma")
    box(d, (980, 40, 1420, 205), fill=(255, 250, 235), outline=(245, 226, 184), r=14)
    text(d, (1200, 66), "② 计算投影金额", size=20, color=INK, bold=True, anchor="ma")
    text(d, (1200, 100), "projected = 今日累计 + 本次 × 人数", size=17, color=GRAY, anchor="ma")
    text(d, (1200, 136), "③ 与阈值比较（1000 元）", size=20, color=INK, bold=True, anchor="ma")
    text(d, (1200, 170), "单笔 ≥ 5000 追加人工复核标记", size=16, color=GRAY, anchor="ma")

    # 分支 B: 否 -> 静态表
    arrow(d, (700, 185), (700, 300))
    text(d, (726, 232), "否", size=17, color=GRAY, bold=True)
    box(d, (500, 300, 900, 430), fill=WHITE, outline=GRAY_L, r=14)
    text(d, (700, 334), "② 查静态分级表", size=21, color=NAVY, bold=True, anchor="ma")
    text(d, (700, 372), "查询 / 状态变更 / 资金凭据", size=18, color=GRAY, anchor="ma")

    # 未登记 -> fail closed（放在静态表左侧，避免与其它连线交叉）
    d.line([(500, 365), (448, 365)], fill=(203, 213, 225), width=3)
    arrow(d, (448, 365), (444, 365), color=(203, 213, 225), width=3, head=10)
    box(d, (80, 305, 444, 425), fill=(254, 243, 242), outline=(246, 208, 204), r=12)
    text(d, (262, 332), "未登记动作", size=19, color=RED, bold=True, anchor="ma")
    text(d, (262, 368), "一律判红 fail-closed", size=16, color=RED, anchor="ma")

    # 汇合 -> 三档输出
    outs = [
        (GREEN, (236, 253, 245), "绿色 · 自动执行", "查询类，直接返回结果", 320),
        (AMBER, (255, 250, 235), "黄色 · 用户确认", "展示详情 → 用户确认 → 执行", 680),
        (RED, (254, 243, 242), "红色 · 强验证", "人脸 / 短信 / U 盾 → 执行", 1040),
    ]
    y = 660
    for color, light, title, desc, x in outs:
        box(d, (x, y, x + 320, y + 150), fill=light, outline=color, r=14, width=2)
        d.ellipse((x + 24, y + 22, x + 48, y + 46), fill=color)
        text(d, (x + 60, y + 18), title, size=21, color=INK, bold=True)
        text(d, (x + 24, y + 70), desc, size=17, color=GRAY)
        text(d, (x + 24, y + 106), "判定记录写入审计链", size=15, color=GRAY)

    # 汇合线：动态分支（x=1200）与静态分支（x=700）下探到 y=620 后横向汇合
    d.line([(1200, 205), (1200, 620)], fill=(203, 213, 225), width=3)
    d.line([(700, 430), (700, 620)], fill=(203, 213, 225), width=3)
    d.line([(480, 620), (1200, 620)], fill=(203, 213, 225), width=3)
    for x in (480, 840, 1200):
        arrow(d, (x, 620), (x, 658), color=(203, 213, 225), width=3, head=10)

    # 底部原则
    box(d, (60, 860, 1620, 960), fill=(248, 250, 253), outline=GRAY_L, r=12, width=1)
    text(d, (840, 880), "判定全程不读模型输出：action 与 args 来自工具调用参数，阈值来自代码常量（app/config.py）",
         size=18, color=GRAY, anchor="ma")
    text(d, (840, 916), "任何分支的结论都必须落库可查；绕过判定的唯一方式是修改代码，而代码受版本管理与评审",
         size=18, color=GRAY, anchor="ma")

    img.save(os.path.join(OUT, "fig6_tier_flow.png"), dpi=(200, 200))


def fig_risk_matrix():
    W, H = 1500, 1000
    img, d = canvas(W, H)

    # 绘图区
    left, top, right, bottom = 200, 120, 1380, 820
    d.rectangle((left, top, right, bottom), fill=WHITE, outline=GRAY_L, width=2)

    # 三档底色：严格按「可能性 + 影响」计算风险分（0 最低 → 4 最高）
    from PIL import Image
    overlay = Image.new("RGB", (right - left, bottom - top), WHITE)
    od = ImageDraw.Draw(overlay)
    cell_w = (right - left) / 3
    cell_h = (bottom - top) / 3
    GREEN_Z, AMBER_Z, RED_Z = (236, 253, 245), (255, 250, 235), (254, 243, 242)
    for prow in range(3):          # 0=高可能, 2=低可能
        for pcol in range(3):      # 0=低影响, 2=高影响
            score = (2 - prow) + pcol
            fill = GREEN_Z if score <= 1 else (AMBER_Z if score <= 3 else RED_Z)
            od.rectangle((pcol * cell_w, prow * cell_h, (pcol + 1) * cell_w, (prow + 1) * cell_h),
                         fill=fill)
    img.paste(overlay, (left, top))
    d = ImageDraw.Draw(img)
    d.rectangle((left, top, right, bottom), outline=GRAY_L, width=2)

    # 轴标签
    text(d, ((left + right) / 2, bottom + 30), "影响程度  →", size=22, color=INK, bold=True, anchor="ma")
    text(d, (left + cell_w * 0.5, bottom + 70), "低", size=19, color=GRAY, anchor="ma")
    text(d, (left + cell_w * 1.5, bottom + 70), "中", size=19, color=GRAY, anchor="ma")
    text(d, (left + cell_w * 2.5, bottom + 70), "高", size=19, color=GRAY, anchor="ma")

    text(d, (left - 44, (top + bottom) / 2), "可能性  ↑", size=22, color=INK, bold=True, anchor="mm")
    for i, lab in enumerate(["高", "中", "低"]):
        text(d, (left - 62, top + cell_h * (i + 0.5)), lab, size=19, color=GRAY, anchor="mm")

    # 风险点：(编号, 名称, 行 0高/1中/2低, 列 0低/1中/2高, dx, dy)
    risks = [
        ("R3", "登录为界面级门禁", 0, 2, 0, 0),
        ("R1", "强验证为模拟通过", 0, 1, 0, 0),
        ("R2", "账本为模拟实现", 1, 2, 0, 0),
        ("R9", "注入规则库被新变体绕过", 1, 1, 96, -44),
        ("R5", "审计落本地文件", 1, 1, -96, 16),
        ("R4", "规则引擎表达覆盖有限", 1, 0, 0, 0),
        ("R6", "演示环境短信码回显", 2, 1, 0, 0),
        ("R7", "会话为内存态", 2, 0, 0, 0),
    ]
    level_color = {0: RED, 1: AMBER, 2: GREEN}
    for rid, label, prow, pcol, dx, dy in risks:
        cx = left + cell_w * (pcol + 0.5) + dx
        cy = top + cell_h * (prow + 0.5) + dy
        color = level_color[prow]
        d.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), fill=color)
        text(d, (cx, cy - 1), rid, size=17, color=WHITE, bold=True, anchor="mm")
        text(d, (cx, cy + 46), label, size=14, color=INK, anchor="ma")

    # 标题与副标题
    text(d, (W / 2, 34), "已知风险矩阵", size=27, color=INK, bold=True, anchor="ma")
    text(d, (W / 2, 72),
         "位置＝缓解前的「可能性 × 影响」　·　气泡颜色＝缓解后的残余等级",
         size=16, color=GRAY, anchor="ma")

    # 图例（右下）
    lx, ly = right - 380, bottom + 24
    for i, (color, label) in enumerate([(GREEN, "低残余"), (AMBER, "中残余"), (RED, "高残余")]):
        x = lx + i * 128
        d.ellipse((x, ly + 6, x + 16, ly + 22), fill=color)
        text(d, (x + 24, ly), label, size=15, color=GRAY)
    img.save(os.path.join(OUT, "fig7_risk_matrix.png"), dpi=(200, 200))


if __name__ == "__main__":
    fig_tier_flow()
    fig_risk_matrix()
    for f in ("fig6_tier_flow.png", "fig7_risk_matrix.png"):
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")
