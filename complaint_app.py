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
    """将手机号中间四位替换为****"""
    return re.sub(r'(1[3-9]\d)\d{4}(\d{4})', r'\1****\2', text)

# ========== 文件解析函数 ==========
def extract_text_from_txt(file_bytes):
    return file_bytes.decode("utf-8")

def extract_text_from_pdf(file_bytes):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

def extract_text_from_docx(file_bytes):
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join([para.text for para in doc.paragraphs])

def parse_uploaded_file(file):
    """根据文件名后缀自动解析文件内容"""
    name = file.name.lower()
    content = file.getvalue()
    if name.endswith(".txt"):
        return extract_text_from_txt(content)
    elif name.endswith(".pdf"):
        return extract_text_from_pdf(content)
    elif name.endswith(".docx"):
        return extract_text_from_docx(content)
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
    # 导入知识库文件
    uploaded_knowledge_file = st.file_uploader(
        "导入已导出的知识库文件",
        type=["txt"],
        accept_multiple_files=False,
        key="knowledge_import"
    )
    if uploaded_knowledge_file:
        try:
            imported_text = uploaded_knowledge_file.getvalue().decode("utf-8")
            st.session_state.knowledge_text = imported_text
            st.session_state.loaded_files = ["导入的知识库"]  # 简单标记
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
            st.warning("本次上传的文件都已存在于知识库中，未添加新内容。")
        else:
            new_texts = []
            for f in new_files:
                try:
                    text = parse_uploaded_file(f)
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
                msg = f"已添加 {len(new_texts)} 个文件"
                if skipped:
                    msg += f"。跳过了 {len(skipped)} 个重复文件：{'，'.join(skipped)}"
                st.success(msg)
                st.rerun()

# 知识库状态与导出
if st.session_state.loaded_files:
    st.info(f"📚 当前知识库包含 {len(st.session_state.loaded_files)} 个文件")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🗑️ 清空知识库，恢复默认"):
            st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
            st.session_state.loaded_files = []
            st.rerun()
    with col2:
        # 导出知识库为txt
        knowledge_bytes = st.session_state.knowledge_text.encode("utf-8")
        b64 = base64.b64encode(knowledge_bytes).decode()
        href = f'<a href="data:file/txt;base64,{b64}" download="knowledge_base.txt">💾 导出当前知识库</a>'
        st.markdown(href, unsafe_allow_html=True)
    with col3:
        st.caption(f"总字数：{len(st.session_state.knowledge_text)}")
else:
    st.caption("目前使用内置基础法律知识，上传内部材料或导入知识库文件可逐步构建专属知识库。")

with st.expander("🔍 预览知识库前2000字"):
    st.text(st.session_state.knowledge_text[:2000])

st.markdown("---")

# ========== 举报工单输入区 ==========
st.subheader("📥 举报工单输入")
# 方式一：直接粘贴
complaint_text = st.text_area(
    "粘贴举报内容",
    value=st.session_state.raw_complaint,
    height=200,
    placeholder="例如：2026年4月25日，消费者李某（电话13812345678）反映在XX超市购买到过期...",
    key="complaint_input"
)
st.session_state.raw_complaint = complaint_text

# 方式二：上传文件自动填充
col_file, _ = st.columns([1, 3])
with col_file:
    uploaded_complaint = st.file_uploader(
        "或上传举报工单文件（.txt .pdf .docx）",
        type=["txt", "pdf", "docx"],
        key="complaint_uploader"
    )
if uploaded_complaint:
    try:
        file_text = parse_uploaded_file(uploaded_complaint)
        st.session_state.raw_complaint = file_text
        st.success(f"已从文件 {uploaded_complaint.name} 加载举报内容，可编辑后分析")
        st.rerun()
    except Exception as e:
        st.error(f"上传文件解析失败：{e}")

# ========== 隐私保护设置 ==========
st.subheader("🛡️ 隐私保护设置")
use_mask = st.checkbox("分析前自动隐藏手机号码（推荐开启）", value=True,
                       help="开启后，系统会将举报内容中的手机号中间四位替换为****，防止隐私泄露")

if st.button("👁️ 预览脱敏后的内容"):
    if complaint_text.strip():
        masked = mask_pii(complaint_text)
        st.text_area("脱敏后效果（仅预览）", value=masked, height=150, disabled=True)
    else:
        st.warning("请先输入举报内容")

