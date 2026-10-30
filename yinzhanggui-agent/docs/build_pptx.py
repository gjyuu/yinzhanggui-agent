"""生成答辩 PPT（10 分钟 / 12 页）。

设计遵循学术汇报规范：白底、单一无衬线字体、论点式标题、一页一图、正文 ≥20pt。
配图：docs/fig 下的自绘示意图 + docs/shot 下的产品截图。
"""
import os

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "fig")
SHOT = os.path.join(HERE, "shot")
OUT = os.path.join(HERE, "银掌柜-答辩PPT.pptx")

FONT = "微软雅黑"
NAVY = RGBColor(0x1F, 0x4E, 0x79)
BLUE = RGBColor(0x2E, 0x75, 0xB6)
INK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x5C, 0x6B, 0x85)
LIGHT = RGBColor(0x8A, 0x96, 0xAB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x1E, 0x7D, 0x4F)
AMBER = RGBColor(0xB4, 0x6A, 0x00)
RED = RGBColor(0xB0, 0x2A, 0x1F)

SW, SH = 13.333, 7.5
MARGIN = 0.62
TITLE_TOP = 0.42


def set_font(run, size=20, bold=False, color=INK):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rPr, qn(tag))
        el.set("typeface", FONT)


def textbox(slide, left, top, width, height, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    return tf


def title(slide, text, size=26):
    tf = textbox(slide, MARGIN, TITLE_TOP, SW - 2 * MARGIN, 1.15)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    p.line_spacing = 1.12
    set_font(p.add_run(), size=size, bold=True, color=NAVY) if False else None
    r = p.add_run()
    r.text = text
    set_font(r, size=size, bold=True, color=NAVY)


def bullets(slide, items, left, top, width, height, size=20, color=INK, gap=10):
    tf = textbox(slide, left, top, width, height)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = 1.3
        p.space_after = Pt(gap)
        pPr = p._pPr if p._pPr is not None else p._p.get_or_add_pPr()
        pPr.set("marL", str(Emu(Inches(0.28))))
        pPr.set("indent", str(-Emu(Inches(0.28))))
        bu = etree.SubElement(pPr, qn("a:buChar"))
        bu.set("char", "•")
        bu_font = etree.SubElement(pPr, qn("a:buFont"))
        bu_font.set("typeface", "Arial")
        r = p.add_run()
        r.text = item
        set_font(r, size=size, color=color)
    return tf


def note(slide, text, top=6.62, size=12):
    tf = textbox(slide, MARGIN, top, SW - 2 * MARGIN, 0.4)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    set_font(r, size=size, color=LIGHT)


def footer(slide, idx, total):
    tf = textbox(slide, MARGIN, 6.94, SW - 2 * MARGIN, 0.32)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "银掌柜 · 银行 AI 智能体　|　人工智能赛道 · 答辩汇报"
    set_font(r, size=10, color=LIGHT)
    tf2 = textbox(slide, SW - MARGIN - 1.0, 6.94, 1.0, 0.32)
    p2 = tf2.paragraphs[0]
    p2.alignment = PP_ALIGN.RIGHT
    r2 = p2.add_run()
    r2.text = f"{idx} / {total}"
    set_font(r2, size=10, color=LIGHT)


def picture(slide, filename, left, top, max_w, max_h, folder=FIG):
    path = os.path.join(folder, filename)
    w, h = Image.open(path).size
    scale = min(max_w / w, max_h / h)
    width, height = w * scale, h * scale
    left = left + (max_w - width) / 2
    top = top + (max_h - height) / 2
    return slide.shapes.add_picture(path, Inches(left), Inches(top), Inches(width), Inches(height))


def frame(slide, left, top, width, height, color=RGBColor(0xE3, 0xE8, 0xF0)):
    from pptx.enum.shapes import MSO_SHAPE
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                 Inches(width), Inches(height))
    shp.fill.background()
    shp.line.color.rgb = color
    shp.line.width = Pt(1)
    shp.adjustments[0] = 0.06
    return shp


