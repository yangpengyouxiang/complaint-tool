import streamlit as st
from openai import OpenAI
import PyPDF2
import docx
import io

# ========== 配置区 ==========
API_KEY = st.secrets["API_KEY"]
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
# ============================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

st.set_page_config(page_title="市监举报辅助系统", layout="wide")
st.title("📋 举报工单智能分析与文书辅助")

# ========== 内置默认知识（当用户未上传文件时使用） ==========
DEFAULT_KNOWLEDGE = """
常用市场监督管理法律法规要点：
- 食品安全法第34条：禁止经营超过保质期的食品。
- 广告法第9条：广告不得使用“国家级”、“最高级”、“最佳”等绝对化用语。
- 无证无照经营查处办法第2条：任何单位或者个人不得违反法律、法规、国务院决定的规定，从事无证无照经营。
裁量参考因素：初次违法、货值金额、危害后果、是否主动消除影响、配合调查程度等。
"""

# ========== 初始化 session_state ==========
if "knowledge_text" not in st.session_state:
    st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []  # 记录文件名列表

# ========== 文件解析函数 ==========
def extract_text_from_txt(file):
    return file.getvalue().decode("utf-8")

def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.getvalue()))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

def extract_text_from_docx(file):
    doc = docx.Document(io.BytesIO(file.getvalue()))
    return "\n".join([para.text for para in doc.paragraphs])

def process_uploaded_files(uploaded_files):
    """处理上传的文件列表，返回合并后的文本和文件名列表"""
    all_text = []
    file_names = []
    for file in uploaded_files:
        try:
            if file.name.endswith(".txt"):
                text = extract_text_from_txt(file)
            elif file.name.endswith(".pdf"):
                text = extract_text_from_pdf(file)
            elif file.name.endswith(".docx"):
                text = extract_text_from_docx(file)
            else:
                st.warning(f"不支持的文件类型：{file.name}，已跳过")
                continue
            all_text.append(f"【文件：{file.name}】\n{text}")
            file_names.append(file.name)
        except Exception as e:
            st.error(f"读取文件 {file.name} 失败：{e}")
    return "\n\n".join(all_text), file_names

# ========== 界面布局 ==========
st.subheader("📂 上传内部文档（Word/PDF/TXT），AI 将学习这些内容")

uploaded = st.file_uploader(
    "支持批量上传，格式：.txt .pdf .docx",
    type=["txt", "pdf", "docx"],
    accept_multiple_files=True,
    key="file_uploader"
)

# 如果有新文件上传，进行处理
if uploaded:
    extracted_text, new_files = process_uploaded_files(uploaded)
    # 如果之前已有文件，则追加；否则替换为新的知识文本（也可以设计成替换模式，这里用替换更清晰）
    if st.button("📥 确认上传并学习"):
        st.session_state.knowledge_text = extracted_text
        st.session_state.uploaded_files = new_files
        st.success(f"已学习 {len(new_files)} 个文件，AI 将基于这些内容进行分析。")
        st.rerun()

# 显示当前已加载的文件
if st.session_state.uploaded_files:
    st.info(f"当前知识库包含文件：{'，'.join(st.session_state.uploaded_files)}")
    if st.button("🗑️ 清空已上传的文件，恢复默认知识"):
        st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
        st.session_state.uploaded_files = []
        st.rerun()
else:
    st.caption("目前使用内置基础法律知识，上传内部材料可提升分析准确性。")

# 可折叠区域预览当前知识文本（可选）
with st.expander("🔍 查看当前知识库内容"):
    st.text(st.session_state.knowledge_text[:2000])  # 只显示前2000字，避免撑爆

st.markdown("---")

# ========== 举报输入区 ==========
st.subheader("📥 粘贴举报工单原文")
complaint_text = st.text_area(
    "举报内容",
    height=200,
    placeholder="例如：2026年4月25日，消费者李某反映在XX超市购买到过期..."
)

# ========== 构造提示词（将知识库全文注入） ==========
def build_prompt(complaint, knowledge):
    return f"""你是一位精通市场监管法律法规的办案助手。请严格根据以下【内部知识库】中的法律规定和裁量标准，对举报工单进行分析。

【内部知识库】
{knowledge}

【举报工单内容】
{complaint}

请输出（必须包含以下所有项目）：
1. 举报类型
2. 被举报主体名称
3. 违法事实摘要（50字内）
4. 可能违反的法律法规条款（优先引用知识库中提及的条款）
5. 是否建议立案（是/否，并说明原因）
6. 若立案，建议的处罚裁量方向（参考知识库中的裁量因素）
7. 生成一份《立案审批表》草稿（用【立案审批表草稿】作为开头）

确保输出格式与知识库中的文书范例风格一致。"""

# ========== 分析按钮 ==========
if st.button("🚀 智能分析", type="primary"):
    if not complaint_text.strip():
        st.warning("请先粘贴举报内容")
    else:
        with st.spinner("AI正在分析，请稍候..."):
            try:
                # 使用当前知识库
                prompt = build_prompt(complaint_text, st.session_state.knowledge_text)
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

                # 分段展示
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

# ========== 侧边栏 ==========
st.sidebar.markdown("""
### 使用说明
1. **上传文件**：把局里的裁量指导意见、优秀处罚决定书等（Word/PDF/TXT）拖到上方上传区，点击“确认上传并学习”。
2. **分析工单**：粘贴举报内容，点击“智能分析”。
3. AI 会根据您上传的内部文件引用法条、给出裁量建议，完全模仿文件内的风格。
4. 如需更换文件，清空后重新上传即可。

### 支持文件格式
- 文本文件 (.txt)
- PDF 文件 (.pdf)
- Word 文档 (.docx)
""")
