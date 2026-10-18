import os

# 测试环境绝不使用真实密钥：优先注入占位值。
# 实际环境变量 > .env 文件，故此处设置可覆盖 backend/.env 中的真实 key。
os.environ["DEEPSEEK_API_KEY"] = "test-key-not-real"
os.environ["APP_ENV"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"
