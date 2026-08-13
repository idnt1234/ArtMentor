import os


# 测试必须使用离线演示提供者，避免消耗真实 API 配额。
os.environ["AI_PROVIDER"] = "demo"
os.environ["GPTSAPI_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["ALLOW_DEMO_FALLBACK"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./data/artmentor-test.sqlite3"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = "./data/uploads/tests"
os.environ["POSE_FEATURE_ENABLED"] = "true"
os.environ["POSE_PROVIDER"] = "demo"
