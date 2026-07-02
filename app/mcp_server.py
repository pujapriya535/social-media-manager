from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SocialMediaMCP")

@mcp.tool()
def get_trending_hashtags(topic: str) -> list[str]:
    """Returns trending hashtags for a given topic."""
    return [f"#{topic.replace(' ', '')}", f"#{topic}Tips", "#TrendingNow"]

@mcp.tool()
def get_competitor_metrics(competitor_name: str) -> str:
    """Returns simulated engagement metrics for a competitor."""
    return f"Competitor {competitor_name} has a 4.5% engagement rate and 10k average impressions."

@mcp.tool()
def schedule_post(content: str, platform: str, time: str) -> str:
    """Simulates scheduling a post on a given platform."""
    return f"Successfully scheduled post on {platform} at {time}. Content preview: {content[:30]}..."

if __name__ == "__main__":
    mcp.run(transport='stdio')
