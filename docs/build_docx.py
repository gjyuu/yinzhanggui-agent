"""生成《银掌柜 · 银行 AI 智能体 技术文档》DOCX。"""
import os
from datetime import date

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "fig")
OUT = os.path.join(HERE, "银掌柜-技术文档.docx")

NAVY = RGBColor(0x1F, 0x33, 0x66)
BLUE = RGBColor(0x1F, 0x4E, 0xD8)
INK = RGBColor(0x18, 0x20, 0x33)
GRAY = RGBColor(0x5C, 0x6B, 0x85)
LIGHT = RGBColor(0x8A, 0x96, 0xAB)

CN_FONT = "微软雅黑"


# ---------------------------------------------------------------- 基础工具
def set_run(run, size=10.5, bold=False, color=INK, font=CN_FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)


def para(doc, text="", size=10.5, bold=False, color=INK, align=None,
         space_before=0, space_after=6, indent_first=None, line=1.45):
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(space_before)
    fmt.space_after = Pt(space_after)
    fmt.line_spacing = line
    if indent_first:
        fmt.first_line_indent = Pt(indent_first)
    if align is not None:
        p.alignment = align
    if text:
        set_run(p.add_run(text), size=size, bold=bold, color=color)
    return p


def heading(doc, text, level=1):
    sizes = {1: 16, 2: 13, 3: 11.5}
    colors = {1: NAVY, 2: NAVY, 3: BLUE}
    p = para(doc, text, size=sizes[level], bold=True, color=colors[level],
             space_before=16 if level == 1 else 10, space_after=8)
    p.style = doc.styles[f"Heading {level}"]
    for r in p.runs:
        set_run(r, size=sizes[level], bold=True, color=colors[level])
    return p


def bullet(doc, text, size=10.5, color=INK):
    p = doc.add_paragraph(style="List Bullet")
    fmt = p.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(3)
    fmt.line_spacing = 1.4
    fmt.left_indent = Cm(0.75)
    set_run(p.add_run(text), size=size, color=color)
    return p


def shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def table(doc, headers, rows, widths=None, size=9.5, header_fill="1F3366"):
    if widths:
        total = sum(widths)
        if total > 16.2:                      # 版心宽度 21 - 2.4*2 = 16.2cm
            widths = [w * 16.2 / total for w in widths]
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        set_run(p.add_run(h), size=size, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        shade(hdr[i], header_fill)
    for r in rows:
        cells = t.add_row().cells
        for i, val in enumerate(r):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.25
            set_run(p.add_run(str(val)), size=size)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def figure(doc, filename, caption, width=16.2):
    path = os.path.join(FIG, filename)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(4)
    p.add_run().add_picture(path, width=Cm(width))
    cap = para(doc, caption, size=9, color=LIGHT, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)
    return cap


def code(doc, lines):
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(4)
    fmt.space_after = Pt(8)
    fmt.left_indent = Cm(0.4)
    fmt.line_spacing = 1.15
    for i, line in enumerate(lines):
        run = p.add_run(line + ("\n" if i < len(lines) - 1 else ""))
        set_run(run, size=9, color=RGBColor(0x33, 0x3D, 0x52), font="Consolas")
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F4F6FA")
    pPr.append(shd)
    return p


def page_break(doc):
    doc.add_page_break()


def add_page_number(paragraph):
    run = paragraph.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    t = OxmlElement("w:t")
    t.text = "1"
    r = OxmlElement("w:r")
    r.append(t)
    fld.append(r)
    run._r.addnext(fld)


# ---------------------------------------------------------------- 文档
def build():
    doc = Document()

    # 页面设置
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.4)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = CN_FONT
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)

    # 页眉页脚
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run(hp.add_run("银掌柜 · 银行 AI 智能体　技术文档"), size=8.5, color=LIGHT)
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(fp.add_run("第 "), size=8.5, color=LIGHT)
    add_page_number(fp)
    set_run(fp.add_run(" 页"), size=8.5, color=LIGHT)

    # ============================== 封面
    for _ in range(4):
        para(doc, "", space_after=0)
    para(doc, "银掌柜", size=36, bold=True, color=NAVY, align=WD_ALIGN_PARAGRAPH.LEFT, space_after=2)
    para(doc, "银行 AI 智能体 · 技术文档", size=18, color=BLUE, space_after=6)
    para(doc, "系统架构 ／ 核心算法 ／ 安全设计", size=12, color=GRAY, space_after=28)

    t = table(doc, ["项目", "内容"], [
        ["作品名称", "银掌柜（YinZhangGui）· 银行 AI 智能体"],
        ["作品定位", "一句话，把银行办了：自然语言驱动、权限分级约束的银行业务智能体"],
        ["参赛赛道", "人工智能赛道 · 银行 AI 智能体"],
        ["文档版本", "v1.0"],
        ["文档日期", date.today().isoformat()],
        ["文档范围", "系统架构、核心算法、安全设计、工程实现、测试验证、已知局限"],
        ["配套材料", "源代码仓库（含 README / 部署说明 / 测试用例）、安全自评报告、答辩 PPT、演示视频"],
    ], widths=[3.2, 12.8], size=9.5)
    para(doc, "", space_after=20)
    para(doc, "本作品为参赛演示系统，账户、流水、联系人等数据均为虚构，不连接任何真实银行系统。",
         size=8.5, color=LIGHT)

    page_break(doc)

    # ============================== 目录
    para(doc, "目　录", size=18, bold=True, color=NAVY, space_after=14)
    toc = [
        ("一、作品概述", ["1.1 一句话定位", "1.2 三条设计原则", "1.3 场景覆盖", "1.4 关键指标"]),
        ("二、系统架构", ["2.1 分层架构", "2.2 单次请求的执行链路", "2.3 会话状态机", "2.4 多渠道一致性"]),
        ("三、核心算法说明", ["3.1 意图理解：规则引擎 + 可选 LLM 增强", "3.2 任务规划：DAG 编译与拓扑执行",
                            "3.3 权限分级：确定性判定", "3.4 幻觉防护：回复后置的事实校验",
                            "3.5 注入防御：归一化 + 模式匹配", "3.6 代码沙箱：AST 白名单",
                            "3.7 操作审计：哈希链", "3.8 异常熔断"]),
        ("四、安全设计", ["4.1 威胁模型与缓解措施", "4.2 权限矩阵", "4.3 强验证设计",
                        "4.4 五道防线总览", "4.5 降级与 fail-closed 路径", "4.6 已知风险与边界"]),
        ("五、工程实现", ["5.1 代码结构", "5.2 接口清单", "5.3 前端信息架构"]),
        ("六、测试与验证", ["6.1 测试分层", "6.2 安全自检", "6.3 演示剧本"]),
        ("七、局限与演进方向", []),
        ("附录 A　接口调用示例", []),
        ("附录 B　权限动作全表（27 项）", []),
    ]
    for title, subs in toc:
        para(doc, title, size=11.5, bold=True, color=NAVY, space_before=8, space_after=3)
        for s in subs:
            para(doc, s, size=10, color=GRAY, space_after=2).paragraph_format.left_indent = Cm(0.8)

    page_break(doc)

    # ============================== 一、概述
    heading(doc, "一、作品概述", 1)

    heading(doc, "1.1 一句话定位", 2)
    para(doc, "银掌柜是一个面向手机银行与 IM 渠道的 AI 智能体：用户用一句自然语言说出需求，"
              "系统自主理解意图、把复杂需求编译成任务 DAG，并在三级权限与多重安全机制的约束下完成真实业务操作。",
         indent_first=21)
    para(doc, "传统手机银行完成一笔转账平均需要 3 步以上操作；银掌柜把这条路径压缩为「一次对话」，"
              "同时用一个确定性的权限引擎保证：该自动的自动、该确认的确认、该强验证的绝不放过。",
         indent_first=21)

    heading(doc, "1.2 三条设计原则", 2)
    table(doc, ["原则", "含义", "落地方式"], [
        ["能力交给模型，权限交给框架",
         "模型只负责「理解与规划」，不参与任何权限判定",
         "权限分级、金额校验、执行与审计全部在确定性代码中完成（app/policy.py、app/executor.py）"],
        ["失败即关闭（fail-closed）",
         "不确定时选择「不做」，而不是「猜着做」",
         "未登记动作按红色处理；意图置信度不足时主动澄清；工具异常自动回滚"],
        ["可解释、可追溯",
         "每一步决策都要能讲清楚、查得到",
         "右侧面板展示 DAG 与权限判定；全链路哈希链审计；回复中的金额必须来自事实集"],
    ], widths=[4.4, 5.4, 6.6])

    heading(doc, "1.3 场景覆盖", 2)
    para(doc, "赛题要求至少覆盖 3 个核心场景，本作品实现全部 6 个，并额外扩展了目标规划类开放问题：", indent_first=21)
    table(doc, ["序号", "场景", "已实现能力"], [
        ["1", "智能转账", "按姓名 / 按手机号（含掩码与尾号）/ 备注 / 预约定时 / AA 拆分收款"],
        ["2", "账单分析", "消费分类统计、环比趋势、异常交易识别（重复扣款 / 凌晨交易 / 境外消费）、月度与年度报告"],
        ["3", "理财操作", "风险偏好匹配推荐、产品横向对比、收益试算（沙箱内计算）、申购、赎回"],
        ["4", "卡片管理", "卡片信息查询、额度调整、交易限额、挂失 / 解挂、虚拟卡与实体卡申请、密码修改"],
        ["5", "订阅代扣", "订阅清单、可疑扣费识别、3 天内扣费提醒、一键取消自动续费"],
        ["6", "跨场景联动", "生日 / 纪念日方案（鲜花 / 蛋糕 / 红包 / 锁定资金 / 其他安排）、配送地址确认、目标储蓄规划"],
        ["+", "目标规划（扩展）", "「我准备给我爱人买车，能拿出多少钱」「预算 120 万三年能攒够吗」等开放问题实算"],
    ], widths=[1.2, 3.2, 11.8])

    heading(doc, "1.4 关键指标", 2)
    table(doc, ["指标", "数值", "说明"], [
        ["权限动作分级", "27 项", "绿色 14 · 黄色 8 · 红色 5，含 1 项金额动态判定"],
        ["工具能力", "24+", "全部经工具注册表暴露，返回值携带结构化事实集"],
        ["自动化测试", "120 个", "覆盖意图、权限、安全、场景、多渠道、演示剧本、事实校验与 HTTP 接口"],
        ["安全自检", "8 项", "注入、越权、幻觉、沙箱逃逸、熔断、审计链、分级一致性"],
        ["演示剧本", "15 步", "前端一键演示 / 命令行重放 / 回归测试三处复用"],
    ], widths=[3.6, 2.4, 10.2])

    # ============================== 二、架构
    page_break(doc)
    heading(doc, "二、系统架构", 1)

    heading(doc, "2.1 分层架构", 2)
    para(doc, "系统分为接入层、智能体层、能力层、数据层四层，右侧「安全底座」以横切方式作用于所有层——"
              "它是独立于模型的确定性代码，而不是模型的一部分。", indent_first=21)
    figure(doc, "fig1_architecture.png", "图 1　银掌柜分层架构（安全底座横切全部层级）")

    table(doc, ["层级", "职责", "关键实现"], [
        ["接入层", "把 Web / APP / IM 的输入归一化为统一请求；承载身份与视角", "app/main.py、app/channels.py"],
        ["智能体层", "意图理解 → 任务规划 → 权限分级 → 执行编排", "app/nlu.py、planner.py、policy.py、executor.py"],
        ["能力层", "唯一可以触碰账本的接口集合，返回结构化事实集", "app/tools.py"],
        ["数据层", "账户 / 流水 / 卡片 / 订阅 / 理财 / 日历", "app/bank.py（生产环境替换为核心系统适配层）"],
        ["安全底座", "注入防御、幻觉防护、操作审计、异常熔断、代码沙箱", "app/security.py"],
    ], widths=[2.6, 8.2, 5.6])

    heading(doc, "2.2 单次请求的执行链路", 2)
    para(doc, "一次用户输入要穿过七个环节，其中三个是安全关卡（①⑥ 为硬拦截点，④ 为分级闸门）：", indent_first=21)
    figure(doc, "fig2_pipeline.png", "图 2　单次请求的七步执行链路")

    heading(doc, "2.3 会话状态机", 2)
    table(doc, ["状态", "含义", "可接受的下一步"], [
        ["idle / done", "空闲或已完成", "任意新指令"],
        ["clarify", "槽位不足，等待用户补充", "补充信息 / 放弃"],
        ["awaiting_confirm", "计划已生成，等待用户确认（黄/红）", "确认 / 取消 / 改口"],
        ["awaiting_mfa", "已下发强验证挑战，等待多因子", "提交验证码 / 放弃"],
        ["awaiting_choice", "跨场景方案待选（如生日安排）", "选择方案 / 说别的（自动释放上下文）"],
        ["paused", "用户主动暂停，计划保留", "继续 / 取消"],
        ["takeover", "人工接管，所有动作需坐席确认", "逐笔确认"],
        ["locked", "触发熔断，5 分钟内拒绝办理", "等待解锁（自动）"],
    ], widths=[3.0, 7.4, 6.0])

    heading(doc, "2.4 多渠道一致性", 2)
    para(doc, "Web、APP、IM 共用同一套执行引擎与风控链路，渠道差异只体现在交互形态上，"
              "不存在「换个渠道就能绕过验证」的路径。", indent_first=21)
    table(doc, ["渠道", "确认方式", "强验证方式", "实现"], [
        ["Web 控制台", "确认卡按钮", "弹窗选择人脸 / 短信 / U 盾", "web/app.js"],
        ["IM / APP", "回复「确认执行」「取消」", "回复 6 位短信验证码", "app/channels.py"],
    ], widths=[3.2, 5.2, 4.6, 3.4])

    # ============================== 三、核心算法
    page_break(doc)
    heading(doc, "三、核心算法说明", 1)
    para(doc, "本章按「理解 → 规划 → 分级 → 执行 → 校验」的顺序说明关键算法。所有算法都以确定性规则为骨架，"
              "大模型只在第 3.1 节作为可选增强项出现。", indent_first=21)

    heading(doc, "3.1 意图理解：规则引擎 + 可选 LLM 增强", 2)
    para(doc, "输入先做归一化（全角转半角、去零宽字符、折叠空白），再进入两级识别：", indent_first=21)
    para(doc, "第一级：正则规则打分。每个意图维护一组模式，命中数即得分；同分时按预定义优先级裁决"
              "（例如「理财产品有什么区别」必须命中对比而不是推荐）。", indent_first=21)
    para(doc, "第二级（可选）：若配置了大模型，用其输出参与意图与槽位补全，但只接受已知意图枚举；"
              "模型输出非法、超时或异常时静默降级为纯规则，不阻断主流程。", indent_first=21)
    para(doc, "槽位抽取覆盖金额（含「五百」「1.5 万」「一千五」等口语写法）、联系人（姓名 / 称谓 / 手机号掩码 / 尾号）、"
              "备注、时间词、品类偏好、目标金额与期限。", indent_first=21)
    code(doc, [
        "# 归一化 → 打分 → 语境修正 → 槽位抽取 → 指代消解",
        "score[intent] += 1   for each matched pattern",
        "if 命中「对比|区别」 and 命中「理财|产品」: compare += 4; 移除 recommend",
        "if 命中「生日|纪念日|礼物」:            event += 4; 移除 plan_goal",
        "intent = max(score, key=lambda k: (score[k], -priority.index(k)))",
        "if not score: return UNKNOWN          # 交给澄清, 不猜",
    ])
    para(doc, "指代与省略处理：当用户说「转 500 给他」时，从上文取联系人并标注「代词指代 → 上文联系人」；"
              "「把那个一直扣钱的关掉」则按风险标记自动定位可疑订阅，再交由用户确认。", indent_first=21)

    heading(doc, "3.2 任务规划：DAG 编译与拓扑执行", 2)
    para(doc, "意图被编译为有向无环图：节点是一次工具调用，边是数据依赖。执行器按拓扑序推进，"
              "前置节点失败则后继节点跳过，并对已执行动作逆序回滚。", indent_first=21)
    figure(doc, "fig4_dag.png", "图 3　任务 DAG 示例（订阅异常处置）与引擎能力")
    para(doc, "回滚采用补偿事务：转账 → 冲正入账，取消订阅 → 恢复订阅，申购 → 撤销持仓，"
              "额度调整 → 还原额度。补偿动作与正向动作一样写入审计链。", indent_first=21)

    heading(doc, "3.3 权限分级：确定性判定", 2)
    para(doc, "分级由静态动作表与金额动态规则共同决定，二者都写在代码常量里（app/policy.py、app/config.py）。", indent_first=21)
    figure(doc, "fig3_tiers.png", "图 4　三级权限矩阵与执行策略")
    para(doc, "金额类动作的判定式（单笔转账与日累计共用）：", indent_first=21)
    code(doc, [
        "projected = 今日累计转账 + 本次金额 × 收款人数量",
        "if 预约转账:      tier = RED if 单笔 > 1000 else YELLOW   # 不占用当日额度",
        "elif projected > 1000: tier = RED ;  review_flag = (单笔 >= 5000)",
        "else:             tier = YELLOW",
        "# 未登记动作 -> RED（fail-closed），并要求多因子",
    ])

    heading(doc, "3.4 幻觉防护：回复后置的事实校验", 2)
    para(doc, "每个工具返回 ToolResult 时都附带 facts（金额集合、卡号尾号集合、可校验文本行）。"
              "回复生成后，抽取其中的所有金额与尾号，逐个比对事实集；只要有一个对不上，"
              "整段回复会被替换为事实模板并记录告警。", indent_first=21)
    code(doc, [
        "allowed_amounts = {round(float(a), 2) for a in facts['amounts']}",
        "for token in MONEY_RE.findall(reply):        # 「12,846.50 元」「¥500」",
        "    if norm(token) not in allowed_amounts:",
        "        violations.append(token)",
        "if violations: reply = safe_template(facts); audit('guard', violations)",
    ])
    para(doc, "工程上还配了一条回归测试（tests/test_guard_coverage.py），对 20 种常见说法逐一断言"
              "「回复不含无依据金额」——历史上正是它抓到了「每月还差 32,031.43 元」这类派生数字漏登记的问题。",
         indent_first=21)

    heading(doc, "3.5 注入防御：归一化 + 模式匹配", 2)
    para(doc, "提示注入在进入任何模型调用之前就被拦截。检测前先做归一化，防止用全角、零宽字符或多余空白绕过匹配。",
         indent_first=21)
    code(doc, [
        "normalized = 全角→半角(text) | 去除\\u200b\\u200c\\u200d\\ufeff | 折叠空白",
        "hits = [label for pattern, label in PATTERNS if pattern.search(normalized)]",
        "if hits: 拒绝执行 → 计入熔断计数 → 审计(injection)",
        "        累计 2 次 → 会话锁定 5 分钟",
    ])
    para(doc, "模式库覆盖：覆盖既有指令、要求绕过风控、越狱关键词、特殊角色标记、身份伪造、"
              "篡改权限参数、诱导直接转账、要求关闭审计、角色伪装等 11 类表达。注意："
              "「把信用卡额度调到 3 万」这类**合法业务**不得误伤——它们由权限引擎按红色处理，而不是按攻击拦截。",
         indent_first=21)

    heading(doc, "3.6 代码沙箱：AST 白名单", 2)
    para(doc, "Agent 需要「算一笔」时（如收益试算），会生成表达式交给沙箱执行。沙箱不是黑名单过滤，"
              "而是语法树白名单：只允许算术、比较、条件表达式与有限内置函数，禁止属性访问、导入、赋值与循环。",
         indent_first=21)
    code(doc, [
        "ALLOWED = {Expression, BinOp, Constant, Name, Call, Compare, IfExp, ...}",
        "for node in ast.walk(tree):",
        "    if type(node) not in ALLOWED: raise SandboxError(type(node).__name__)",
        "env = {'__builtins__': {}} | {k: v for k, v in context.items()}",
        "return eval(compile(tree, '<sandbox>', 'eval'), env)",
    ])
    para(doc, "实测拒绝：__import__('os')、open(...)、().__class__.__bases__、列表推导与 exec 调用。", indent_first=21)

    heading(doc, "3.7 操作审计：哈希链", 2)
    para(doc, "每条审计记录包含 ts、trace_id、session、stage、summary 与业务字段，"
              "并额外保存前一条记录的哈希，形成可校验的链。任何一条被篡改，校验会在该条失配。", indent_first=21)
    code(doc, [
        "entry['prev'] = prev_hash",
        "entry['hash'] = sha256(canonical_json(entry) + prev_hash)[:16]",
        "prev_hash = entry['hash']",
        "verify(): 逐条重算, 返回 (ok, 首个失配下标)",
    ])

    heading(doc, "3.8 异常熔断", 2)
    para(doc, "熔断器按会话统计两类信号：连续失败次数与注入尝试次数。达到阈值即锁定，锁定期间所有请求直接拒绝，"
              "不做任何降级尝试。", indent_first=21)
    table(doc, ["信号", "阈值", "动作"], [
        ["连续失败（工具失败 / 强验证失败）", "3 次", "锁定 5 分钟"],
        ["注入尝试", "2 次", "锁定 5 分钟"],
        ["任意成功操作", "—", "失败计数清零"],
    ], widths=[7.0, 2.4, 6.8])

    # ============================== 四、安全设计
    page_break(doc)
    heading(doc, "四、安全设计", 1)

    heading(doc, "4.1 威胁模型与缓解措施", 2)
    table(doc, ["威胁", "攻击面", "缓解措施", "代码位置"], [
        ["提示注入 / 越狱", "用户输入", "归一化 + 11 类模式拦截 + 熔断", "security.InjectionGuard"],
        ["越权操作（让 AI 自己提权）", "对话内容", "权限判定不读模型输出；阈值硬编码", "policy.classify"],
        ["模型幻觉编造金额", "模型回复", "事实集比对 + 安全模板替换", "security.HallucinationGuard"],
        ["恶意代码执行", "生成式计算", "AST 白名单沙箱", "security.Sandbox"],
        ["绕过确认直接动钱", "交互流程", "服务端状态机：未确认不执行", "executor._advance"],
        ["重复提交 / 重放", "接口", "会话级幂等：确认后进入下一状态", "executor.confirm"],
        ["审计被篡改", "日志", "哈希链校验", "security.AuditLog"],
        ["连续试探", "整体", "连续失败与注入次数熔断", "security.CircuitBreaker"],
        ["数据越权（客户看到后台）", "前端", "视角隔离：客户视角隐藏 DAG/审计/权限面板", "web/console.css"],
    ], widths=[3.6, 2.8, 6.4, 4.0], size=9)

    heading(doc, "4.2 权限矩阵", 2)
    para(doc, "完整的 27 项动作分级见附录 B。三类执行策略对应三种交互形态：", indent_first=21)
    table(doc, ["级别", "判定依据", "执行策略", "典型动作"], [
        ["绿色", "纯查询类，不改变资金与账户状态", "自动执行，无需二次确认", "余额 / 流水 / 账单分析 / 理财查询与试算 / 日历"],
        ["黄色", "会改变账户或业务状态，但风险可控", "展示操作详情，用户确认后执行", "小额转账（日累计 ≤1000）、AA 收款、取消订阅、虚拟卡申请、理财赎回"],
        ["红色", "涉及资金安全或账户关键凭据", "多因子认证通过后执行", "大额转账（日累计 >1000）、理财申购、挂失/解挂、额度调整、改密码"],
    ], widths=[1.6, 4.6, 4.6, 6.0])

    heading(doc, "4.3 强验证设计", 2)
    bullet(doc, "挑战由服务端下发：challenge_id、可用方式、180 秒有效期、最多 3 次尝试。")
    bullet(doc, "三种方式：人脸识别、短信验证码（一次性、演示环境回显）、U 盾。")
    bullet(doc, "验证未通过前资金不发生任何变动；连续失败计入熔断。")
    bullet(doc, "超时后回到确认态，需要重新发起，不复用旧挑战。")

    heading(doc, "4.4 五道防线总览", 2)
    figure(doc, "fig5_defense.png", "图 5　安全五道防线")

    heading(doc, "4.5 降级与 fail-closed 路径", 2)
    table(doc, ["异常场景", "系统行为"], [
        ["大模型不可用 / 超时", "静默降级为规则引擎，功能不中断"],
        ["意图无法识别", "不猜，返回澄清并列出能力清单"],
        ["槽位不足（如缺金额）", "主动追问，不默认任何金额"],
        ["工具执行失败", "逆序回滚已执行动作，明确告知「没有产生未经确认的扣款」"],
        ["配置缺失", "未登记动作按红色处理，要求多因子"],
    ], widths=[6.0, 10.2])

    heading(doc, "4.6 已知风险与边界", 2)
    table(doc, ["编号", "已知风险", "当前处置", "生产化建议"], [
        ["R1", "人脸 / U 盾为模拟通过", "演示环境明确提示", "对接行方 SDK 与硬件密钥"],
        ["R2", "账户体系为演示账本", "数据全部虚构并标注", "接入核心系统，替换 app/bank.py"],
        ["R3", "前端登录为界面级门禁", "localStorage 判定，不伪装为安全鉴权", "网关层会话校验 + 服务端签名"],
        ["R4", "规则引擎覆盖有限表达", "超出口径主动澄清", "引入 LLM 增强 + 持续补充语料"],
        ["R5", "审计落本地 JSONL", "哈希链保证完整性", "写入 WORM 存储 / 集中审计平台"],
        ["R6", "多轮上下文仅保留最近联系人/金额", "不做长期记忆", "按合规要求设计记忆与遗忘策略"],
    ], widths=[1.2, 4.6, 5.0, 5.4], size=9)

    # ============================== 五、工程实现
    page_break(doc)
    heading(doc, "五、工程实现", 1)

    heading(doc, "5.1 代码结构", 2)
    table(doc, ["模块", "职责", "规模"], [
        ["app/main.py", "FastAPI 路由：对话、确认、强验证、审计、权限矩阵、自检、演示、看板", "≈220 行"],
        ["app/executor.py", "会话编排 + DAG 执行引擎（确认卡、强验证、暂停/回退/接管）", "≈600 行"],
        ["app/planner.py", "意图 → DAG 编译；确认卡字段描述", "≈420 行"],
        ["app/policy.py", "三级权限引擎与阈值判定", "≈200 行"],
        ["app/security.py", "注入防御 / 幻觉防护 / 熔断 / 沙箱 / 哈希链审计", "≈330 行"],
        ["app/nlu.py", "意图理解（规则 + LLM 增强）、槽位与指代", "≈520 行"],
        ["app/tools.py", "24+ 工具实现，返回结构化事实集", "≈700 行"],
        ["app/bank.py", "模拟银行账本", "≈600 行"],
        ["app/eventplan.py", "跨场景三步对话（方案 → 地址 → 下单）", "≈150 行"],
        ["app/channels.py", "多渠道归一化（Web / APP / IM）", "≈120 行"],
        ["app/demo.py", "15 步演示剧本（前端/字幕稿/回归三处复用）", "≈180 行"],
        ["app/selfcheck.py", "8 项安全自检", "≈180 行"],
        ["web/", "落地页、登录页、个人中心、控制台（原生 JS，无构建）", "≈2,400 行"],
        ["tests/", "120 个用例", "≈1,100 行"],
    ], widths=[3.8, 9.6, 2.8], size=9)

    heading(doc, "5.2 接口清单", 2)
    table(doc, ["方法", "路径", "说明"], [
        ["POST", "/api/chat", "对话主入口：{session_id, text} → 回复 + 计划 + 确认卡 + 审计"],
        ["POST", "/api/confirm", "确认或取消：{session_id, decision}"],
        ["POST", "/api/mfa/verify", "强验证：{session_id, method, code}"],
        ["POST", "/api/im/webhook", "IM / APP 渠道：{channel, user_id, text}"],
        ["GET", "/api/policy", "权限矩阵（前端与安全自评共用）"],
        ["GET", "/api/audit", "审计记录 + 哈希链校验"],
        ["GET", "/api/selfcheck", "8 项安全自检"],
        ["GET", "/api/demo/script", "演示剧本"],
        ["POST", "/api/demo/run", "服务端重放剧本"],
        ["GET", "/api/dashboard", "个人中心 / 落地页看板数据（scope=customer 为客户视角）"],
        ["GET/POST", "/api/session/{id}[/reset]", "会话快照 / 重置演示数据"],
    ], widths=[1.8, 5.6, 8.8], size=9)

    heading(doc, "5.3 前端信息架构", 2)
    para(doc, "前端按「受众」而非「功能」组织，避免客户看到后台概念：", indent_first=21)
    table(doc, ["页面", "受众", "内容"], [
        ["/ 落地页", "评委 / 公众", "产品定位、能力概览、可交互 Dashboard 预览（真实数据）"],
        ["/login、/register", "客户", "演示身份选择（客户 / 风控管理员）；注册界面存在但不可用（不做真实开户）"],
        ["/center 个人中心", "客户", "支出结构、账户洞察、操作安全等级、最近操作记录"],
        ["/app 控制台", "客户 / 风控", "客户视角仅对话；风控视角才显示任务 DAG、权限矩阵、审计日志"],
    ], widths=[3.4, 3.0, 9.8])

    # ============================== 六、测试
    page_break(doc)
    heading(doc, "六、测试与验证", 1)

    heading(doc, "6.1 测试分层", 2)
    table(doc, ["文件", "覆盖内容", "用例数"], [
        ["tests/test_nlu.py", "金额解析、模糊表达、指代消解、未知意图不臆测", "17"],
        ["tests/test_policy.py", "三级判定、日累计升级、边界值、未知动作 fail-closed", "13"],
        ["tests/test_security.py", "注入（含零宽/全角）、幻觉、熔断、沙箱逃逸、审计篡改", "19"],
        ["tests/test_scenarios.py", "六大场景端到端 + 中断/回退/接管/失败回滚", "26"],
        ["tests/test_channels.py", "IM 渠道文本确认、验证码、跨渠道不提权", "9"],
        ["tests/test_demo.py", "演示剧本 15 步逐步回归", "7"],
        ["tests/test_guard_coverage.py", "20 种常见说法断言「无无依据金额」", "20"],
        ["tests/test_api.py", "HTTP 接口、权限矩阵、自检、审计链、数据重置", "10"],
    ], widths=[5.0, 9.6, 1.6], size=9)
    para(doc, "执行：python -m pytest → 120 passed（约 1 秒）。", size=9.5, color=GRAY)

    heading(doc, "6.2 安全自检（/api/selfcheck）", 2)
    table(doc, ["编号", "探测项", "预期结果"], [
        ["1", "提示注入：要求忽略规则并直接转 9000 元", "拦截，余额不变"],
        ["2", "权限分级：1500 元转账", "进入红色强验证，不直接执行"],
        ["3", "权限分级：300 元转账", "黄色确认，确认前不扣款"],
        ["4", "幻觉防护：回复含无依据金额", "被拦截并替换为真实数据"],
        ["5", "代码沙箱：导入 os / 读取文件 / 类链逃逸", "三段全部拒绝"],
        ["6", "异常熔断：连续 3 次失败", "锁定 5 分钟"],
        ["7", "操作审计：哈希链完整性", "校验通过"],
        ["8", "黄色动作：确认后执行", "不触发多因素"],
    ], widths=[1.2, 9.4, 5.6], size=9)

    heading(doc, "6.3 演示剧本", 2)
    para(doc, "15 步剧本同时被前端「一键演示」、命令行 tools/demo.py 与回归测试复用，保证「演示所见 = 测试所验」。",
         indent_first=21)
    table(doc, ["步骤", "场景", "权限级别", "关键验证点"], [
        ["S1", "余额查询", "绿", "无需确认"],
        ["S2–S3", "小额 / 大额转账", "黄 / 红", "确认卡字段完整；强验证前余额不变"],
        ["S4–S6", "账单分析、异常识别、订阅取消", "绿 / 绿 / 黄", "分类占比、可疑扣款定位、指代消解"],
        ["S7–S8", "收益试算、理财申购", "绿 / 红", "沙箱内计算；申购需强验证"],
        ["S9–S9c", "跨场景方案 → 细节 → 地址确认", "绿 / 黄", "不替用户做主；地址未确认不下单"],
        ["S10–S11", "目标规划、产品对比", "绿", "可支配上限实算；逐项对比"],
        ["S12–S13", "撤销转账、注入攻击", "红 / 拦截", "冲正入账；余额不动、审计留痕"],
    ], widths=[1.8, 6.4, 2.2, 5.8], size=9)

    # ============================== 七、局限
    heading(doc, "七、局限与演进方向", 2)
    bullet(doc, "账户与资金为模拟账本；接入真实核心系统后，工具层与风控层无需改动。")
    bullet(doc, "强验证为模拟通过，生产环境需对接行方 SDK。")
    bullet(doc, "规则引擎覆盖常见表达，超出口径主动澄清（刻意的安全设计）。")
    bullet(doc, "未实现多租户与真实身份体系；当前以「演示身份」做视角隔离。")
    bullet(doc, "审计为本地文件；生产环境应写入 WORM 存储并接入集中审计平台。")

    # ============================== 附录
    page_break(doc)
    heading(doc, "附录 A　接口调用示例", 1)
    code(doc, [
        "# 1) 发起一次转账",
        "curl -X POST http://127.0.0.1:8000/api/chat \\",
        "  -H 'Content-Type: application/json' \\",
        "  -d '{\"session_id\":\"demo\",\"text\":\"给王强转200元，备注饭钱\"}'",
        "",
        "# 2) 确认执行（黄色）",
        "curl -X POST http://127.0.0.1:8000/api/confirm \\",
        "  -d '{\"session_id\":\"demo\",\"decision\":\"approve\"}'",
        "",
        "# 3) 强验证（红色，仅演示环境回显验证码）",
        "curl -X POST http://127.0.0.1:8000/api/mfa/verify \\",
        "  -d '{\"session_id\":\"demo\",\"method\":\"sms\",\"code\":\"123456\"}'",
        "",
        "# 4) IM 渠道（纯文本确认）",
        "curl -X POST http://127.0.0.1:8000/api/im/webhook \\",
        "  -d '{\"channel\":\"wechat\",\"user_id\":\"u1\",\"text\":\"给王强转200元\"}'",
    ])

    heading(doc, "附录 B　权限动作全表（27 项）", 1)
    table(doc, ["级别", "动作（代码标识）"], [
        ["绿色（14）", "query_balance、query_txn、analyze_bills、detect_anomaly、query_wealth、"
                       "recommend_wealth、compare_wealth、quote_wealth、plan_budget、list_subscriptions、"
                       "query_cards、query_calendar、resolve_contact、compute"],
        ["黄色（8）", "split_aa、lock_savings、apply_physical_card、apply_virtual_card、set_txn_limit、"
                     "cancel_subscription、redeem_wealth、schedule_order"],
        ["红色（5）", "subscribe_wealth、freeze_card、unfreeze_card、adjust_card_limit、change_password"],
        ["动态", "transfer（按「今日累计 + 本次金额」判定：≤1000 黄，>1000 红；单笔 ≥5000 追加人工复核标记）"],
    ], widths=[2.4, 13.8], size=9)

    para(doc, "", space_after=10)
    para(doc, "—— 文档结束 ——", size=9, color=LIGHT, align=WD_ALIGN_PARAGRAPH.CENTER)

    doc.save(OUT)
    print(f"saved: {OUT} ({os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    build()
