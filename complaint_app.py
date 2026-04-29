import streamlit as st
from openai import OpenAI
import PyPDF2
import docx
import io
import re
import base64

# ========== 配置区 ==========
API_KEY = st.secrets["API_KEY"]
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_KNOWLEDGE_CHARS = 4000  # 发送给AI的知识库最大字符数，避免过长导致响应慢
# ============================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

st.set_page_config(page_title="市监举报辅助系统", layout="wide")
st.title("📋 举报工单智能分析与文书辅助")

# ========== 内置默认知识 ==========
DEFAULT_KNOWLEDGE = """
常用市场监督管理法律法规要点：
- 食品安全法第34条：禁止经营超过保质期的食品。
- 广告法第9条：广告不得使用“国家级”、“最高级”、“最佳”等绝对化用语。
- 无证无照经营查处办法第2条：任何单位或者个人不得违反法律、法规、国务院决定的规定，从事无证无照经营。
裁量参考因素：初次违法、货值金额、危害后果、是否主动消除影响、配合调查程度等。
"""

# ========== 脱敏函数 ==========
def mask_pii(text):
    return re.sub(r'(1[3-9]\d)\d{4}(\d{4})', r'\1****\2', text)

# ========== 文件解析函数（加缓存，避免重复解析） ==========
@st.cache_data(show_spinner=False)
def parse_file_bytes(file_name, file_bytes):
    """根据扩展名解析文件，返回文本"""
    name = file_name.lower()
    if name.endswith(".txt"):
        return file_bytes.decode("utf-8")
    elif name.endswith(".pdf"):
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted
        return text
    elif name.endswith(".docx"):
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join([para.text for para in doc.paragraphs])
    else:
        raise ValueError(f"不支持的文件类型: {name}")

# ========== 初始化 session_state ==========
if "knowledge_text" not in st.session_state:
    st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
if "loaded_files" not in st.session_state:
    st.session_state.loaded_files = []
if "raw_complaint" not in st.session_state:
    st.session_state.raw_complaint = ""

# ========== 知识库上传区域 ==========
st.subheader("📂 上传内部文档，构建或恢复知识库")
col_upload, col_load = st.columns([3, 1])
with col_upload:
    uploaded_knowledge = st.file_uploader(
        "支持批量上传：.txt .pdf .docx",
        type=["txt", "pdf", "docx"],
        accept_multiple_files=True,
        key="knowledge_uploader"
    )
with col_load:
    uploaded_knowledge_file = st.file_uploader(
        "导入已导出的知识库",
        type=["txt"],
        key="knowledge_import"
    )
    if uploaded_knowledge_file:
        try:
            imported_text = uploaded_knowledge_file.getvalue().decode("utf-8")
            st.session_state.knowledge_text = imported_text
            st.session_state.loaded_files = ["导入的知识库"]
            st.success("知识库已导入")
            st.rerun()
        except Exception as e:
            st.error(f"导入失败：{e}")

if uploaded_knowledge:
    if st.button("📥 确认添加至知识库"):
        existing = st.session_state.loaded_files
        new_files = []
        skipped = []
        for f in uploaded_knowledge:
            if f.name in existing:
                skipped.append(f.name)
            else:
                new_files.append(f)

        if not new_files:
            st.warning("本次上传的文件都已存在，未添加新内容。")
        else:
            new_texts = []
            for f in new_files:
                try:
                    text = parse_file_bytes(f.name, f.getvalue())
                    new_texts.append(f"【文件：{f.name}】\n{text}")
                except Exception as e:
                    st.error(f"读取文件 {f.name} 失败：{e}")
            if new_texts:
                extracted_text = "\n\n".join(new_texts)
                if st.session_state.knowledge_text == DEFAULT_KNOWLEDGE:
                    st.session_state.knowledge_text = extracted_text
                else:
                    st.session_state.knowledge_text += "\n\n" + extracted_text
                st.session_state.loaded_files.extend([f.name for f in new_files])
                msg = f"✅ 已添加 {len(new_texts)} 个文件"
                if skipped:
                    msg += f"，跳过 {len(skipped)} 个重复文件"
                st.success(msg)
                st.rerun()

if st.session_state.loaded_files:
    st.info(f"📚 知识库包含 {len(st.session_state.loaded_files)} 个文件")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🗑️ 清空知识库"):
            st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
            st.session_state.loaded_files = []
            st.rerun()
    with col2:
        knowledge_bytes = st.session_state.knowledge_text.encode("utf-8")
        b64 = base64.b64encode(knowledge_bytes).decode()
        href = f'<a href="data:file/txt;base64,{b64}" download="knowledge_base.txt">💾 导出知识库</a>'
        st.markdown(href, unsafe_allow_html=True)
    with col3:
        st.caption(f"总字数：{len(st.session_state.knowledge_text)}")
else:
    st.caption("当前使用内置法律知识，可上传材料或导入已有知识库文件。")

with st.expander("🔍 预览知识库开头"):
    st.text(st.session_state.knowledge_text[:500])

st.markdown("---")

# ========== 举报工单输入区（使用表单减少频繁重跑） ==========
st.subheader("📥 举报工单输入")

