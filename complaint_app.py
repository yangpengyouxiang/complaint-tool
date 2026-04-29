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

# ========== 内置默认知识 ==========
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
if "loaded_files" not in st.session_state:
    st.session_state.loaded_files = []   # 记录已加载的文件名

# ========== 文件解析函数（不变） ==========
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
    """处理上传文件，返回(新提取文本, 新文件名列表)"""
    new_texts = []
    new_names = []
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
            new_texts.append(f"【文件：{file.name}】\n{text}")
            new_names.append(file.name)
        except Exception as e:
            st.error(f"读取文件 {file.name} 失败：{e}")
    return "\n\n".join(new_texts), new_names

# ========== 界面布局 ==========
st.subheader("📂 上传内部文档（Word/PDF/TXT），AI 将持续学习")

uploaded = st.file_uploader(
    "支持批量上传，格式：.txt .pdf .docx",
    type=["txt", "pdf", "docx"],
    accept_multiple_files=True,
    key="file_uploader"
)

# ========== 处理上传按钮 ==========
if uploaded:
    if st.button("📥 确认添加至知识库"):
        # 先过滤掉已存在的文件
        existing = st.session_state.loaded_files
        new_files = []
        skipped = []
        for f in uploaded:
            if f.name in existing:
                skipped.append(f.name)
            else:
                new_files.append(f)
        
        if not new_files:
            st.warning("本次上传的文件都已存在于知识库中，未添加新内容。")
        else:
            # 提取新文件文本
            extracted_text, added_names = process_uploaded_files(new_files)
            # 追加到现有知识库
            if st.session_state.knowledge_text == DEFAULT_KNOWLEDGE:
                # 如果当前还是默认知识，先清空再添加（避免默认知识和文件混合导致提示词过长，也可保留默认；这里选择替换默认）
                st.session_state.knowledge_text = extracted_text
            else:
                st.session_state.knowledge_text += "\n\n" + extracted_text
            # 更新已加载文件列表
            st.session_state.loaded_files.extend(added_names)
            msg = f"已添加 {len(added_names)} 个文件：{'，'.join(added_names)}"
            if skipped:
                msg += f"。跳过了 {len(skipped)} 个重复文件：{'，'.join(skipped)}"
            st.success(msg)
            st.rerun()

# 显示已加载文件列表
if st.session_state.loaded_files:
    st.info(f"📚 当前知识库包含 {len(st.session_state.loaded_files)} 个文件：{'，'.join(st.session_state.loaded_files)}")
else:
    st.caption("目前使用内置基础法律知识，上传内部材料可逐步构建专属知识库。")

# 按钮：清空知识库
col1, col2 = st.columns(2)
with col1:
    if st.button("🗑️ 清空知识库，恢复默认"):
        st.session_state.knowledge_text = DEFAULT_KNOWLEDGE
        st.session_state.loaded_files = []
        st.rerun()
with col2:
    # 可预览当前知识库总字数
    st.caption(f"知识库总字数：{len(st.session_state.knowledge_text)}")

# 可折叠查看知识库内容
with st.expander("🔍 查看当前知识库前2000字"):
    st.text(st.session_state.knowledge_text[:2000])

st.markdown("---")

# ========== 举报输入区 ==========
st.subheader("📥 粘贴举报工单原文")
complaint_text = st.text_area(
    "举报内容",
    height=200,
    placeholder="例如：2026年4月25日，消费者李某反映在XX超市购买到过期..."
)

# ========== 构造提示词 ==========
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
1. **逐步添砖加瓦**：每次上传新内部文件（Word/PDF/TXT），点击“确认添加至知识库”，内容会**累积**而不是覆盖。
2. 同名文件不会重复添加，系统会自动跳过。
3. 点击“清空知识库”可一键恢复初始状态。
4. 粘贴工单后点击分析，AI会基于您上传的全部文件进行辅助。

### 支持文件格式
- 文本文件 (.txt)
- PDF 文件 (.pdf)
- Word 文档 (.docx)
""")
