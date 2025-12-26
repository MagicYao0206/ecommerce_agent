import warnings
from langchain_core._api.deprecation import LangChainDeprecationWarning
warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)

from langchain_dashscope import ChatDashScope
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
import pandas as pd
import re
from config import (
    DASHSCOPE_API_KEY, 
    DASHSCOPE_MODEL,
    AGENT_PROMPT, 
    PRODUCT_DATA_PATH
)

try:
    from product_search import search_products_from_kg
except ImportError:
    # 降级方案：无 product_search 时直接用 CSV 检索
    def search_products_from_kg(user_input):
        try:
            # 提取价格
            price_match = re.search(r'(\d+)元|(\d+)以内|不超过(\d+)', user_input)
            max_price = int([g for g in price_match.groups() if g][0]) if price_match else 1000
            # 提取肤质
            skin_type = "通用"
            if "油性" in user_input or "油皮" in user_input:
                skin_type = "油性"
            elif "干性" in user_input or "干皮" in user_input:
                skin_type = "干性"
            elif "混合" in user_input:
                skin_type = "混合性"
            # 筛选商品
            filtered_df = product_df[
                (product_df["price"] <= max_price) &
                (product_df["suitable_for"].str.contains(skin_type, na=False))
            ].head(3)
            if filtered_df.empty:
                return "没有找到符合条件的商品，可以调整筛选条件试试～"
            # 生成推荐语
            content = "为你推荐以下商品：\n"
            for idx, row in filtered_df.iterrows():
                content += f"{idx+1}. {row['name']}（¥{row['price']}）：{row.get('advantages', '暂无优势描述')}\n"
            return content
        except Exception as e:
            return f"商品检索失败：{str(e)}"

# 1. 校验 API Key
if not DASHSCOPE_API_KEY:
    raise ValueError(
        "请配置系统环境变量 DASHSCOPE_API_KEY！\n"
        "Windows配置步骤：\n"
        "1. 右键「此电脑」→「属性」→「高级系统设置」→「环境变量」\n"
        "2. 「系统变量」→「新建」，变量名：DASHSCOPE_API_KEY，值：你的阿里云百炼API Key\n"
        "3. 重启VSCode后重新运行"
    )

# 2. 初始化大模型（适配 langchain-dashscope 0.1.8 + dashscope 1.14.1）
llm = ChatDashScope(
    dashscope_api_key=DASHSCOPE_API_KEY,
    model_name=DASHSCOPE_MODEL if DASHSCOPE_MODEL else "qwen-turbo",  # 兜底用轻量版
    temperature=0.7,
    streaming=False  # 关闭流式输出，避免报错
)

# 3. 加载商品数据（容错处理）
try:
    product_df = pd.read_csv(PRODUCT_DATA_PATH, encoding="utf-8")
    # 数据预处理
    product_df['price'] = pd.to_numeric(product_df['price'], errors='coerce')
    product_df = product_df.dropna(subset=['product_id', 'name', 'price'])
    # 填充空值
    product_df['suitable_for'] = product_df['suitable_for'].fillna('通用肤质')
    product_df['advantages'] = product_df['advantages'].fillna('暂无')
    product_df['disadvantages'] = product_df['disadvantages'].fillna('暂无')
except FileNotFoundError:
    raise FileNotFoundError(
        f"未找到商品数据集！\n"
        f"请在 {PRODUCT_DATA_PATH} 路径下创建 product_data.csv，参考以下示例：\n"
        "product_id,name,category,price,budget_range,suitable_for,parameters,advantages,disadvantages,coupon_id,coupon_amount,coupon_condition\n"
        "1001,控油持妆粉底液A,美妆,450,300-500,油性皮肤,持妆8小时，遮瑕力强,控油不脱妆,色号偏黄,C001,50,满400可用"
    )
except Exception as e:
    raise Exception(f"加载数据集失败：{str(e)}（请检查 CSV 格式是否正确）")

# 4. 初始化会话记忆（适配 LangChain 0.1.19）
memory = ConversationBufferMemory(
    memory_key="history",
    return_messages=False,  # 0.1.x 版本核心配置
    human_prefix="用户",
    ai_prefix="小智"
)

# 5. 构建对话链
prompt_template = PromptTemplate(
    input_variables=["history", "input"],
    template=f"{AGENT_PROMPT}\n\n对话历史：{{history}}\n用户当前输入：{{input}}\n你的回复："
)

conversation_chain = ConversationChain(
    llm=llm,
    memory=memory,
    prompt=prompt_template,
    verbose=True,
    return_final_only=True
)

# 6. 商品对比函数
def compare_products(product_names):
    filtered_df = product_df[product_df["name"].isin(product_names)]
    if filtered_df.empty:
        return "未找到对应商品，无法对比～"
    
    compare_table = "| 商品 | 价格 | 适合肤质 | 优点 | 缺点 |\n| --- | --- | --- | --- | --- |\n"
    for _, row in filtered_df.iterrows():
        compare_table += f"| {row['name']} | ¥{row['price']} | {row['suitable_for']} | {row['advantages']} | {row['disadvantages']} |\n"
    
    if len(filtered_df) >= 2:
        advice = f"\n总结：{product_names[0]}和{product_names[1]}各有优势，可根据你的肤质/预算选择～"
    else:
        advice = "\n可输入2款商品名称进行对比（如：粉底液A和B哪个好）"
    
    return compare_table + advice

