import streamlit as st
from openai import OpenAI

# ========== 配置区 ==========
API_KEY = st.secrets["API_KEY"]          # 正式部署时从 Secrets 读取
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
# ============================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 页面设置
st.set_page_config(page_title="市监举报辅助系统", layout="wide")
st.title("📋 举报工单智能分析与文书辅助")

# ========== 默认范例（可被用户覆盖） ==========
DEFAULT_EXAMPLE = """
# 业务要求
- 引用法律条款请精确到条、款、项。
- 裁量说理必须包含：是否初次违法、货值金额、有无危害后果。
- 文书草稿请使用正式格式，留出承办人签字栏。

# 参考范例

## 食品安全类
举报内容：消费者反映在XX超市买到过期“XX牌”酸奶，生产日期2026年1月，保质期5个月。
分析示范：
1. 举报类型：食品安全
2. 被举报主体：XX超市
3. 违法事实摘要：涉嫌经营超过保质期的食品
4. 违反条款：《中华人民共和国食品安全法》第三十四条第（十）项
5. 是否立案：是
6. 裁量方向：货值小、初次违法，依据《食品安全法》第一百二十四条，建议从轻，处5000元罚款
7. 【立案审批表草稿】
   案由：涉嫌经营超过保质期食品案
   当事人：XX超市
   违法事实：2026年4月25日，消费者在该超市购得过期酸奶……
   立案依据：《食品安全法》第三十四条、第一百二十四条。
   承办人意见：建议立案调查。
   承办人：_________    日期：_________

## 广告违法类
举报内容：XX网店在商品页面宣称“全网最低价”，但无法提供依据。
分析示范：
1. 举报类型：广告违法（虚假宣传）
2. 被举报主体：XX网店
3. 违法事实摘要：使用“全网最低价”绝对化用语且无依据
4. 违反条款：《中华人民共和国广告法》第九条第（三）项
5. 是否立案：是
6. 裁量方向：首次网店发布，及时改正，依据《广告法》第五十七条，建议从轻，处2000元罚款
7. 【立案审批表草稿】
   案由：涉嫌发布违法广告案
   当事人：XX网店
   违法事实：……（略）
   立案依据：《广告法》第九条、第五十七条。
   承办人意见：建议立案调查。
   承办人：_________    日期：_________
"""

# ========== 初始化 session_state（保存用户编辑的范例） ==========
if "example_text" not in st.session_state:
    st.session_state.example_text = DEFAULT_EXAMPLE

# ========== 界面布局：业务指导编辑区 ==========
st.subheader("📝 业务指导与参考范例（可在此修改，AI将据此分析）")

# 文本输入框，显示当前范例，高度300像素
example_input = st.text_area(
    "编辑业务要求和范例（支持 Markdown 格式）",
    value=st.session_state.example_text,
    height=300,
    key="example_area"       # 固定 key，防止刷新后丢失用户正在输入的内容
)

# 按钮行
col1, col2 = st.columns(2)
with col1:
    if st.button("💾 保存当前范例（本次会话有效）"):
        st.session_state.example_text = example_input
        st.success("✅ 范例已保存，下次分析将使用新范例")
with col2:
    if st.button("🔄 恢复默认范例"):
        st.session_state.example_text = DEFAULT_EXAMPLE
        st.rerun()            # 刷新页面，让文本框显示默认范例

# 分割线
st.markdown("---")

# ========== 举报内容输入区 ==========
st.subheader("📥 粘贴举报工单原文")
complaint_text = st.text_area(
    "举报内容（可含时间、地点、被举报人、事实描述等）",
    height=200,
    placeholder="例如：2026年4月25日，消费者李某反映在XX超市购买到过期..."
)

# ========== 动态构建提示词（将用户范例嵌入） ==========
def build_prompt(complaint, example):
    return f"""你是一位精通市场监管法律法规的办案助手。请严格参考下面的业务指导和范例，对举报工单进行分析。

## 业务指导与参考范例
{example}

## 需要分析的举报工单
{complaint}

请按照范例中的格式输出，必须包含：
1. 举报类型
2. 被举报主体名称
3. 违法事实摘要（一句话）
4. 可能违反的法律法规条款
5. 是否建议立案（是/否，并给出理由）
6. 若立案，建议的处罚裁量方向
7. 生成《立案审批表》草稿（用【立案审批表草稿】作为开头）

确保引用法条准确，裁量理由充分。"""

# ========== 分析按钮及逻辑 ==========
if st.button("🚀 智能分析", type="primary"):
    if not complaint_text.strip():
        st.warning("请先粘贴举报内容")
    else:
        with st.spinner("AI正在分析，请稍候..."):
            try:
                current_example = st.session_state.example_text
                prompt = build_prompt(complaint_text, current_example)

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

                # 分段展示结果
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

# ========== 侧边栏说明 ==========
st.sidebar.markdown("""
### 使用说明
1. **上方业务指导框**：可增删案例、修改裁量要求。
2. 点击「保存当前范例」，再粘贴举报工单。
3. 点「智能分析」，AI 会严格模仿范例格式和裁量风格。
4. 如需重置，点「恢复默认范例」即可。

### 支持投诉类型
- 食品安全、药品/医疗器械
- 广告虚假宣传、商标侵权
- 价格违法、不正当竞争
- 无照经营、超范围经营
""")