import re


def _is_adjacent_transposition(left, right):
    if left == right:
        return True
    if len(left) != len(right) or len(left) < 5:
        return False
    differences = [
        index for index, (left_char, right_char) in enumerate(zip(left, right))
        if left_char != right_char
    ]
    if len(differences) != 2 or differences[1] != differences[0] + 1:
        return False
    first, second = differences
    return left[first] == right[second] and left[second] == right[first]


def _token_matches(token, folded_text, words):
    if token in folded_text:
        return True
    if len(token) < 5:
        return False

    for start in range(len(words)):
        joined = ""
        for word in words[start : start + 3]:
            joined += word
            if len(joined) > len(token):
                break
            if joined == token or _is_adjacent_transposition(token, joined):
                return True
    return False


def folded_tokens_match(tokens, folded_text):
    """Match exact terms plus joined-name terms with one adjacent transposition."""
    normalized_tokens = [str(token or "").strip() for token in tokens if str(token or "").strip()]
    if not normalized_tokens:
        return True
    words = re.findall(r"\w+", folded_text or "")
    return all(_token_matches(token, folded_text or "", words) for token in normalized_tokens)
