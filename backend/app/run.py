import os

import uvicorn


def main() -> None:
    # 云平台会注入 PORT；本地直接运行时仍使用 7860。
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
