"""生成《安全自评报告：权限分级实现说明与已知风险清单》DOCX。"""
import os
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from build_docx import (BLUE, CN_FONT, GRAY, INK, LIGHT, NAVY, add_page_number, bullet,
                        code, figure, heading, page_break, para, set_run, table)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "银掌柜-安全自评报告.docx")


def build():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.4)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = CN_FONT
    normal.font.size = Pt(10.5)

    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run(hp.add_run("银掌柜 · 安全自评报告"), size=8.5, color=LIGHT)
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(fp.add_run("第 "), size=8.5, color=LIGHT)
    add_page_number(fp)
    set_run(fp.add_run(" 页"), size=8.5, color=LIGHT)

    # ---------------- 封面
    for _ in range(5):
        para(doc, "", space_after=0)
    para(doc, "安全自评报告", size=34, bold=True, color=NAVY, space_after=4)
    para(doc, "权限分级实现说明与已知风险清单", size=18, color=BLUE, space_after=30)
    table(doc, ["项目", "内容"], [
        ["作品名称", "银掌柜 · 银行 AI 智能体"],
        ["报告对象", "权限分级机制（三级）、五项安全机制、残余风险"],
        ["自评依据", "赛题「核心技术要求」第 1、2 条；本作品源代码、自动化测试与安全自检脚本"],
        ["版本 / 日期", f"v1.0　/　{date.today().isoformat()}"],
        ["报告结论", "权限分级：符合；五项安全机制：符合；残余风险 9 项，均已列出并给出生产化路径"],
    ], widths=[3.0, 13.0], size=9.5)
    para(doc, "", space_after=24)
    para(doc, "声明：本报告基于参赛作品的演示实现自评，账户与资金数据均为虚构，不构成对真实生产系统的安全承诺。",
         size=8.5, color=LIGHT)

    page_break(doc)

    # ---------------- 一、概述
    heading(doc, "一、报告概述", 1)

    heading(doc, "1.1 目的与范围", 2)
    para(doc, "本报告回答两个问题：一是「权限分级到底怎么实现的、能不能被绕过」；"
              "二是「这套系统还有哪些已知风险、残余风险是什么量级」。", indent_first=21)
    table(doc, ["范围", "是否覆盖", "说明"], [
        ["三级权限判定逻辑", "覆盖", "静态分级表 + 金额动态判定 + fail-closed"],
        ["分级强制执行", "覆盖", "服务端状态机、确认卡、多因子认证"],
        ["五项安全机制", "覆盖", "幻觉防护 / 注入防御 / 操作审计 / 异常熔断 / 代码沙箱"],
        ["分级一致性验证", "覆盖", "安全自检 3 项 + 自动化测试 13 项"],
        ["生产环境合规与渗透测试", "未覆盖", "演示环境不具备真实账户体系与网络边界"],
    ], widths=[4.6, 2.2, 9.2])

    heading(doc, "1.2 自评方法", 2)
    bullet(doc, "代码走查：逐条核对权限判定的输入来源，确认「模型输出不参与判定」。")
    bullet(doc, "自动化验证：pytest 13 项权限用例，覆盖边界值、日累计升级与未知动作。")
    bullet(doc, "主动探测：/api/selfcheck 以脚本方式发起注入、越权、幻觉等 8 类探测并给出结论。")
    bullet(doc, "失败路径演练：余额不足、封闭期赎回、强验证连续失败等异常场景的回滚与熔断。")

    heading(doc, "1.3 结论摘要", 2)
    table(doc, ["赛题要求", "自评结论", "主要证据"], [
        ["三级权限分级（绿/黄/红）", "符合", "27 项动作分级（14/8/5）+ 金额动态判定 + 3 项自检"],
        ["幻觉防护（不得编造）", "符合", "回复后置事实校验 + 20 例回归测试"],
        ["注入防御（不得绕过权限）", "符合", "归一化 + 11 类模式拦截 + 熔断 + 2 项自检"],
        ["操作审计（决策链路与执行日志）", "符合", "哈希链审计，覆盖 input→tool→mfa 全链路"],
        ["异常熔断（连续失败锁定）", "符合", "3 次失败 / 2 次注入 → 锁定 5 分钟"],
        ["沙箱环境（受限可监控）", "符合", "AST 白名单执行，禁止属性访问/导入/赋值"],
    ], widths=[6.0, 2.2, 8.0])

    # ---------------- 二、权限分级
    page_break(doc)
    heading(doc, "二、权限分级实现说明", 1)

    heading(doc, "2.1 分级模型", 2)
    table(doc, ["级别", "定义", "判定依据", "执行策略"], [
        ["绿色", "纯查询，不改变资金与账户状态", "静态表登记为 query 类动作", "模型确认意图后直接执行，无需二次确认"],
        ["黄色", "会改变账户或业务状态，风险可控", "静态表登记为 state-change 类；或金额在免验额度内",
         "展示完整操作详情，用户明确确认后执行"],
        ["红色", "涉及资金安全或账户关键凭据", "静态表登记为 red 类；或金额超过阈值；或动作未登记",
         "多因子认证通过后才执行"],
    ], widths=[1.8, 5.0, 5.2, 4.2])

    heading(doc, "2.2 判定流程", 2)
    para(doc, "判定完全基于「动作名 + 工具参数」，不读取模型生成的任何文本。流程分三步："
              "识别是否金额类动作 → 查静态表或计算投影金额 → 汇合为执行策略。", indent_first=21)
    figure(doc, "fig6_tier_flow.png", "图 1　权限分级判定流程（含 fail-closed 分支）")

    heading(doc, "2.3 静态分级表（27 项）", 2)
    table(doc, ["级别", "动作（代码标识）"], [
        ["绿色（14）", "query_balance、query_txn、analyze_bills、detect_anomaly、query_wealth、recommend_wealth、"
                       "compare_wealth、quote_wealth、plan_budget、list_subscriptions、query_cards、query_calendar、"
                       "resolve_contact、compute"],
        ["黄色（8）", "split_aa、lock_savings、apply_physical_card、apply_virtual_card、set_txn_limit、"
                     "cancel_subscription、redeem_wealth、schedule_order"],
        ["红色（5）", "subscribe_wealth、freeze_card、unfreeze_card、adjust_card_limit、change_password"],
        ["动态（1）", "transfer：按「今日累计 + 本次金额」判定（≤1000 黄，>1000 红；单笔 ≥5000 追加人工复核标记）"],
    ], widths=[2.4, 13.8], size=9)

    heading(doc, "2.4 金额动态判定", 2)
    para(doc, "转账类动作不按单笔金额拍脑袋，而是计算「投影金额」后与阈值比较；预约转账不占用当日免验额度。",
         indent_first=21)
    code(doc, [
        "projected = 今日累计转账 + 本次金额 × 收款人数量",
        "if 预约转账(when > today):",
        "    tier = RED if 本次金额 > 1000 else YELLOW",
        "elif projected > 1000:",
        "    tier = RED;  review_flag = (本次金额 >= 5000)",
        "else:",
        "    tier = YELLOW",
    ])
    table(doc, ["输入场景", "投影金额", "判定级别", "说明"], [
        ["单笔 200 元", "200", "黄色", "免验额度内，确认后执行"],
        ["单笔 1000 元", "1000", "黄色", "边界值取等号，仍属黄色"],
        ["单笔 1001 元", "1001", "红色", "越过阈值即升级强验证"],
        ["今日已转 800 元，再转 300 元", "1100", "红色", "日累计口径，不是单笔口径"],
        ["单笔 6000 元", "6000", "红色 + 复核标记", "金额较大，建议人工复核"],
        ["预约「下周一转 800 元」", "—", "黄色", "预约不占用当日额度，按单笔判定"],
    ], widths=[5.4, 2.2, 3.2, 5.4])

    heading(doc, "2.5 强制执行机制", 2)
    bullet(doc, "服务端状态机：计划生成后进入 awaiting_confirm，未收到确认请求时不会执行任何副作用动作。")
    bullet(doc, "确认卡：展示收款人、金额、付款账户、备注、执行时间、执行后余额、风控判定理由，逐项可核对。")
    bullet(doc, "多因子认证：红色动作下发一次性挑战（人脸识别 / 短信验证码 / U 盾），180 秒过期、最多 3 次尝试。")
    bullet(doc, "验证前资金不动：认证通过后才执行工具调用；失败或超时则回到确认态，不复用旧挑战。")
    bullet(doc, "fail-closed：动作未登记、参数缺失、工具异常，一律按最高风险处理或直接拒绝。")

    heading(doc, "2.6 实现位置（代码证据）", 2)
    table(doc, ["机制", "文件", "关键函数 / 常量"], [
        ["分级判定", "app/policy.py", "STATIC_TIERS、classify()、max_tier()"],
        ["阈值常量", "app/config.py", "YELLOW_TRANSFER_LIMIT=1000、RED_SINGLE_AMOUNT=5000"],
        ["执行闸门", "app/executor.py", "_advance()、confirm()、verify_mfa()、_pending_cards()"],
        ["确认卡字段", "app/planner.py", "describe()"],
        ["强验证挑战", "app/executor.py", "session.mfa（methods / expires / attempts）"],
        ["多渠道等价", "app/channels.py", "handle()（IM 文本确认与验证码）"],
    ], widths=[3.6, 4.6, 8.0], size=9)

    heading(doc, "2.7 分级一致性验证", 2)
    table(doc, ["验证项", "手段", "预期 / 实际结果"], [
        ["300 元转账落在黄色", "自检 #3 + 测试", "awaiting_confirm，tier=yellow；确认前余额不变"],
        ["1500 元转账落在红色", "自检 #2 + 测试", "确认后进入 awaiting_mfa；未验证前余额不变"],
        ["黄色动作不触发多因子", "自检 #8", "确认后直接 done，未下发挑战"],
        ["未知动作 fail-closed", "测试", "tier=red，requires_mfa=True"],
        ["日累计升级", "测试", "先 600 后 600，第二笔判红"],
        ["IM 渠道不可提权", "测试", "IM 回「确认」后仍需强验证"],
    ], widths=[4.6, 4.0, 7.6])

    # ---------------- 三、安全机制
    page_break(doc)
    heading(doc, "三、五项安全机制实现要点", 1)
    table(doc, ["机制", "做法", "验证证据", "已知边界"], [
        ["幻觉防护", "每个工具返回结构化 facts（金额集合 / 卡号尾号）；回复生成后抽取金额与尾号逐个比对，"
                     "失配则整段替换为事实模板并告警",
         "20 例「回复无无依据金额」回归；自检 #4", "只校验金额与尾号等可枚举事实，不校验语义表述"],
        ["注入防御", "全角转半角、去零宽字符、折叠空白后匹配 11 类注入模式；命中即拒绝并计入熔断",
         "7 组注入用例；自检 #1；含变体混淆用例", "规则库为已知模式，新变体需持续补规则"],
        ["操作审计", "每条记录含 prev 与 hash（sha256 前 16 位），形成链；覆盖 input/nlu/plan/policy/tool/confirm/mfa/guard/rollback",
         "自检 #7 校验链完整性；篡改用例可定位首个失配点", "落本地 JSONL，本机可删（见 R5）"],
        ["异常熔断", "连续 3 次失败或 2 次注入尝试 → 锁定 5 分钟；锁定期间所有请求直接拒绝",
         "自检 #6；注入连击用例", "按会话计数，换会话可绕过（见 R7 关联）"],
        ["代码沙箱", "AST 白名单：禁属性访问、导入、赋值与循环；仅允许算术、比较与内置纯函数",
         "3 段逃逸用例全部拒绝；收益试算在沙箱内执行", "仅覆盖表达式级计算，不执行任意脚本"],
    ], widths=[2.4, 6.4, 4.4, 3.4], size=8.5)

    # ---------------- 四、风险清单
    page_break(doc)
    heading(doc, "四、已知风险清单", 1)
    para(doc, "下表为本作品自查发现的风险项，按「可能性 × 影响」定位（图 2），并给出缓解措施与残余风险等级。"
              "等级判据：残余风险 = 现有缓解措施落地后仍存在的风险。", indent_first=21)
    figure(doc, "fig7_risk_matrix.png", "图 2　已知风险矩阵（残余风险，缓解前评估）")

    table(doc, ["编号", "风险描述", "影响", "可能性", "现有缓解", "残余", "生产化建议"], [
        ["R1", "人脸识别与 U 盾为模拟通过", "高", "高", "界面明确标注「演示环境」；生产不可用",
         "中", "对接行方强验证 SDK 与硬件密钥"],
        ["R2", "账户与资金为模拟账本", "高", "中", "数据全部虚构并声明；工具层与风控层解耦",
         "中", "实现核心系统适配层，替换 app/bank.py"],
        ["R3", "登录为界面级门禁（前端 localStorage 判定）", "高", "高",
         "不将其伪装为安全鉴权；文档明示", "高", "网关层会话校验 + 服务端签名令牌"],
        ["R4", "规则引擎对超出覆盖的表达会澄清", "中", "中", "未知即澄清，不猜着执行", "低",
         "引入 LLM 增强 + 持续补充语料"],
        ["R5", "审计落本地文件，本机可删除", "中", "中", "哈希链保证篡改可发现", "中",
         "写入 WORM 存储 / 集中审计平台"],
        ["R6", "演示环境短信验证码回显", "中", "低", "仅演示环境；标注真实环境走运营商通道", "低",
         "关闭回显，接入短信网关"],
        ["R7", "会话与熔断计数为进程内内存态", "低", "高", "重启即清空，不影响资金安全", "低",
         "会话外部化（Redis）+ 计数持久化"],
        ["R8", "注入规则库可能被新型变体绕过", "高", "中", "多层防御：权限判定不读模型输出；命中即熔断",
         "中", "规则持续更新 + 引入语义级检测"],
        ["R9", "可选 LLM 接入时外部依赖不可用", "低", "中", "静默降级为规则引擎，功能不中断", "低",
         "多供应商兜底 + 超时熔断"],
    ], widths=[1.2, 4.4, 1.1, 1.3, 4.4, 1.1, 4.3], size=8)

    heading(doc, "4.1 残余风险接受说明", 2)
    bullet(doc, "R1 / R2 / R3 属于「演示环境与真实环境的差距」，不属于实现缺陷；三者在架构上都预留了替换点"
                "（强验证适配层、账本适配层、网关鉴权），替换不需要改动权限引擎。")
    bullet(doc, "R3 是本次自评中等级最高的一项：真实上线前必须先补服务端鉴权，否则前端门禁可被绕过。")
    bullet(doc, "R5 / R7 / R8 属于可运营收敛的风险：已有检测或降级手段，随部署形态升级即可下降。")

    # ---------------- 五、结论
    heading(doc, "五、自评结论与整改计划", 1)
    table(doc, ["项", "结论", "后续动作", "阶段"], [
        ["三级权限分级", "符合赛题要求，且不可由对话提权", "补充更多动作类型的分级评审", "持续"],
        ["五项安全机制", "全部实现并有自动化验证", "规则库与事实集覆盖持续扩展", "持续"],
        ["R3 服务端鉴权", "不满足生产要求", "网关层会话校验、服务端令牌", "上线前必做"],
        ["R1 真实强验证", "不满足生产要求", "对接行方 SDK", "上线前必做"],
        ["R5 审计持久化", "不满足监管要求", "WORM 存储 + 集中审计", "试点阶段"],
        ["R7 会话外部化", "可用性风险", "Redis 会话与计数持久化", "试点阶段"],
    ], widths=[3.4, 4.6, 5.2, 3.4])

    para(doc, "总体结论：在「演示实现」的定位下，权限分级与五项安全机制均达到赛题要求，"
              "且关键属性可通过脚本复现；已识别的 9 项残余风险均有明确的生产化路径，其中 2 项"
              "（服务端鉴权、真实强验证）必须在真实上线前关闭。", indent_first=21, space_before=6)

    # ---------------- 附录
    page_break(doc)
    heading(doc, "附录 A　复现方法", 1)
    code(doc, [
        "# 1) 安装依赖并启动（Windows / Linux 一致）",
        "pip install -r requirements.txt",
        "python run.py 8000",
        "",
        "# 2) 逐项复核权限分级（脚本化，无需点界面）",
        "python -m pytest tests/test_policy.py -v      # 13 项分级判定",
        "python -m pytest tests/test_security.py -v     # 19 项安全机制",
        "python -m pytest -q                            # 全量 120 项",
        "",
        "# 3) 现场安全自检（8 项，含注入/越权/幻觉/沙箱/熔断/审计链）",
        "curl http://127.0.0.1:8000/api/selfcheck | python -m json.tool",
        "",
        "# 4) 复核「未确认不执行」：确认前查余额，确认后再查",
        "curl -X POST http://127.0.0.1:8000/api/chat -d '{\"session_id\":\"a\",\"text\":\"给王强转1500元\"}'",
        "curl -X POST http://127.0.0.1:8000/api/confirm -d '{\"session_id\":\"a\",\"decision\":\"approve\"}'",
        "# 上一步返回 awaiting_mfa，此时余额未变；验证码通过后才扣款",
    ])

    heading(doc, "附录 B　与本报告相关的其他材料", 1)
    table(doc, ["材料", "内容", "位置"], [
        ["技术文档", "系统架构、核心算法、安全设计、测试验证", "docs/银掌柜-技术文档.docx"],
        ["源代码", "权限引擎、安全模块、测试用例", "app/policy.py、app/security.py、tests/"],
        ["权限矩阵接口", "机器可读的分级表（前端与自评共用）", "GET /api/policy"],
        ["审计接口", "审计记录 + 哈希链校验结果", "GET /api/audit"],
    ], widths=[3.4, 8.6, 4.6])

    para(doc, "", space_after=10)
    para(doc, "—— 报告结束 ——", size=9, color=LIGHT, align=WD_ALIGN_PARAGRAPH.CENTER)

    try:
        doc.save(OUT)
        print(f"saved: {OUT} ({os.path.getsize(OUT)//1024} KB)")
    except PermissionError:
        alt = OUT.replace(".docx", f"-{date.today().strftime('%m%d')}.docx")
        doc.save(alt)
        print(f"原文件被占用，已另存: {alt} ({os.path.getsize(alt)//1024} KB)")


if __name__ == "__main__":
    build()