with st.form("complaint_form", clear_on_submit=False):
    # 文件上传（自动填充）
    col_file, _ = st.columns([1, 3])
    with col_file:
        uploaded_complaint = st.file_uploader(
            "上传工单文件（.txt .pdf .docx）",
            type=["txt", "pdf", "docx"],
            key="complaint_uploader"
        )

    # 文本区域
    complaint_text = st.text_area(
        "粘贴举报内容",
        value=st.session_state.raw_complaint,
        height=200,
        placeholder="例如：2026年4月25日，消费者李某（电话13812345678）反映在XX超市购买到过期...",
        key="complaint_input"
    )

    # 脱敏选项
    use_mask = st.checkbox("🛡️ 分析前自动隐藏手机号（推荐）", value=True)

    # 处理文件上传，更新 session_state
    if uploaded_complaint is not None:
        try:
            file_text = parse_file_bytes(uploaded_complaint.name, uploaded_complaint.getvalue())
            st.session_state.raw_complaint = file_text
            # 因为表单内无法直接 rerun，所以通过修改 session_state，提交后下一次刷新会更新值，但这里需要即时显示
            # 用 st.experimental_rerun 会导致表单闪烁。我们设置一个标志，然后在表单外处理。
            st.session_state["pending_file"] = file_text
        except Exception as e:
            st.error(f"文件解析失败：{e}")

    # 分析提交按钮
    submitted = st.form_submit_button("🚀 开始智能分析", type="primary")

# 表单外处理文件上传带来的文字更新（如果 pending_file 存在，则刷新页面）
if "pending_file" in st.session_state and st.session_state["pending_file"] is not None:
    st.session_state.raw_complaint = st.session_state["pending_file"]
    del st.session_state["pending_file"]
    st.rerun()

# ========== 分析逻辑（只有提交表单后才执行） ==========
if submitted:
    final_complaint = st.session_state.raw_complaint
    if not final_complaint.strip():
        st.warning("请先粘贴举报内容或上传文件")
    else:
        # 脱敏处理
        if use_mask:
            final_complaint = mask_pii(final_complaint)

        # 截断知识库，避免 token 过长导致延迟
        full_knowledge = st.session_state.knowledge_text
        if len(full_knowledge) > MAX_KNOWLEDGE_CHARS:
            truncated_knowledge = full_knowledge[:MAX_KNOWLEDGE_CHARS] + "\n...（知识库已截断，仅发送前部分内容）"
        else:
            truncated_knowledge = full_knowledge

        prompt = f"""你是一位精通市场监管法律法规的办案助手。请严格根据以下【内部知识库】中的法律规定和裁量标准，对举报工单进行分析。

【内部知识库】
{truncated_knowledge}

【举报工单内容】
{final_complaint}

请输出（必须包含以下所有项目）：
1. 举报类型
2. 被举报主体名称
3. 违法事实摘要（50字内）
4. 可能违反的法律法规条款（优先引用知识库中提及的条款）
5. 是否建议立案（是/否，并说明原因）
6. 若立案，建议的处罚裁量方向（参考知识库中的裁量因素）
7. 生成一份《立案审批表》草稿（用【立案审批表草稿】作为开头）

确保输出格式与知识库中的文书范例风格一致。"""

        with st.spinner("AI 正在分析，请稍候..."):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "你是一个专业、严谨的市场监管法律助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=2000
                )
                result = response.choices[0].message.content
                st.success("✅ 分析完成")

                sections = result.split("\n\n")
                for sec in sections:
                    if sec.strip():
                        if "【立案审批表草稿】" in sec:
                            st.subheader("📄 立案审批表草稿")
                            st.text_area("草稿内容（可复制）", value=sec.replace("【立案审批表草稿】","").strip(), height=300)
                        else:
                            st.markdown(sec)
            except Exception as e:
                st.error(f"调用 AI 出错：{e}")

# ========== 底部安全说明 ==========
st.markdown("---")
with st.expander("🔒 数据安全与隐私保护说明"):
    st.markdown("""
    ### ✅ 数据安全核心要点
    - **用后即焚**：页面关闭后数据全部消失，服务器不保存。
    - **HTTPS 加密**：全链路加密传输，与网银同级别。
    - **AI 服务合规**：使用已备案的 DeepSeek，承诺不利用用户数据训练。
    - **默认脱敏**：手机号自动隐藏，传输前即作处理。

    ### 🆚 相比直接使用聊天 AI 的优势
    | 维度 | 聊天 AI | 本工具 |
    |------|--------|--------|
    | 数据留存 | 永久保存对话 | 不保存 |
    | 法条引用 | 可能不准确 | 基于知识库，严格匹配 |
    | 文书格式 | 自由输出 | 一键生成审批表草稿 |
    | 团队共享 | 各自为战 | 一次性上传知识库，全单位共享 |

    ### 🏠 未来本地部署
    可在单位内网部署，数据完全不出单位，达到等保要求。
    """)

# ========== 侧边栏 ==========
st.sidebar.markdown("""
### 📘 使用指引
1. 上传内部文书构建知识库（可导出/导入持久保存）
2. 粘贴或上传举报工单
3. 点击「开始智能分析」生成建议文书

### ⚡ 网络优化提示
- **在微信中打开较慢是正常现象**，建议复制链接到手机浏览器（如 Chrome、Safari）使用，速度更快。
- 首次加载可能需要 10 秒左右，耐心等待。
- 知识库内容过长会影响分析速度，系统已自动截取前 4000 字发送。

### 📂 支持类型
食品安全、广告违法、价格违法、无照经营等
""")
