"""自动测试禁止继承外发追踪设置，不加载真实凭据。"""

import os

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
