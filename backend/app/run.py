import os

import uvicorn


def main() -> None:
    # Hugging Face Docker Spaces 默认监听 7860，也兼容平台注入的 PORT。
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
