import os
import random

# FastMCP no longer accepts a ``debug`` kwarg; debug mode is read from the
# environment when fastmcp is imported.
os.environ.setdefault("FASTMCP_DEBUG", "true")

from fastmcp import FastMCP  # noqa: E402

# Initialize MCP server
mcp = FastMCP("Company Simple MCP Server")


@mcp.tool
def rand_num(a: int, b: int) -> int:
    """Generate a random number between a and b."""
    num = random.randint(a, b)
    print(num)
    return num

if __name__ == "__main__":
    print("Starting simple MCP server...")
    print("Run with (from backend/): uv run fastmcp run ../workspace/examples/mcp_server.py --transport 'streamable-http' --port 8001")
    # mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
    mcp.run()