def callout(slide, text, left, top, width, height=0.82, size=15):
    """关键结论条：浅蓝底 + 深蓝字，用于一句话点题。"""
    from pptx.enum.shapes import MSO_SHAPE
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                 Inches(width), Inches(height))
    shp.fill.solid()
    shp.fill.fore_color.rgb = RGBColor(0xEE, 0xF3, 0xFB)
    shp.line.color.rgb = RGBColor(0xD6, 0xE2, 0xF3)
    shp.line.width = Pt(0.75)
    shp.adjustments[0] = 0.12
    shp.text_frame.word_wrap = True
    shp.text_frame.margin_left = shp.text_frame.margin_right = Inches(0.14)
    shp.text_frame.margin_top = shp.text_frame.margin_bottom = Inches(0.04)
    shp.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = shp.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = text
    set_font(r, size=size, bold=False, color=NAVY)


def table(slide, headers, rows, left, top, width, col_ratios, size=15, header_size=15, row_h=0.42):
    n_rows = len(rows) + 1
    shape = slide.shapes.add_table(n_rows, len(headers), Inches(left), Inches(top),
                                   Inches(width), Inches(row_h * n_rows))
    tbl = shape.table
    total = sum(col_ratios)
    for i, ratio in enumerate(col_ratios):
        tbl.columns[i].width = Emu(int(Inches(width) * ratio / total))
    for j, head in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        cell.margin_left = cell.margin_right = Inches(0.1)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run()
        r.text = head
        set_font(r, size=header_size, bold=True, color=WHITE)
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 else RGBColor(0xF6, 0xF8, 0xFB)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            color = INK
            if val.startswith("红") or val.startswith("拦截"):
                color = RED
            elif val.startswith("黄"):
                color = AMBER
            elif val.startswith("绿"):
                color = GREEN
            r = p.add_run()
            r.text = str(val)
            set_font(r, size=size, color=color, bold=(j == 0))
    return tbl


