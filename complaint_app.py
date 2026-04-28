import streamlit as st
from openai import OpenAI

# ========== 配置区 ==========
# 正式部署到云端时，这里改成 st.secrets["API_KEY"]，本地测试先用写死的 key
API_KEY =st.secrets["API_KEY"]  # 记得替换
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
# ============================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 页面设置
st.set_page_config(page_title="市监举报辅助系统", layout="wide")
st.title("📋 举报工单智能分析与文书辅助")

# 输入框
st.subheader("📥 粘贴举报工单原文")
complaint_text = st.text_area(
    "举报内容",
    height=200,
    placeholder="例如：2026年4月25日，消费者反映在XX超市购买到过期食品..."
)

# 提示词模板
PROMPT_TEMPLATE = """你是一位精通市场监管法律法规的办案助手。请对以下举报工单进行分析，并严格按照要求输出：

【举报工单内容】
{complaint}

请输出（必须包含以下所有项目）：
1. 举报类型（如：食品安全/广告违法/价格违法/无照经营等）
2. 被举报主体名称
3. 违法事实摘要（一句话，50字内）
4. 可能违反的法律法规条款（列明法律名称+条号）
5. 是否建议立案（是/否，并说明原因）
6. 若立案，建议的处罚裁量方向（例如：依据《XX法》第X条，货值不足1万，初次违法，建议从轻，处XX元罚款）
7. 根据以上信息，生成一份《立案审批表》草稿（包含：案由、当事人、违法事实、立案依据、承办人意见）

输出格式：用清晰的序号分隔，第七条表格草稿用【立案审批表草稿】作为开头。
"""

if st.button("🚀 智能分析", type="primary"):
    if not complaint_text.strip():
        st.warning("请先粘贴举报内容")
    else:
        with st.spinner("AI正在分析，请稍候..."):
            try:
                prompt = PROMPT_TEMPLATE.format(complaint=complaint_text)
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

# 侧边栏
st.sidebar.markdown("""
### 使用说明
1. 将12315系统或电话记录的举报工单粘贴入框。
2. 点击“智能分析”，AI将自动提取关键信息并生成文书草稿。
3. 结果可复制到电子表格或OA系统。
""")