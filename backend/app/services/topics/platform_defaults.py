"""Starting platform playbooks (spec §22). Copied into `platform_rules` per
organization the first time they're needed; admins edit them from there."""

from typing import TypedDict

from app.models.enums import Platform


class RuleDefaults(TypedDict):
    post_types: list[str]
    objectives: list[str]
    affinity_keywords: list[str]
    tone: str
    guidance: str
    max_length: int
    hashtag_limit: int


DEFAULT_RULES: dict[Platform, RuleDefaults] = {
    Platform.LINKEDIN: {
        "post_types": [
            "Thought leadership",
            "Educational",
            "Industry insight",
            "Case-study style",
            "Carousel",
            "Question",
        ],
        "objectives": [
            "Thought leadership",
            "Education",
            "Lead generation",
            "Brand awareness",
            "Recruiting",
        ],
        "affinity_keywords": [
            "b2b",
            "business",
            "decision makers",
            "executives",
            "leaders",
            "leadership",
            "founders",
            "professionals",
            "enterprise",
            "managers",
            "cto",
            "cfo",
            "hr",
            "recruiting",
            "hiring",
            "saas",
            "industry",
            "thought leadership",
            "lead generation",
        ],
        "tone": "Professional and insightful",
        "guidance": (
            "Lead with a clear point of view in the first two lines. Use short paragraphs and "
            "concrete takeaways. Prefer real expertise over hype."
        ),
        "max_length": 3000,
        "hashtag_limit": 5,
    },
    Platform.X: {
        "post_types": ["Short insight", "Thread", "Question", "Data point", "Discussion"],
        "objectives": ["Engagement", "Thought leadership", "Brand awareness", "Community"],
        "affinity_keywords": [
            "developers",
            "engineers",
            "tech",
            "technology",
            "startups",
            "news",
            "breaking",
            "real-time",
            "community",
            "open source",
            "ai",
            "crypto",
            "engagement",
        ],
        "tone": "Sharp and conversational",
        "guidance": (
            "One idea per post. Make the first line work on its own. Threads: number the "
            "posts and end with a recap."
        ),
        "max_length": 280,
        "hashtag_limit": 2,
    },
    Platform.INSTAGRAM: {
        "post_types": [
            "Carousel",
            "Single visual",
            "Reel concept",
            "Infographic",
            "Educational graphic",
        ],
        "objectives": ["Brand awareness", "Education", "Engagement", "Community"],
        "affinity_keywords": [
            "consumers",
            "customers",
            "lifestyle",
            "design",
            "visual",
            "creative",
            "fashion",
            "food",
            "travel",
            "fitness",
            "wellness",
            "students",
            "young",
            "brand awareness",
        ],
        "tone": "Warm and visual",
        "guidance": (
            "The visual carries the message: a strong headline on the first slide or frame, "
            "and a caption that adds context. Keep text on images short."
        ),
        "max_length": 2200,
        "hashtag_limit": 15,
    },
    Platform.FACEBOOK: {
        "post_types": ["Educational", "Community", "Business insight", "Visual", "Discussion"],
        "objectives": ["Community", "Engagement", "Education", "Brand awareness"],
        "affinity_keywords": [
            "community",
            "local",
            "families",
            "parents",
            "small business",
            "smb",
            "customers",
            "members",
            "nonprofit",
            "events",
            "community building",
        ],
        "tone": "Friendly and approachable",
        "guidance": (
            "Write for a broad audience. Invite comments with a genuine question and keep "
            "jargon to a minimum."
        ),
        "max_length": 2000,
        "hashtag_limit": 3,
    },
    Platform.BLOG: {
        "post_types": [
            "How-to guide",
            "Explainer",
            "Thought leadership article",
            "Industry analysis",
            "Listicle",
            "Case-study style",
        ],
        "objectives": [
            "Organic search traffic",
            "Education",
            "Thought leadership",
            "Lead generation",
            "Brand awareness",
        ],
        "affinity_keywords": [
            "seo",
            "search",
            "organic traffic",
            "website",
            "content marketing",
            "long-form",
            "in-depth",
            "guide",
            "how to",
            "education",
            "evergreen",
            "research",
            "buyers",
            "decision makers",
            "b2b",
            "thought leadership",
            "lead generation",
        ],
        "tone": "Informative and authoritative",
        "guidance": (
            "Answer the reader's search intent early. Use an SEO-friendly title, a short "
            "introduction, H2 sections with H3 subheadings where useful, practical examples, "
            "a conclusion and one clear call to action. Aim for 1,200-2,000 words, keep "
            "paragraphs short and use the primary keyword naturally, never stuffed."
        ),
        "max_length": 20000,
        "hashtag_limit": 0,
    },
}
