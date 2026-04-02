"""
Railway entrypoint — reads PORT from environment and starts uvicorn.
Railway injects PORT as an environment variable but doesn't expand $PORT
in shell commands set via the API. This script reads it via os.environ.
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=2,
    )
