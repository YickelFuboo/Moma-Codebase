import os
from typing import Union, List
import tiktoken


encoder = tiktoken.get_encoding("cl100k_base")

def num_tokens_from_string( texts: Union[str, List[str]]) -> int:
    """Returns the number of tokens in a text string."""
    try:
        if isinstance(texts, str):
            return len(encoder.encode(texts))
        
        return sum(len(encoder.encode(text)) for text in texts)
    except Exception:
        return 0

def truncate(string: str, max_len: int) -> str:
    """turns truncated text if the length of text exceed max_lenRe."""
    return encoder.decode(encoder.encode(string)[:max_len])
