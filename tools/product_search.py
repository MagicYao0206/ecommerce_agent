from neo4j import GraphDatabase
import re
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

def search_products_from_kg(user_input):
    """从Neo4j知识图谱检索商品"""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    except Exception as e:
        return f"数据库连接失败: {str(e)}"
    
    # 解析用户输入
    # 提取价格
    price_match = re.search(r'(\d+)元', user_input)
    max_price = int(price_match.group(1)) if price_match else 1000
    
    # 提取肤质
    skin_type = ""
    if "油性" in user_input or "油皮" in user_input:
        skin_type = "油性"
    elif "干性" in user_input or "干皮" in user_input:
        skin_type = "干性"
    elif "混合" in user_input:
        skin_type = "混合性"
    elif "敏感" in user_input:
        skin_type = "敏感性"
    
    # 提取类别
    category = ""
    if "美妆" in user_input:
        category = "美妆"
    elif "服装" in user_input:
        category = "服装"
    elif "家电" in user_input:
        category = "家电"
    
    # 构建Cypher查询
    cypher_parts = ["MATCH (p:Product)"]
    where_clauses = ["p.price <= $max_price"]
    params = {"max_price": max_price}
    
    if skin_type:
        cypher_parts.append("-[:SUITABLE_FOR]->(s:SkinType)")
        where_clauses.append("s.name CONTAINS $skin_type")
        params["skin_type"] = skin_type
    
    if category:
        cypher_parts.append("-[:BELONGS_TO]->(c:Category)")
        where_clauses.append("c.name = $category")
        params["category"] = category
    
    cypher_query = " ".join(cypher_parts) + "\nWHERE " + " AND ".join(where_clauses)
    cypher_query += "\nRETURN p.product_id, p.name, p.price ORDER BY p.price LIMIT 3"
    
    # 执行查询
    try:
        with driver.session() as session:
            result = session.run(cypher_query, params)
            products = [{"id": r["p.product_id"], "name": r["p.name"], "price": r["p.price"]} for r in result]
    except Exception as e:
        return f"查询执行失败: {str(e)}"
    finally:
        driver.close()
    
    # 生成回复
    if not products:
        return "没有找到符合条件的商品，可以尝试调整筛选条件哦~"
        
    content = "为你推荐以下商品：\n"
    for idx, p in enumerate(products):
        content += f"{idx+1}. {p['name']}（¥{p['price']}）\n"
    
    return content