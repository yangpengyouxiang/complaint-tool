import streamlit as st
from openai import OpenAI
import re
import io
import base64

# ========== 配置 ==========
API_KEY = st.secrets["API_KEY"]
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_KNOWLEDGE_CHARS = 4000

# ========== 惰性导入大型库 ==========
@st.cache_resource
def get_client():
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)

def _pypdf2():
    import PyPDF2
    return PyPDF2

def _docx():
    import docx
    return docx

def _openpyxl():
    import openpyxl
    return openpyxl

# ========== 基础设置（极简） ==========
st.set_page_config(page_title="市监举报辅助")
st.markdown("## 📋 举报工单智能分析")

# ========== 默认知识 ==========
DEFAULT_KB = (
    "常用市场监督管理法律法规要点：\n"
    "- 食品安全法第34条：禁止经营超过保质期的食品。\n"
    "- 广告法第9条：广告不得使用“国家级”、“最高级”、“最佳”等绝对化用语。\n"
    "- 无证无照经营查处办法第2条：不得无证无照经营。\n"
    "裁量参考：初次违法、货值金额、危害后果、配合程度。"
)

def mask_pii(text):
    return re.sub(r'(1[3-9]\d)\d{4}(\d{4})', r'\1****\2', text)

@st.cache_data(show_spinner=False)
def parse_file(file_name, file_bytes):
    name = file_name.lower()
    if name.endswith(".txt"):
        return file_bytes.decode("utf-8")
    if name.endswith(".pdf"):
        r = _pypdf2().PdfReader(io.BytesIO(file_bytes))
        return "".join(p.extract_text() or "" for p in r.pages)
    if name.endswith(".docx"):
        d = _docx().Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in d.paragraphs)
    if name.endswith(".xlsx"):
        wb = _openpyxl().load_workbook(io.BytesIO(file_bytes))
        lines = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                line = " ".join(str(c) for c in row if c is not None)
                if line.strip():
                    lines.append(line)
        return "\n".join(lines)
    raise ValueError("不支持的类型")

# ========== 会话初始化 ==========
if "kb" not in st.session_state:
    st.session_state.kb = DEFAULT_KB
if "kb_files" not in st.session_state:
    st.session_state.kb_files = []
if "complaint" not in st.session_state:
    st.session_state.complaint = ""

client = get_client()

# ========== 知识库（折叠） ==========
with st.expander("📂 知识库（上传/导入/导出）", expanded=False):
    a, b = st.columns([2, 1])
    with a:
        up_kb = st.file_uploader("上传 .txt/.pdf/.docx/.xlsx", type=["txt","pdf","docx","xlsx"],
                                 accept_multiple_files=True, key="upkb")
    with b:
        imp = st.file_uploader("导入.txt", type=["txt"], key="imp")
        if imp:
            try:
                st.session_state.kb = imp.getvalue().decode("utf-8")
                st.session_state.kb_files = ["导入"]
                st.success("已导入")
                st.rerun()
            except Exception as e:
                st.error(e)

    if up_kb:
        if st.button("添加"):
            exist = st.session_state.kb_files
            newf, skip = [], []
            for f in up_kb:
                if f.name in exist:
                    skip.append(f.name)
                else:
                    newf.append(f)
            if not newf:
                st.warning("无新文件")
            else:
                parts = []
                for f in newf:
                    try:
                        t = parse_file(f.name, f.getvalue())
                        parts.append(f"【{f.name}】\n{t}")
                    except Exception as e:
                        st.error(f"{f.name} 解析失败：{e}")
                if parts:
                    joined = "\n\n".join(parts)
                    if st.session_state.kb == DEFAULT_KB:
                        st.session_state.kb = joined
                    else:
                        st.session_state.kb += "\n\n" + joined
                    st.session_state.kb_files.extend([f.name for f in newf])
                    st.success(f"已添加 {len(parts)} 个文件")
                    st.rerun()

    if st.session_state.kb_files:
        st.caption(f"{len(st.session_state.kb_files)} 个文件，{len(st.session_state.kb)} 字")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("清空"):
                st.session_state.kb = DEFAULT_KB
                st.session_state.kb_files = []
                st.rerun()
        with c2:
            b64 = base64.b64encode(st.session_state.kb.encode("utf-8")).decode()
            st.markdown(f'<a href="data:file/txt;base64,{b64}" download="kb.txt">导出</a>', unsafe_allow_html=True)
    else:
        st.caption("默认法律知识")

# ========== 工单表单 ==========
with st.form("main", clear_on_submit=False):
    l, r = st.columns([3, 1])
    with l:
        st.markdown("#### 📥 举报内容")
        txt = st.text_area("输入", value=st.session_state.complaint, height=180,
                           placeholder="粘贴或上传 .txt/.pdf/.docx/.xlsx 文件", label_visibility="collapsed", key="ta")
    with r:
        st.markdown("#### 📎 上传")
        up_comp = st.file_uploader("支持 .txt/.pdf/.docx/.xlsx", type=["txt","pdf","docx","xlsx"],
                                   label_visibility="collapsed", key="upcomp")
        if up_comp:
            try:
                file_txt = parse_file(up_comp.name, up_comp.getvalue())
                st.session_state.complaint = file_txt
                st.session_state["pend"] = file_txt
            except Exception as e:
                st.error(e)

    ocol, bcol = st.columns([2, 1])
    with ocol:
        use_mask = st.checkbox("🛡️ 隐藏手机号", value=True)
    with bcol:
        go = st.form_submit_button("🚀 智能分析", type="primary", use_container_width=True)

if "pend" in st.session_state and st.session_state["pend"] is not None:
    st.session_state.complaint = st.session_state["pend"]
    del st.session_state["pend"]
    st.rerun()

# ========== 分析 ==========
if go:
    raw = st.session_state.complaint
    if not raw.strip():
        st.warning("请输入内容")
    else:
        final = mask_pii(raw) if use_mask else raw
        kb = st.session_state.kb
        if len(kb) > MAX_KNOWLEDGE_CHARS:
            kb = kb[:MAX_KNOWLEDGE_CHARS] + "\n(已截断)"
        prompt = f"""你是办案助手，依据知识库分析工单：

【知识库】
{kb}

【工单】
{final}

输出：
1. 举报类型
2. 被举报主体
3. 违法事实摘要（≤50字）
4. 涉嫌违反条款
5. 是否立案及理由
6. 裁量建议
7. 【立案审批表草稿】（含案由、当事人、违法事实、立案依据、承办人意见）"""
        with st.spinner("分析中……"):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role":"system","content":"严谨的市场监管助手，注意隐私。"},
                              {"role":"user","content":prompt}],
                    temperature=0.1,
                    max_tokens=2000
                )
                ans = resp.choices[0].message.content
                st.success("完成")
                for part in ans.split("\n\n"):
                    if part.strip():
                        if "【立案审批表草稿】" in part:
                            st.markdown("#### 📄 立案审批表草稿")
                            clean = part.replace("【立案审批表草稿】","").strip()
                            st.text_area("可复制", value=clean, height=300, label_visibility="collapsed")
                        else:
                            st.markdown(part)
            except Exception as e:
                st.error(f"出错：{e}")

# ========== 底部信息 ==========
with st.expander("🔒 安全说明"):
    st.caption("用后即焚 · HTTPS加密 · 合规AI · 自动脱敏")

st.sidebar.caption("⏳ 白天高峰可能稍慢，建议复制链接到浏览器打开，或提前5分钟进入页面待命。")
