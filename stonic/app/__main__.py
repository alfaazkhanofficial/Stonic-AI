import argparse
import os
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("STONIC_PORT", "8765")))
    parser.add_argument("--host", type=str, default=os.environ.get("STONIC_HOST", "127.0.0.1"))
    args, _ = parser.parse_known_args()

    uvicorn.run(
        "stonic.app.api:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        access_log=False,
        log_level="info"
    )