# ================================================================ 各页
def s_title(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tf = textbox(s, MARGIN, 1.75, SW - 2 * MARGIN, 1.0)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "银掌柜 · 银行 AI 智能体"
    set_font(r, size=40, bold=True, color=NAVY)

    tf2 = textbox(s, MARGIN, 2.78, SW - 2 * MARGIN, 0.9)
    p2 = tf2.paragraphs[0]
    r2 = p2.add_run()
    r2.text = "让「说话就能办业务」在权限框架内真正落地"
    set_font(r2, size=26, color=BLUE)

    tf3 = textbox(s, MARGIN, 3.95, SW - 2 * MARGIN, 1.2)
    for i, line in enumerate(["人工智能赛道 · 银行 AI 智能体",
                              "答辩汇报 · 10 分钟"]):
        p = tf3.paragraphs[0] if i == 0 else tf3.add_paragraph()
        p.space_after = Pt(6)
        r = p.add_run()
        r.text = line
        set_font(r, size=18, color=GRAY)

    frame(s, MARGIN, 5.3, 5.4, 1.15)
    tf4 = textbox(s, MARGIN + 0.22, 5.48, 5.0, 0.85)
    p = tf4.paragraphs[0]
    r = p.add_run()
    r.text = "一句话，把银行办了"
    set_font(r, size=22, bold=True, color=NAVY)
    p2 = tf4.add_paragraph()
    r2 = p2.add_run()
    r2.text = "查询自动执行 · 动钱先确认 · 高风险强验证"
    set_font(r2, size=13, color=GRAY)

    note(s, "全部数据为虚构演示数据，不连接任何真实银行系统。", top=6.5)


def s_problem(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "瓶颈不在「能不能办」，而在「敢不敢让 AI 办」")
    bullets(s, [
        "手机银行完成一笔转账，平均要 3 步以上操作",
        "大模型已经能听懂需求，但它会编造、会被诱导、会越权",
        "银行业务真正稀缺的不是能力，而是可追责的边界",
    ], MARGIN, 1.95, 7.4, 3.6)
    frame(s, 8.5, 1.9, 4.2, 3.3)
    tf = textbox(s, 8.72, 2.12, 3.76, 2.9)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "核心问题"
    set_font(r, size=15, bold=True, color=BLUE)
    for line in ["AI 替客户动钱的那一刻，", "谁来决定这一笔该不该问、", "该问几遍、该验几道？"]:
        p = tf.add_paragraph()
        p.space_before = Pt(6)
        r = p.add_run()
        r.text = line
        set_font(r, size=18, color=INK)
    note(s, "来源：赛题背景描述（传统手机银行操作路径长、入口深）。")
    footer(s, idx, total)


def s_answer(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "我们的答案：能力交给模型，权限交给框架")
    rows = [
        ["能力交给模型", "模型只做理解与规划，不参与任何权限判定"],
        ["权限交给框架", "分级、校验、执行、审计全部由确定性代码完成"],
        ["失败即关闭", "不确定时选择不做：未登记动作按最高风险处理"],
        ["可解释可追溯", "每步决策可视化，全链路哈希链审计"],
    ]
    table(s, ["设计原则", "落地方式"], rows, MARGIN, 2.0, 12.1, [1, 2.2], size=18, header_size=18, row_h=0.78)
    tf = textbox(s, MARGIN, 6.05, 12.1, 0.5)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "一句话：模型永远是不可信输入，权限判定不读它的输出。"
    set_font(r, size=20, bold=True, color=BLUE)
    footer(s, idx, total)


def s_arch(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "安全底座横切四层架构，模型无权决定权限")
    picture(s, "fig1_architecture.png", MARGIN, 1.78, 7.15, 3.75)
    bullets(s, [
        "接入层：Web / APP / IM 归一化成同一请求",
        "智能体层：理解 → 规划 → 分级 → 编排",
        "能力层：24 项工具，唯一可触达账本的入口",
        "数据层：账本可整体替换为核心系统适配层",
        "安全底座：5 类机制，横切而非某一层",
    ], 7.95, 1.92, 4.75, 3.4, size=16, gap=11)
    callout(s, "关键：安全底座不是模型的一部分 —— 对话无法改变它。", MARGIN, 5.78, 7.15, size=14)
    note(s, "图 1　分层架构（自绘）", top=6.62)
    footer(s, idx, total)


def s_pipeline(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "一次请求穿过七个环节，其中三道是硬闸门")
    picture(s, "fig2_pipeline.png", MARGIN, 1.80, 7.15, 3.05)
    bullets(s, [
        "① 注入检测：11 类模式，命中即拒绝并计数",
        "② 理解：规则打分，可选 LLM 增强只补槽位",
        "③ 规划：编译成 DAG，节点是一次工具调用",
        "④ 分级闸门：绿自动 / 黄确认 / 红强验证",
        "⑥ 事实校验：金额对不上就整段重写回复",
    ], 7.95, 1.92, 4.75, 3.5, size=16, gap=11)
    callout(s, "任何一步失败 → 已执行动作逆序回滚，余额回到原点。", MARGIN, 5.72, 7.15, size=14)
    note(s, "图 2　七步执行链路（自绘）", top=6.62)
    footer(s, idx, total)


def s_understand(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "口语、省略、开放目标都能接住，任务被编译成图")
    picture(s, "fig4_dag.png", MARGIN, 1.80, 7.15, 3.20)
    bullets(s, [
        "「转 500 给他」→ 取上文联系人，标注指代来源",
        "「那个一直扣钱的」→ 按风险标记定位订阅",
        "「买辆车能拿多少」→ 实算可支配上限与缺口",
        "节点带权限等级；前置失败则后继跳过",
        "回退靠补偿动作：冲正 / 恢复订阅 / 撤销持仓",
    ], 7.95, 1.92, 4.75, 3.6, size=16, gap=11)
    callout(s, "不确定就澄清，不猜 —— 猜错的成本远高于多问一句。", MARGIN, 5.80, 7.15, size=14)
    note(s, "图 3　任务 DAG 与引擎能力（自绘）", top=6.62)
    footer(s, idx, total)


def s_tiers(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "权限按风险分级：小额确认、大额强验证、未知即最严")
    picture(s, "fig3_tiers.png", MARGIN, 1.78, 7.15, 3.85)
    bullets(s, [
        "27 项动作分级：绿 14 / 黄 8 / 红 5",
        "转账判定式：今日累计 + 本次金额 > 1000 → 红",
        "单笔 ≥ 5000 追加「人工复核」标记",
        "红档强制多因子：人脸 / 短信 / U 盾",
        "未登记动作一律按红色（fail-closed）",
    ], 7.95, 1.92, 4.75, 3.6, size=16, gap=11)
    callout(s, "阈值写在代码常量里，模型没有修改权限的接口。", MARGIN, 5.86, 7.15, size=14)
    note(s, "图 4　三级权限矩阵（自绘）", top=6.64)
    footer(s, idx, total)


def s_defense(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "五道确定性防线，让编造、越权、逃逸无处落脚")
    picture(s, "fig5_defense.png", MARGIN, 1.80, 7.15, 3.20)
    bullets(s, [
        "注入：归一化后匹配，含零宽/全角变体",
        "幻觉：回复里的金额必须存在于事实集",
        "审计：input→tool→mfa 全链路哈希链",
        "熔断：连续 3 次失败或 2 次注入即锁定 5 分钟",
        "沙箱：AST 白名单，属性访问与导入直接拒绝",
    ], 7.95, 1.92, 4.75, 3.6, size=16, gap=11)
    callout(s, "模型输出被当作不可信输入：五道防线全部读不到模型的「意见」。", MARGIN, 5.80, 7.15, size=14)
    note(s, "图 5　安全五道防线（自绘）", top=6.62)
    footer(s, idx, total)


def s_product(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "同一套引擎，两个视角：客户只看对话，风控才看引擎")
    picture(s, "landing.png", MARGIN, 1.80, 5.35, 2.95, folder=SHOT)
    picture(s, "console-confirm.png", 6.20, 1.80, 2.55, 3.05, folder=SHOT)
    bullets(s, [
        "客户视角：只有对话与自己的账户快照",
        "风控视角：任务 DAG、权限矩阵、审计日志",
        "确认卡列出收款人、金额、执行后余额、风控判定",
        "同一会话可切换视角，身份由登录选择器带入",
    ], 9.05, 1.92, 3.65, 3.2, size=16, gap=12)
    callout(s, "客户感知「简单」，监管要求「可解释」——同一套引擎，两种呈现。", MARGIN, 5.30, 12.1, size=15)
    note(s, "界面截图为作品真实运行截图（localhost:8000），非设计稿。", top=6.28)
    footer(s, idx, total)


def s_verify(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "验证不是口号：120 项自动化测试与 8 项安全自检全部通过")
    rows = [
        ["权限分级", "13 项", "三级判定、日累计升级、未知动作 fail-closed"],
        ["安全机制", "19 项", "注入（含零宽/全角）、幻觉、熔断、沙箱逃逸、审计篡改"],
        ["场景端到端", "26 项", "六大场景 + 中断 / 回退 / 人工接管"],
        ["事实校验", "20 项", "20 种常见说法断言「回复无无依据金额」"],
        ["接口与剧本", "17 项", "HTTP 接口、多渠道、15 步演示剧本回归"],
    ]
    table(s, ["测试层", "用例", "验证内容"], rows, MARGIN, 1.95, 12.1, [1.1, 0.7, 3.6], size=15, header_size=16, row_h=0.62)
    tf = textbox(s, MARGIN, 5.75, 12.1, 0.5)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "另：安全自检 8/8 通过（注入、越权、幻觉、沙箱、熔断、审计链）。"
    set_font(r, size=17, color=GRAY)
    footer(s, idx, total)


def s_conclusion(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "可解释的安全，才是可交付的智能")
    bullets(s, [
        "六个场景全覆盖，且都能在权限闸门下真实执行",
        "把「模型不可信」写进架构，而不是写进提示词",
        "验证可复现：pytest 120 passed，自检 8/8",
    ], MARGIN, 1.95, 7.6, 3.0, size=20, gap=14)
    frame(s, 8.45, 1.9, 4.25, 3.15)
    tf = textbox(s, 8.68, 2.12, 3.8, 2.75)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "诚实边界"
    set_font(r, size=15, bold=True, color=RED)
    for line in ["账本为模拟实现", "强验证为模拟通过", "登录为界面级门禁", "审计落本地文件"]:
        p = tf.add_paragraph()
        p.space_before = Pt(5)
        r = p.add_run()
        r.text = "· " + line
        set_font(r, size=15, color=INK)
    tf2 = textbox(s, MARGIN, 5.35, 12.1, 1.2)
    p = tf2.paragraphs[0]
    r = p.add_run()
    r.text = "下一步：接入核心系统适配层 · 对接行方强验证 SDK · 审计写入 WORM 存储"
    set_font(r, size=16, color=GRAY)
    p2 = tf2.add_paragraph()
    p2.space_before = Pt(10)
    r2 = p2.add_run()
    r2.text = "源码与文档：yinzhanggui-agent　|　联系方式：（待填）"
    set_font(r2, size=15, color=BLUE)
    footer(s, idx, total)


def s_refs(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title(s, "参考与素材说明", size=24)
    rows = [
        ["赛题要求", "人工智能赛道 · 银行 AI 智能体（组委会提供）", "—"],
        ["行业对标", "Revolut AIR：AI 银行助手公开介绍（赛题引用）", "赛题背景章节"],
        ["动画库许可", "GSAP Standard No-Charge License（2025-04-30 起商用免费）", "gsap.com/community/standard-license"],
        ["本文配图", "图 1–5 为本作品自绘示意图（docs/fig，Pillow 生成）", "本项目源代码"],
        ["界面截图", "本作品落地页与控制台真实截图（localhost:8000）", "本项目源代码"],
    ]
    table(s, ["类别", "内容", "出处 / 许可"], rows, MARGIN, 1.95, 12.1, [1.0, 4.4, 2.6], size=14, header_size=15, row_h=0.66)
    tf = textbox(s, MARGIN, 6.12, 12.1, 0.6)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "未使用第三方图片、字体下载或网络素材；演示数据全部虚构。"
    set_font(r, size=15, color=GRAY)
    footer(s, idx, total)


NOTES = {
    1: "0:00-0:25 开场：我是……，作品叫银掌柜，一句话，把银行办了。今天用十分钟讲清楚一件事——它为什么敢让 AI 替客户动钱。",
    2: "0:25-1:20 先立问题：手机银行的操作摩擦只是表象。真正的门槛是责任边界——AI 替客户动钱那一刻，谁决定该不该问、问几遍、验几道。",
    3: "1:20-2:10 给答案，也是全篇的题眼：能力交给模型，权限交给框架。模型只做理解与规划；分级、校验、执行、审计全在确定性代码里。",
    4: "2:10-3:10 架构：四层加一个横切的安全底座。请注意，安全底座不是模型的一部分，所以模型无法通过对话把自己变安全或变危险。",
    5: "3:10-4:10 一次请求穿过七步。三道硬闸门：① 注入检测，命中即拒绝；④ 分级闸门，决定是否需要确认；⑥ 事实校验，不通过就重写回复。",
    6: "4:10-5:10 理解与规划。口语、省略、开放目标都能接住；复杂需求编译成 DAG，节点是工具调用，边是数据依赖，失败可逆序回滚。",
    7: "5:10-6:20 分级是这套系统的心脏：27 项动作，绿 14、黄 8、红 5。转账按今日累计加本次金额实时判定，超过 1000 元必须强验证。",
    8: "6:20-7:20 五道防线：注入、幻觉、审计、熔断、沙箱。全部是独立于模型的确定性代码——我们把模型输出当作不可信输入来处理。",
    9: "7:20-8:10 产品形态：同一套引擎，客户只看对话，风控视角才看 DAG、权限矩阵和审计日志。右边是真实界面：确认卡列出全部要素，红色动作要强验证。",
    10: "8:10-9:00 验证：120 项自动化测试、8 项安全自检全部通过。特别说一条——有一条回归测试专门盯「回复里不许出现无依据的金额」。",
    11: "9:00-9:40 结论：六个场景全覆盖，把模型不可信写进架构。右侧是我们主动交代的边界：账本模拟、强验证模拟、登录是界面级门禁、审计落本地。",
    12: "9:40-10:00 素材与许可说明，然后进入提问环节。",
}


def build():
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)
    total = 12

    s_title(prs)
    s_problem(prs, 2, total)
    s_answer(prs, 3, total)
    s_arch(prs, 4, total)
    s_pipeline(prs, 5, total)
    s_understand(prs, 6, total)
    s_tiers(prs, 7, total)
    s_defense(prs, 8, total)
    s_product(prs, 9, total)
    s_verify(prs, 10, total)
    s_conclusion(prs, 11, total)
    s_refs(prs, 12, total)

    for i, slide in enumerate(prs.slides, start=1):
        if i in NOTES:
            slide.notes_slide.notes_text_frame.text = NOTES[i]

    prs.save(OUT)
    print(f"saved: {OUT} ({os.path.getsize(OUT)//1024} KB, {len(prs.slides.__iter__.__self__._sldIdLst)} slides)")


if __name__ == "__main__":
    build()
