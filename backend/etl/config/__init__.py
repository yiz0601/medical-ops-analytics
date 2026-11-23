"""ETL 配置层：路径、数据库连接、数据源注册、表结构与字典。

模块清单：
    settings.py       全局路径与数据库连接（含无 MySQL 环境的 SQLite 冒烟回退）
    dicts.py          维度字典（科室、费别归类、病种与模拟 DRG 分组、检验判定）
    ods_schema.py     ODS 贴源层 6 张表的 SQLAlchemy 表结构
    dwd_schema.py     DWD 明细层 6 张表的 SQLAlchemy 表结构
    source_config.py  数据源注册、连接测试、数据源清单
"""