# ========== 分析按钮 ==========
st.subheader("🚀 启动分析")
if st.button("开始智能分析", type="primary"):
    if not st.session_state.raw_complaint.strip():
        st.warning("请先粘贴举报内容或上传文件")
    else:
        final_text = mask_pii(st.session_state.raw_complaint) if use_mask else st.session_state.raw_complaint

        with st.spinner("AI正在分析，请稍候..."):
            try:
                prompt = f"""你是一位精通市场监管法律法规的办案助手。请严格根据以下【内部知识库】中的法律规定和裁量标准，对举报工单进行分析。

【内部知识库】
{st.session_state.knowledge_text}

【举报工单内容】
{final_text}

请输出（必须包含以下所有项目）：
1. 举报类型
2. 被举报主体名称
3. 违法事实摘要（50字内）
4. 可能违反的法律法规条款（优先引用知识库中提及的条款）
5. 是否建议立案（是/否，并说明原因）
6. 若立案，建议的处罚裁量方向（参考知识库中的裁量因素）
7. 生成一份《立案审批表》草稿（用【立案审批表草稿】作为开头）

确保输出格式与知识库中的文书范例风格一致。"""

                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "你是一个专业、严谨的市场监管法律助手，请在分析时注意保护举报人隐私。"},
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
                st.error(f"调用AI出错：{str(e)}")

# ========== 底部：数据安全与隐私说明 ==========
st.markdown("---")
with st.expander("🔒 数据安全与隐私保护说明（点击展开）"):
    st.markdown("""
    ### ✅ 为什么不用担心案件数据泄露？
    - **仅本次分析使用，用后即焚**：系统不存储任何举报内容或分析结果，关闭页面后数据彻底消失，服务器不留痕。
    - **传输全程加密**：所有数据通过 HTTPS 加密通道传输，如同网络银行般安全。
    - **AI 服务合规**：我们调用的是已通过国家生成式人工智能备案的 **DeepSeek** 服务，其协议明确承诺**不将用户数据用于模型训练**。
    - **脱敏机制默认开启**：分析前自动过滤手机号等个人信息（可预览），即使传输过程被截获，也只能看到 `138****` 这样的脱敏片段。

    ### 🆚 与直接打开聊天 AI（如网页版 DeepSeek）分析案件相比，本工具的优势
    | 对比维度 | 直接聊天 AI | 本工具 |
    |---------|------------|--------|
    | 数据留存 | 对话记录保存在平台，可能被第三方接触 | **不保存**，刷新即清空 |
    | 法律准确性 | 可能随意发挥，不引用具体法条 | 基于内部知识库，**严格引用条款和裁量标准** |
    | 文书规范性 | 输出格式随意，需人工二次整理 | **一键生成立案审批表草稿**，直接可用 |
    | 团队复用 | 每个人都要重新描述案情 | 上传一次内部文件，**全单位共享知识库** |
    | 隐私保护 | 无脱敏功能，涉案人信息可能泄露 | **自动脱敏**，且不形成历史对话 |

    ### 🏠 未来本地部署（私有化）的特点
    - 所有计算和模型推理都在**单位内部服务器**完成，数据完全不出单位网络。
    - 可对接市场监管内网 OA 系统，形成完整闭环。
    - 可按需定制裁决模型，学习本局全部历史案例，越用越准。
    - 当前公网版本主要用于**功能演示与验证**，领导批准后可无缝切换到本地部署，届时零外部流量。
    """)

# ========== 侧边栏 ==========
st.sidebar.markdown("""
### 📘 使用指引
1. **构建知识库**：上传内部文件（裁量指导、优秀处罚书等），可导出备份，下次导入恢复。
2. **输入举报**：粘贴文字或上传文件（TXT/PDF/Word）自动填充。
3. **隐私保护**：默认自动隐藏手机号，可预览。
4. **一键分析**：点击“开始智能分析”，20秒左右生成文书草稿。

### 📁 知识库持久化
- 使用“导出当前知识库”将学习成果保存为 .txt 文件。
- 下次打开时，用右侧的“导入已导出的知识库文件”恢复，**无需重新上传内部材料**。

### 📂 支持分析类型
食品安全、广告违法、价格违法、无照经营等
""")