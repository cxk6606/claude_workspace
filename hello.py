"""小程序：统计一段文本里出现次数最多的词。"""
from collections import Counter
import platform
import re


def top_words(text: str, n: int = 3) -> list[tuple[str, int]]:
    words = re.findall(r"[a-z']+", text.lower())
    return Counter(words).most_common(n)


if __name__ == "__main__":
    text = "the quick brown fox jumps over the lazy dog and the dog barks back"
    print(f"运行环境: {platform.system()} / Python {platform.python_version()}")
    for word, count in top_words(text):
        print(f"{word}: {count}")
