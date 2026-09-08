from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUTPUT = "Kickstarter爬虫交付说明与批量爬取指南.docx"
BLUE = RGBColor(46, 116, 181)
DARK_BLUE = RGBColor(31, 77, 120)
NAVY = RGBColor(11, 37, 69)
GRAY = RGBColor(90, 98, 108)
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F2F4F7"


def set_font(run, name="Microsoft YaHei", size=11, bold=None, color=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    run._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def shade_cell(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_table_geometry(table, widths):
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "120")
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(width))
        grid.append(grid_col)
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            cell.width = Inches(widths[index] / 1440)
            tc_w = cell._tc.get_or_add_tcPr().find(qn("w:tcW"))
            tc_w.set(qn("w:w"), str(widths[index]))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("第 ")
    set_font(run, size=9, color=GRAY)
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr_text)
    run._r.append(fld_char2)
    tail = paragraph.add_run(" 页")
    set_font(tail, size=9, color=GRAY)


def style_document(doc):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    normal = doc.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 14, 7),
        ("Heading 3", 12, DARK_BLUE, 10, 5),
    ):
        style = doc.styles[name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    for name in ("List Bullet", "List Number"):
        style = doc.styles[name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(11)
        style.paragraph_format.left_indent = Inches(0.375)
        style.paragraph_format.first_line_indent = Inches(-0.188)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.25


def add_header_footer(doc):
    section = doc.sections[0]
    header = section.header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run("Kickstarter 爬虫交付说明与批量爬取指南")
    set_font(run, size=9, bold=True, color=GRAY)
    footer = section.footer
    add_page_number(footer.paragraphs[0])


def add_title_page(doc):
    for _ in range(4):
        doc.add_paragraph()
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = kicker.add_run("技术交付文档")
    set_font(r, size=11, bold=True, color=BLUE)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(10)
    r = title.add_run("Kickstarter 爬虫")
    set_font(r, size=30, bold=True, color=NAVY)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(28)
    r = subtitle.add_run("调试、完善、批量采集与运行指南")
    set_font(r, size=16, color=DARK_BLUE)

    summary = doc.add_paragraph()
    summary.alignment = WD_ALIGN_PARAGRAPH.CENTER
    summary.paragraph_format.space_after = Pt(60)
    r = summary.add_run("包含项目、创作者、协作者元数据采集及失败恢复机制")
    set_font(r, size=10.5, color=GRAY)

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = meta.add_run("交付版本：2026-07-27")
    set_font(r, size=11, bold=True, color=NAVY)
    doc.add_page_break()


def add_status_table(doc):
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    headers = ("工作模块", "状态", "结果")
    for i, value in enumerate(headers):
        cell = table.rows[0].cells[i]
        shade_cell(cell, LIGHT_BLUE)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(value)
        set_font(r, size=10.5, bold=True, color=NAVY)
    rows = [
        ("运行问题排查", "完成", "解决无输出、超时、403及失败任务重复问题"),
        ("项目元数据", "完成", "项目ID、链接、筹款时间、金额和状态"),
        ("创作者数据", "完成", "身份、项目统计、注册时间、外链及地区"),
        ("协作者数据", "完成", "协作者身份、角色、链接和公开资料"),
        ("数据库任务", "完成", "MySQL任务队列、事务写入、重试和恢复"),
        ("批量URL导入", "完成", "支持TXT、CSV、JSON，规范化并去重"),
        ("真实项目测试", "完成", "3个项目全部通过，HTTP与字段检查正常"),
    ]
    for row_values in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row_values):
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i == 1 else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(value)
            set_font(r, size=9.5)
    set_repeat_table_header(table.rows[0])
    set_table_geometry(table, [2300, 1200, 5860])


def add_code_block(doc, lines):
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.cell(0, 0)
    shade_cell(cell, LIGHT_GRAY)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    for idx, line in enumerate(lines):
        r = p.add_run(line)
        r.font.name = "Consolas"
        r._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        r.font.size = Pt(9)
        if idx < len(lines) - 1:
            r.add_break()
    set_table_geometry(table, [9360])


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.add_run(text)
    return p


def number(doc, text):
    p = doc.add_paragraph(style="List Number")
    p.add_run(text)
    return p


def build():
    doc = Document()
    style_document(doc)
    add_header_footer(doc)
    add_title_page(doc)

    doc.add_heading("1. 交付概览", level=1)
    doc.add_paragraph(
        "本次交付目标是将原有 Kickstarter 爬虫从“可能长时间无输出、频繁触发安全验证、"
        "失败后无法正确恢复”的状态，调整为可观察、可恢复、可小批量长期运行的采集程序。"
        "程序默认直连、单线程和低频运行，不尝试绕过交互式人机验证。"
    )
    add_status_table(doc)

    doc.add_heading("2. 已完成的工作", level=1)
    doc.add_heading("2.1 请求与风控处理", level=2)
    for text in (
        "固定 Chrome TLS 指纹与匹配的 User-Agent，避免随机指纹互相矛盾。",
        "每个任务复用 Session 和 Cookie，减少新会话反复触发验证的概率。",
        "请求设置30秒超时，输出请求次数、HTTP状态和最终跳转地址。",
        "识别403、429、Captcha、Verify you are human及安全验证页面。",
        "使用有限重试和退避等待；任务级失败按15、30、60分钟等间隔重新调度。",
        "连续失败达到上限后标记为 blocked，不会无限循环或假装成功。",
    ):
        bullet(doc, text)

    doc.add_heading("2.2 数据字段", level=2)
    doc.add_paragraph("项目字段包括：")
    for text in (
        "项目ID、项目链接、项目名称、状态和支持者数量；",
        "筹款开始时间、筹款结束时间；",
        "币种、目标金额、实际筹款金额。",
    ):
        bullet(doc, text)
    doc.add_paragraph("创作者字段包括：")
    for text in (
        "创作者ID、名称、Kickstarter主页链接和注册时间；",
        "发起项目数量、支持项目数量、累计支持者数量；",
        "地区、简介、外部链接和身份验证状态。",
    ):
        bullet(doc, text)
    doc.add_paragraph("协作者字段包括：")
    for text in (
        "协作者ID、名称、角色和主页链接；",
        "地区、简介、注册时间、外部链接和项目统计；",
        "预留服务商标记、服务类别、分类来源和置信度字段。",
    ):
        bullet(doc, text)

    doc.add_heading("2.3 数据库与批量任务", level=2)
    for text in (
        "建立项目、创作者、协作者、项目—协作者关系和任务队列表。",
        "项目、创作者和协作者使用唯一ID去重，并通过事务写入。",
        "支持 pending、processing、retry、filtered_year、success、blocked、not_found 状态。",
        "程序异常退出超过1小时后，遗留 processing 任务可以自动恢复。",
        "支持按筹款开始年份筛选，但年份筛选仍需要候选项目URL。",
    ):
        bullet(doc, text)

    doc.add_heading("3. 测试结果", level=1)
    doc.add_paragraph(
        "已使用3个真实项目进行低频冒烟测试，覆盖正在筹款、历史失败和历史成功项目。"
        "每个项目均完成项目主页请求和GraphQL请求，核心字段检查全部通过。"
    )
    test_table = doc.add_table(rows=1, cols=4)
    test_table.style = "Table Grid"
    for i, value in enumerate(("项目", "状态", "项目ID", "结果")):
        shade_cell(test_table.rows[0].cells[i], LIGHT_BLUE)
        p = test_table.rows[0].cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(value)
        set_font(r, size=10, bold=True, color=NAVY)
    for values in (
        ("Rosalie", "live", "347939087", "通过"),
        ("DUB STEP", "failed", "1995908361", "通过"),
        ("TADCALO", "successful", "195266957", "通过"),
    ):
        cells = test_table.add_row().cells
        for i, value in enumerate(values):
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(value)
            set_font(r, size=9.5)
    set_repeat_table_header(test_table.rows[0])
    set_table_geometry(test_table, [3600, 1800, 2160, 1800])

    doc.add_heading("4. 交付文件说明", level=1)
    files = (
        ("maininfo_spider.py", "修复后的原项目主页爬虫。"),
        ("project_metadata_spider.py", "单项目项目、创作者和协作者采集。"),
        ("metadata_batch_spider.py", "MySQL单线程批量任务和失败恢复。"),
        ("url_importer.py", "TXT、CSV、JSON项目URL导入和去重。"),
        ("metadata_schema.sql", "元数据及任务表结构。"),
        ("smoke_test.py / sample_urls.txt", "多项目自动验收测试。"),
        ("proxy_probe.py", "代理DNS、端口、认证和目标页面探测。"),
        ("docker-compose.metadata.yml", "本地MySQL 8持久化环境。"),
        ("requirements-metadata.txt", "最小Python依赖。"),
    )
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    for i, value in enumerate(("文件", "用途")):
        shade_cell(table.rows[0].cells[i], LIGHT_BLUE)
        r = table.rows[0].cells[i].paragraphs[0].add_run(value)
        set_font(r, size=10, bold=True, color=NAVY)
    for filename, purpose in files:
        cells = table.add_row().cells
        set_font(cells[0].paragraphs[0].add_run(filename), size=9)
        set_font(cells[1].paragraphs[0].add_run(purpose), size=9.5)
    set_repeat_table_header(table.rows[0])
    set_table_geometry(table, [3500, 5860])

    doc.add_page_break()
    doc.add_heading("5. 首次安装与启动", level=1)
    number(doc, "解压交付包，将 config.example.json 复制为 config.json。")
    add_code_block(doc, ["Copy-Item config.example.json config.json"])
    number(doc, "修改 config.json 中的数据库连接信息。旧代理尚无认证信息，应保持 enable_proxy=0。")
    doc.add_paragraph(
        "示例配置与Docker Compose均默认使用root用户，并共用MYSQL_ROOT_PASSWORD，"
        "因此新机器复制示例配置后不会出现数据库用户不一致。"
    )
    number(doc, "重新创建虚拟环境，不要复制其他机器的旧 .venv。")
    add_code_block(
        doc,
        [
            "python -m venv .venv",
            r".\.venv\Scripts\python.exe -m pip install -r requirements-metadata.txt",
        ],
    )
    doc.add_paragraph(
        "最终依赖清单同时包含新流程和旧脚本所需的 beautifulsoup4、requests、"
        "tls-client、curl_cffi、lxml 和 pymysql。"
    )
    number(doc, "启动本机MySQL。如果已有MySQL，可跳过Docker步骤。")
    add_code_block(
        doc,
        [
            "$cfg = Get-Content -Raw config.json | ConvertFrom-Json",
            "$env:MYSQL_ROOT_PASSWORD = $cfg.db_config.password",
            "$env:MYSQL_DATABASE = $cfg.db_config.database",
            "docker compose -f docker-compose.metadata.yml up -d --wait",
        ],
    )
    number(doc, "首次初始化表结构。")
    add_code_block(
        doc,
        [r".\.venv\Scripts\python.exe metadata_batch_spider.py --init-schema --limit 1"],
    )

    doc.add_heading("6. 使用项目 URL 文件批量爬取", level=1)
    doc.add_heading("6.1 准备URL文件", level=2)
    doc.add_paragraph("推荐使用TXT文件，每行一个项目URL：")
    add_code_block(
        doc,
        [
            "https://www.kickstarter.com/projects/uchibacoyapiece/rosalie",
            "https://www.kickstarter.com/projects/deviever/dub-step-the-dub-step-guitar-pedal",
            "https://www.kickstarter.com/projects/tadcalo/tadcalo-full-switch-two-type-c-kvm-docking-station",
        ],
    )
    doc.add_paragraph(
        "也支持CSV和JSON。CSV列名可使用 project_url、project_link、url 或 link。"
        "导入器会去除 ?ref=... 等查询参数、统一域名、排除非法链接并自动去重。"
    )

    doc.add_heading("6.2 先检查，再导入", level=2)
    doc.add_paragraph("只检查文件，不写数据库：")
    add_code_block(
        doc,
        [r".\.venv\Scripts\python.exe url_importer.py urls.txt --dry-run"],
    )
    doc.add_paragraph("确认结果后正式导入：")
    add_code_block(doc, [r".\.venv\Scripts\python.exe url_importer.py urls.txt"])
    doc.add_paragraph("同一个文件重复导入不会产生重复任务。")

    doc.add_heading("6.3 小批量运行", level=2)
    doc.add_paragraph("先运行10条，确认网络和数据结构：")
    add_code_block(
        doc,
        [r".\.venv\Scripts\python.exe metadata_batch_spider.py --limit 10"],
    )
    doc.add_paragraph("确认稳定后逐步提高批次：")
    add_code_block(
        doc,
        [r".\.venv\Scripts\python.exe metadata_batch_spider.py --limit 50"],
    )
    doc.add_paragraph("按筹款开始年份筛选：")
    add_code_block(
        doc,
        [r".\.venv\Scripts\python.exe metadata_batch_spider.py --limit 50 --year 2025"],
    )
    doc.add_paragraph(
        "注意：项目URL无法仅根据年份推导。--year 只对已经导入的候选URL进行年份筛选，"
        "不会自动发现该年份的全部Kickstarter项目。"
    )
    doc.add_paragraph(
        "年份不匹配的任务会标记为 filtered_year，而不是 success。同一年再次运行不会"
        "重复请求；切换年份或取消 --year 后，相关任务会自动恢复为 pending 并重新处理。"
    )
    doc.add_paragraph(
        "年份判断在项目主页解析后立即进行；不符合年份时只产生一次主页请求，不再调用"
        "GraphQL。批量输出包含 processed、succeeded、filtered 和 failed；本轮存在失败"
        "任务时进程退出码为2，只有成功或年份过滤时退出码为0。"
    )

    doc.add_heading("7. 查看任务状态与重新运行", level=1)
    doc.add_paragraph("查看各状态数量：")
    add_code_block(
        doc,
        [
            "SELECT crawl_status, COUNT(*)",
            "FROM metadata_crawl_tasks",
            "GROUP BY crawl_status;",
        ],
    )
    status_table = doc.add_table(rows=1, cols=2)
    status_table.style = "Table Grid"
    for i, value in enumerate(("状态", "含义")):
        shade_cell(status_table.rows[0].cells[i], LIGHT_BLUE)
        r = status_table.rows[0].cells[i].paragraphs[0].add_run(value)
        set_font(r, size=10, bold=True, color=NAVY)
    for status, meaning in (
        ("pending", "等待处理"),
        ("processing", "正在处理"),
        ("retry", "失败，等待到期重试"),
        ("filtered_year", "已读取，但筹款开始年份不符合本轮筛选"),
        ("success", "采集并写入成功"),
        ("blocked", "连续失败达到上限，需要人工检查"),
        ("not_found", "项目不存在或返回404"),
    ):
        cells = status_table.add_row().cells
        set_font(cells[0].paragraphs[0].add_run(status), size=9.5)
        set_font(cells[1].paragraphs[0].add_run(meaning), size=9.5)
    set_repeat_table_header(status_table.rows[0])
    set_table_geometry(status_table, [2300, 7060])

    doc.add_paragraph("查看失败任务：")
    add_code_block(
        doc,
        [
            "SELECT task_id, project_url, attempt_count,",
            "       last_status_code, last_error, next_retry_at",
            "FROM metadata_crawl_tasks",
            "WHERE crawl_status IN ('retry','blocked','not_found');",
        ],
    )
    doc.add_paragraph("字段调整后，可重置指定任务：")
    add_code_block(
        doc,
        [
            "UPDATE metadata_crawl_tasks",
            "SET crawl_status='pending', attempt_count=0,",
            "    last_error=NULL, next_retry_at=NULL",
            "WHERE task_id=123;",
        ],
    )

    doc.add_page_break()
    doc.add_heading("8. 运行注意事项", level=1)
    doc.add_heading("8.1 请求频率", level=2)
    for text in (
        "保持单线程；批量程序默认每个项目随机等待5～15秒。",
        "不要同时运行多个Kickstarter脚本访问同一批项目。",
        "不要为了追求速度直接增大线程数；稳定性优先于短时吞吐量。",
        "大批量运行应先测试10条，再扩大到50条或更大的计划批次。",
    ):
        bullet(doc, text)

    doc.add_heading("8.2 403与人机验证", level=2)
    for text in (
        "程序会识别403、429和常见安全验证页面。",
        "出现验证后会等待并有限重试；任务仍失败则进入retry队列。",
        "不要在403后立即无限重试，否则可能延长出口IP的风控时间。",
        "普通HTTP程序不能可靠自动完成交互式验证码，必要时应暂停并人工检查。",
    ):
        bullet(doc, text)

    doc.add_heading("8.3 代理", level=2)
    doc.add_paragraph(
        "现有4个HTTP代理节点的域名和10030端口均正常，但无认证请求全部返回"
        "407 Proxy Authentication Required。因此当前配置必须保持关闭代理。"
        "只有取得用户名密码，或完成运行机器公网IP白名单授权后，才能设置 enable_proxy=1。"
    )
    doc.add_paragraph("当前直连已通过多个真实项目测试，代理不是程序运行的必要条件。")

    doc.add_heading("8.4 数据时效", level=2)
    for text in (
        "实际金额、支持人数和项目状态会随时间变化，应保留采集时间。",
        "需要最终金额时，应在项目结束后重新采集一次。",
        "创作者累计支持者数量和项目统计也可能随新项目变化。",
        "公开资料不存在时，地区、简介或外部链接会保留为空，不能凭空补全。",
    ):
        bullet(doc, text)

    doc.add_heading("8.5 协作者服务商分类", level=2)
    doc.add_paragraph(
        "Kickstarter不提供标准的“是否为服务商”和“服务类别”字段。程序会先保存协作者"
        "名称、角色、简介、地区和外部链接等原始公开资料。后续可以按 collaborator_id "
        "去重，再使用统一规则分类为Marketing、Advertising、Localization、Fulfillment、"
        "Manufacturing、PR、Consulting或Other，并同时记录分类来源和置信度。"
    )

    doc.add_heading("9. 验收与后续调整", level=1)
    for text in (
        "运行 smoke_test.py，确认样例项目全部通过。",
        "使用 url_importer.py --dry-run 检查实际URL文件。",
        "导入后先运行10条，核对数据库字段和失败比例。",
        "字段变化时修改采集结果和数据库结构，再重置指定任务重新采集。",
        "如果需要按年份全量发现项目，必须另行提供合法的候选URL数据源。",
    ):
        bullet(doc, text)
    doc.add_paragraph(
        "交付程序解决的是“已有项目URL文件后的稳定批量采集”。URL文件可以由使用方后续"
        "自行准备，程序不依赖当前测试数据，也不要求在交付阶段完成实际全量爬取。"
    )

    doc.add_heading("10. 代理预检与任务启动门禁（操作建议）", level=1)
    doc.add_paragraph(
        "本节只说明运行方式，不代表爬虫代码已增加自动拦截。交付包已有 proxy_probe.py，"
        "可在启动批量任务前独立检查代理。建议将“代理预检成功”作为批量任务的启动条件；"
        "预检失败时停止本轮任务，先处理认证、白名单或网络问题。"
    )
    doc.add_heading("10.1 推荐检查顺序", level=2)
    for text in (
        "检查 config.json 中 enable_proxy、Host、端口、用户名和密码是否符合实际认证方式。",
        "检查代理域名能否解析、10030端口能否建立TCP连接。",
        "通过代理访问公网IP查询服务，确认出口IP与直连不同。",
        "通过代理建立HTTPS CONNECT并访问一个Kickstarter测试项目。",
        "只有出口IP检查和目标页面检查成功后，才启动批量任务。",
    ):
        number(doc, text)
    doc.add_heading("10.2 手工执行门禁", level=2)
    add_code_block(
        doc,
        [
            r".\.venv\Scripts\python.exe proxy_probe.py",
            "if ($LASTEXITCODE -ne 0) {",
            '    throw "代理预检失败，已停止批量任务"',
            "}",
            r".\.venv\Scripts\python.exe metadata_batch_spider.py --limit 10",
        ],
    )
    doc.add_paragraph(
        "proxy_probe.py退出码为0表示至少有一条代理线路完成出口IP检查且Kickstarter返回200；"
        "非0表示没有线路完整通过。出现407时请求尚未成功到达Kickstarter，应先检查应用ID/"
        "应用密码或公网IP白名单。若不准备使用代理，应保持 enable_proxy=0，并使用直连冒烟"
        "测试作为启动前检查。"
    )
    doc.add_heading("10.3 建议记录的预检结果", level=2)
    for text in (
        "检查时间、运行机器名称和直连公网IP；",
        "代理Host、解析IP、TCP端口状态和代理出口IP；",
        "IP检查状态码、Kickstarter状态码、最终URL及错误原因；",
        "是否允许启动任务，以及作出判断的人员。",
    ):
        bullet(doc, text)

    doc.add_heading("11. 小象代理注册、购买与认证说明", level=1)
    doc.add_paragraph(
        "以下流程依据小象代理官方帮助中心在2026-07-28可访问的资料整理。平台页面、套餐、"
        "价格、优惠、发票和退款规则可能调整，实际操作以官网登录后的购买页、订单页和客服"
        "答复为准。不要在文档、聊天记录或代码仓库中公开应用密码。"
    )
    doc.add_heading("11.1 注册与实名认证", level=2)
    for text in (
        "访问官方站点 https://www.xiaoxiangdaili.com，选择注册/登录。",
        "使用可接收验证码的手机号创建账号；一个手机号通常对应一个账号。",
        "按照会员中心提示完成实名认证。官方帮助中心说明交易前需要实名认证。",
        "如需企业采购、合同、发票或对公转账，先联系平台在线客服确认当前流程。",
    ):
        number(doc, text)
    doc.add_heading("11.2 选择与购买产品", level=2)
    for text in (
        "进入产品购买页，选择“隧道代理—动态转发”，不要误购成短效IP提取产品。",
        "先申请试用或购买较短周期/较小规格进行连通性和目标站点测试。",
        "确认线路、有效期、并发限制、流量/请求计费方式和IP切换规则后再正式下单。",
        "按购买页支持的方式支付；如需账户充值、对公转账、合同或发票，联系官方客服。",
        "支付成功后进入“产品管理—隧道代理”查看应用信息和使用状态。",
    ):
        number(doc, text)
    doc.add_heading("11.3 获取认证信息", level=2)
    doc.add_paragraph("动态转发隧道支持两种常见认证方式，二选一即可：")
    for text in (
        "账号密码认证：后台“产品管理—隧道代理”页面中的应用ID作为 proxy_username，"
        "应用密码作为 proxy_pwd；它们不是网站登录手机号和登录密码。",
        "绑定IP认证：将实际运行爬虫机器的公网出口IP加入应用白名单，配置中的用户名和"
        "密码可以为空。家庭宽带、校园网和移动热点公网IP可能变化，变化后需重新绑定。",
    ):
        bullet(doc, text)
    doc.add_paragraph(
        "代理地址使用 http-dynamic.xiaoxiangdaili.com:10030，S02、S03、S04可作为其他"
        "线路。一次任务内应尽量保持同一Host、同一认证方式和同一会话，不要每次请求随意"
        "切换身份。"
    )
    doc.add_heading("11.4 配置示例与保密要求", level=2)
    add_code_block(
        doc,
        [
            '"proxy_host_list": ["http-dynamic.xiaoxiangdaili.com"],',
            '"proxy_port": 10030,',
            '"proxy_username": "后台显示的应用ID",',
            '"proxy_pwd": "后台显示的应用密码",',
            '"enable_proxy": 1',
        ],
    )
    doc.add_paragraph(
        "采用IP白名单时用户名和密码留空。config.json含数据库密码和代理凭据，不应提交"
        "到公开仓库；交付时只提供config.example.json，由运行人员在本机创建config.json。"
    )
    doc.add_heading("11.5 407排查顺序", level=2)
    for text in (
        "确认套餐仍有效，购买的是隧道动态转发产品。",
        "确认应用ID和应用密码来自产品管理页面，不是网站登录密码。",
        "如用白名单，确认绑定的是运行机器当前公网出口IP，而不是127.0.0.1或192.168地址。",
        "确认提取/管理代理的机器与实际使用代理的出口符合平台授权要求。",
        "确认Host和10030端口无拼写错误，并重新运行proxy_probe.py。",
        "仍返回407时保存检查时间、Host和错误信息，联系官方客服核查应用状态。",
    ):
        number(doc, text)

    doc.add_heading("12. 官方参考资料", level=1)
    sources = (
        ("快速入门", "https://www.xiaoxiangdaili.com/help/dev/index"),
        ("隧道代理接入指南", "https://www.xiaoxiangdaili.com/tunnel-short/CSharp/guide"),
        ("新用户常见问题", "https://www.xiaoxiangdaili.com/help/question/index"),
        ("常见购买问题", "https://www.xiaoxiangdaili.com/help/question/common-buy"),
        ("407问题排查", "https://www.xiaoxiangdaili.com/help/4274"),
    )
    source_table = doc.add_table(rows=1, cols=2)
    source_table.style = "Table Grid"
    for i, value in enumerate(("资料", "官方地址")):
        shade_cell(source_table.rows[0].cells[i], LIGHT_BLUE)
        r = source_table.rows[0].cells[i].paragraphs[0].add_run(value)
        set_font(r, size=10, bold=True, color=NAVY)
    for label, url in sources:
        cells = source_table.add_row().cells
        set_font(cells[0].paragraphs[0].add_run(label), size=9.5)
        set_font(cells[1].paragraphs[0].add_run(url), size=8.5)
    set_repeat_table_header(source_table.rows[0])
    set_table_geometry(source_table, [2600, 6760])

    doc.core_properties.title = "Kickstarter爬虫交付说明与批量爬取指南"
    doc.core_properties.subject = "程序调试、批量URL导入、运行与注意事项"
    doc.core_properties.author = "项目交付"
    doc.save(OUTPUT)


if __name__ == "__main__":
    build()
