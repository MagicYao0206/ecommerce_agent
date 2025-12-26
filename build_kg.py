from neo4j import GraphDatabase
import pandas as pd
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, PRODUCT_DATA_PATH

# 1. 连接Neo4j
driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# 2. 加载并清洗商品数据
product_df = pd.read_csv(PRODUCT_DATA_PATH)
# 价格转换为数值类型
product_df['price'] = pd.to_numeric(product_df['price'], errors='coerce')
# 填充空值
product_df['suitable_for'] = product_df['suitable_for'].fillna('通用肤质')
# 移除关键字段缺失的行
product_df = product_df.dropna(subset=['product_id', 'name', 'category', 'price'])

# 3. 创建节点和关系
def create_product_kg(tx, product_id, name, category, price, suitable_for):
    # 创建「商品」节点
    tx.run(
        "CREATE (p:Product {product_id: $product_id, name: $name, price: $price})",
        product_id=product_id, name=name, price=price
    )
    # 创建「类目」节点
    tx.run(
        "MERGE (c:Category {name: $category})",  # MERGE避免重复创建
        category=category
    )
    # 创建「商品-属于-类目」关系
    tx.run(
        "MATCH (p:Product {product_id: $product_id}), (c:Category {name: $category}) "
        "CREATE (p)-[:BELONGS_TO]->(c)",
        product_id=product_id, category=category
    )
    # 创建「肤质」节点
    tx.run(
        "MERGE (s:SkinType {name: $suitable_for})",
        suitable_for=suitable_for
    )
    # 创建「商品-适合-肤质」关系
    tx.run(
        "MATCH (p:Product {product_id: $product_id}), (s:SkinType {name: $suitable_for}) "
        "CREATE (p)-[:SUITABLE_FOR]->(s)",
        product_id=product_id, suitable_for=suitable_for
    )

# 4. 批量导入数据（使用事务批量提交）
try:
    with driver.session() as session:
        tx = session.begin_transaction()
        for idx, row in product_df.iterrows():
            create_product_kg(
                tx,
                product_id=row["product_id"],
                name=row["name"],
                category=row["category"],
                price=row["price"],
                suitable_for=row["suitable_for"]
            )
            # 每100条提交一次
            if idx % 100 == 0 and idx > 0:
                tx.commit()
                tx = session.begin_transaction()
        tx.commit()  # 提交剩余数据
    print("商品知识图谱构建完成！")
except Exception as e:
    print(f"构建知识图谱时出错: {str(e)}")
finally:
    driver.close()