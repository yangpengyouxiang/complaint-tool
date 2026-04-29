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
MAX_KNOWLEDGE_CHARS = 4000          # 知识库截断长度
# ============================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

st.set_page_config(page_title="市监举报辅助系统", layout="wide", initial_sidebar_state="collapsed")

# 简洁标题
st.markdown("## 📋 举报工单智能分析辅助工具")

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

# ========== 文件解析（含缓存） ==========
@st.cache_data(show_spinner=False)
def parse_file_bytes(file_name, file_bytes):
    name = file_name.lower()
    if name.endswith(".txt"):
        return file_bytes.decode("utf-8")
    elif name.endswith(".pdf"):
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            if page.extract_text():
                text += page.extract_text()
        return text
    elif name.endswith(".docx"):
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join([para.text for para in doc.paragraphs])
    else:
        raise ValueError("不支持的文件类型")

# ========== 会话状态初始化 ==========
if "knowledge_text" not in st.session_state:
    st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
if "loaded_files" not in st.session_state:
    st.session_state.loaded_files = []
if "raw_complaint" not in st.session_state:
    st.session_state.raw_complaint = ""

# ========== 知识库管理区（紧凑布局） ==========
with st.expander("📂 知识库管理（上传内部文件 / 导入导出）", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        uploaded_knowledge = st.file_uploader("上传文件（支持 .txt .pdf .docx）",
                                              type=["txt", "pdf", "docx"],
                                              accept_multiple_files=True,
                                              key="knowledge_uploader")
    with col2:
        uploaded_import = st.file_uploader("导入已导出的知识库",
                                           type=["txt"],
                                           key="knowledge_import")
        if uploaded_import:
            try:
                imported = uploaded_import.getvalue().decode("utf-8")
                st.session_state.knowledge_text = imported
                st.session_state.loaded_files = ["导入的知识库"]
                st.success("知识库已导入")
                st.rerun()
            except Exception as e:
                st.error(f"导入失败：{e}")

    if uploaded_knowledge:
        if st.button("确认添加至知识库"):
            existing = st.session_state.loaded_files
            new_files = []
            skipped = []
            for f in uploaded_knowledge:
                if f.name in existing:
                    skipped.append(f.name)
                else:
                    new_files.append(f)
            if not new_files:
                st.warning("本次上传的文件均已存在")
            else:
                new_texts = []
                for f in new_files:
                    try:
                        text = parse_file_bytes(f.name, f.getvalue())
                        new_texts.append(f"【{f.name}】\n{text}")
                    except Exception as e:
                        st.error(f"解析 {f.name} 失败：{e}")
                if new_texts:
                    if st.session_state.knowledge_text == DEFAULT_KNOWLEDGE:
                        st.session_state.knowledge_text = "\n\n".join(new_texts)
                    else:
                        st.session_state.knowledge_text += "\n\n" + "\n\n".join(new_texts)
                    st.session_state.loaded_files.extend([f.name for f in new_files])
                    st.success(f"已添加 {len(new_texts)} 个文件")
                    st.rerun()

    # 显示知识库状态
    if st.session_state.loaded_files:
        col_a, col_b, col_c = st.columns([2, 1, 1])
        with col_a:
            st.caption(f"已加载 {len(st.session_state.loaded_files)} 个文件，总字数 {len(st.session_state.knowledge_text)}")
        with col_b:
            if st.button("清空知识库", key="clear_kb"):
                st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
                st.session_state.loaded_files = []
                st.rerun()
        with col_c:
            kb_bytes = st.session_state.knowledge_text.encode("utf-8")
            b64 = base64.b64encode(kb_bytes).decode()
            href = f'<a href="data:file/txt;base64,{b64}" download="knowledge_base.txt">导出知识库</a>'
            st.markdown(href, unsafe_allow_html=True)
    else:
        st.caption("当前使用默认法律知识，可上传文件构建专属知识库")

# ========== 工单输入与分析（核心表单） ==========
st.markdown("---")
with st.form("main_form", clear_on_submit=False):
    left, right = st.columns([3, 1])
    with left:
        st.markdown("#### 📥 举报工单内容")
        complaint_text = st.text_area(
            "输入或粘贴举报内容",
            value=st.session_state.raw_complaint,
            height=180,
            placeholder="如：2026年4月25日，李某（电话13812345678）反映在XX超市购买到过期食品……",
            label_visibility="collapsed",
            key="complaint_area"
        )
    with right:
        st.markdown("#### 📎 上传工单文件")
        uploaded_complaint = st.file_uploader(
            "支持 .txt .pdf .docx",
            type=["txt", "pdf", "docx"],
            label_visibility="collapsed",
            key="complaint_upload"
        )
        if uploaded_complaint is not None:
            try:
                file_text = parse_file_bytes(uploaded_complaint.name, uploaded_complaint.getvalue())
                st.session_state.raw_complaint = file_text
                # 使用一个标志，在表单外刷新
                st.session_state["pending_file"] = file_text
            except Exception as e:
                st.error(f"解析失败：{e}")

    # 脱敏选项与分析按钮同行
    col_opt, col_btn = st.columns([2, 1])
    with col_opt:
        use_mask = st.checkbox("🛡️ 自动隐藏举报内容中的手机号（推荐）", value=True)
    with col_btn:
        submitted = st.form_submit_button("🚀 开始智能分析", type="primary", use_container_width=True)

# 处理文件上传后刷新
if "pending_file" in st.session_state and st.session_state["pending_file"] is not None:
    st.session_state.raw_complaint = st.session_state["pending_file"]
    del st.session_state["pending_file"]
    st.rerun()

# ========== 分析结果展示 ==========
if submitted:
    final_text = st.session_state.raw_complaint
    if not final_text.strip():
        st.warning("请先输入举报内容")
    else:
        if use_mask:
            final_text = mask_pii(final_text)

        # 截断知识库
        full_kb = st.session_state.knowledge_text
        if len(full_kb) > MAX_KNOWLEDGE_CHARS:
            kb_section = full_kb[:MAX_KNOWLEDGE_CHARS] + "\n...(知识库已截断)"
        else:
            kb_section = full_kb

        prompt = f"""你是精通市场监管法规的办案助手，请依据以下知识库分析举报工单，并严格按格式输出：

【知识库】
{kb_section}

【工单内容】
{final_text}

输出必须包含：
1. 举报类型
2. 被举报主体
3. 违法事实摘要（50字内）
4. 涉嫌违反条款（优先知识库内条文）
5. 是否建议立案及理由
6. 裁量建议（参照知识库裁量因素）
7. 【立案审批表草稿】（完整草稿，含案由、当事人、违法事实、立案依据、承办人意见）"""

        with st.spinner("AI 正在分析并生成文书，请稍候..."):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "你是一位严谨的市场监管法律助手，注意隐私保护。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=2000
                )
                result = response.choices[0].message.content
                st.success("分析完成")

                # 分段展示
                parts = result.split("\n\n")
                for part in parts:
                    if part.strip():
                        if "【立案审批表草稿】" in part:
                            st.markdown("#### 📄 立案审批表草稿")
                            clean = part.replace("【立案审批表草稿】", "").strip()
                            st.text_area("草稿（可复制）", value=clean, height=300, label_visibility="collapsed")
                        else:
                            st.markdown(part)
            except Exception as e:
                st.error(f"AI 调用出错：{e}")

# ========== 底部安全说明（简洁折叠） ==========
st.markdown("---")
with st.expander("🔒 数据安全说明"):
    st.markdown("- 用后即焚：关闭页面后所有数据消失，服务器不保留")
    st.markdown("- 传输加密：全程 HTTPS 加密，与网银同级")
    st.markdown("- AI 合规：使用已备案的 DeepSeek，不利用用户数据训练")
    st.markdown("- 自动脱敏：手机号中间四位变星号，分析时已预处理")

# ========== 侧边栏（极简提示） ==========
st.sidebar.markdown("""
**📌 使用提示**
- 知识库上传后可导出保存，下次导入即可复用。
- 微信内打开较慢，建议复制链接到手机浏览器使用。
- 系统默认隐藏手机号，可手动取消勾选。
""")
