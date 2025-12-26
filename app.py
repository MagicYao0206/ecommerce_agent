import streamlit as st
from agent import handle_user_input

# 页面配置
st.set_page_config(
    page_title="电商智能导购Agent",
    page_icon="🛒",
    layout="wide"
)

# 标题
st.title("🛒 电商智能导购Agent - 小智")
st.subheader("需求挖掘→商品推荐→对比→下单引导全流程")

# 初始化会话历史（Streamlit会话状态）
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "你好呀～我是小智，有什么想买的商品可以告诉我，我会帮你推荐最合适的哦！"}
    ]

# 显示历史消息
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 用户输入框
if user_input := st.chat_input("请输入你的购物需求（如：500元内适合油性皮肤的粉底液）"):
    # 添加用户消息到历史
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # 调用Agent处理输入
    with st.chat_message("assistant"):
        with st.spinner("小智正在思考..."):
            try:
                response = handle_user_input(user_input)
                st.markdown(response)
            except Exception as e:
                error_msg = "抱歉，处理请求时出现错误，请稍后再试~"
                st.markdown(error_msg)
                st.error(f"错误详情: {str(e)}")
                response = error_msg
    # 添加助手消息到历史
    st.session_state.messages.append({"role": "assistant", "content": response})

if st.sidebar.button("清空对话历史"):
    st.session_state.messages = [
        {"role": "assistant", "content": "你好呀～我是小智，有什么想买的商品可以告诉我，我会帮你推荐最合适的哦！"}
    ]
    st.rerun()

# 优化会话日志显示
# st.sidebar.subheader("会话日志")
# for idx, msg in enumerate(st.session_state.messages):
#     # 限制显示长度并添加换行
#     content = msg['content'][:50].replace('\n', ' ') + ('...' if len(msg['content'])>50 else '')
#     st.sidebar.text(f"{idx+1}. {msg['role']}: {content}")