# 7. 优惠券查询函数
def query_coupons(product_ids):
    if not product_ids:
        return {"content": "当前无可用优惠券信息～"}
    
    filtered_df = product_df[product_df["product_id"].isin(product_ids)]
    if filtered_df.empty:
        return {"content": "当前商品暂无可用优惠券～"}
    
    content = "🎫 可用优惠券汇总：\n"
    for _, row in filtered_df.iterrows():
        if pd.notna(row["coupon_amount"]):
            content += f"- {row['name']}：满{row['coupon_condition']}减{row['coupon_amount']}元，折后¥{row['price']-row['coupon_amount']}\n"
    
    return {"content": content}

# 8. 商品检索函数
def search_products(user_input):
    try:
        # 1. 解析预算（保留原有逻辑）
        price_match = re.search(r'(\d+)元|(\d+)以内|不超过(\d+)', user_input)
        max_price = int([g for g in price_match.groups() if g][0]) if price_match else 1000
        min_price = 0
        budget_range_match = re.search(r'(\d+)-(\d+)元', user_input)
        if budget_range_match:
            min_price = int(budget_range_match.group(1))
            max_price = int(budget_range_match.group(2))
        
        # 2. 解析肤质/使用场景
        skin_or_lip_state = "通用"
        if "油性" in user_input or "油皮" in user_input:
            skin_or_lip_state = "油性"
        elif "干性" in user_input or "干皮" in user_input:
            skin_or_lip_state = "干性"
        elif "干燥" in user_input or "干唇" in user_input:
            skin_or_lip_state = "干燥唇部"
        elif "浅唇" in user_input:
            skin_or_lip_state = "浅唇"
        
        # 3. 解析子品类（根据关键词匹配CSV中的子品类）
        sub_category = ""
        if "口红" in user_input or "唇釉" in user_input:
            sub_category = "美妆-口红"
        elif "粉底液" in user_input:
            sub_category = "美妆-粉底液"
        elif "面霜" in user_input:
            sub_category = "美妆-面霜"
        else:
            sub_category = "美妆"
        
        # 4. 精准筛选：子品类+预算+肤质/唇部状态（确保只从CSV筛选）
        filtered_df = product_df[
            (product_df["category"] == sub_category) &  # 精准匹配子品类
            (product_df["price"] >= min_price) &
            (product_df["price"] <= max_price) &
            (product_df["suitable_for"].str.contains(skin_or_lip_state, na=False))  # 匹配肤质/唇部状态
        ]
        
        # 5. 生成推荐内容（严格用CSV数据，无数据时明确提示）
        if filtered_df.empty:
            return {
                "product_ids": [], 
                "content": f"未找到符合条件的{user_input.split('买')[1]}，可调整预算再尝试～"
            }
        
        content = f"为你推荐以下符合需求的{user_input.split('买')[1]}：\n"
        product_ids = []
        for idx, row in filtered_df.head(3).iterrows():
            discount_price = row["price"] - row["coupon_amount"] if pd.notna(row["coupon_amount"]) else row["price"]
            content += f"{idx+1}. {row['name']}～原价¥{row['price']}，折后¥{discount_price}（满{row['coupon_condition']}减{row['coupon_amount']}元）～优势：{row['advantages']}～\n"
            product_ids.append(row["product_id"])
        
        return {"product_ids": product_ids, "content": content}
    
    except Exception as e:
        return {"product_ids": [], "content": "商品检索失败，请稍后再试～"}

# 9. 核心处理函数
def handle_user_input(user_input):
    # 1. 拦截无关话题
    irrelevant_keywords = ["天气", "星期", "时间", "吃饭", "游戏", "电影"]
    if any(keyword in user_input for keyword in irrelevant_keywords):
        return "不好意思，我主要负责电商购物导购哦～你想了解哪类商品？（如美妆/服装/家电）"
    
    # 2. 拦截售后问题
    after_sales_keywords = ["退换货", "保质期", "售后", "保修"]
    if any(keyword in user_input for keyword in after_sales_keywords):
        return "我们支持7天无理由退换货，商品保质期以包装为准，有购物需求可以继续问我～"
    
    try:
        # 仅保留用户输入，流程规则已在 AGENT_PROMPT 中定义，无需重复注入
        final_input = user_input
        
        # 调用模型生成回复（无冗余格式）
        base_response = conversation_chain.predict(input=final_input)
    
    except Exception as e:
        # 仅保留错误提示，不打印冗余日志
        return f"暂时无法处理你的请求，请稍后再试～"
    
    # 3. 工具调用逻辑（保留，仅在“推荐/对比”时触发）
    tool_keywords = ["推荐", "对比", "哪个好", "选哪个"]
    if any(keyword in user_input.lower() for keyword in tool_keywords):
        product_response = search_products(user_input)
        product_ids = product_response.get("product_ids", [])
        coupon_response = query_coupons(product_ids)
        # 组合回复（保持简洁，用换行分隔）
        final_response = f"{base_response}\n\n{product_response['content']}\n\n{coupon_response['content']}"
    else:
        # 非工具调用场景（如澄清需求、下单），直接返回模型回复
        final_response = base_response
    
    # 限制回复长度，避免过长
    return final_response[:250] if len(final_response) > 250 else final_response

# 测试入口
if __name__ == "__main__":
    print("="*50)
    print("智能导购小智已上线（输入「退出」结束对话）")
    print("="*50)
    while True:
        try:
            user_input = input("你：")
            if user_input.strip() == "退出":
                print("小智：再见啦～有购物需求随时找我！")
                break
            if not user_input.strip():
                print("小智：你还没说想买什么哦～")
                continue
            # 处理用户输入
            response = handle_user_input(user_input)
            print(f"小智：{response}")
        except KeyboardInterrupt:
            print("\n小智：对话已结束，再见～")
            break
        except Exception as e:
            print(f"小智：出错了 - {str(e)}")