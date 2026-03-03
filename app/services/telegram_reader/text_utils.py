"""Text utilities: link filtering for digest content."""

import re


def filter_links(block: str) -> str:
    """
    Remove all links from text: markdown [text](url) and bare URLs (http/https/www).
    Keeps only the link text for markdown links; removes bare URLs and normalizes spaces.
    """
    # Markdown links: keep only text inside [], remove (url)
    block = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", block)
    # Bare URLs (http, https, www)
    block = re.sub(r"https?://\S+|www\.\S+", "", block)
    # Collapse multiple spaces and strip
    block = re.sub(r"  +", " ", block).strip()
    return block

def replace_question_marks_to_retorical_questions(block: str) -> str:
    """
    Replace question marks to retorical questions.
    """
    return block.replace("?", "!?")
