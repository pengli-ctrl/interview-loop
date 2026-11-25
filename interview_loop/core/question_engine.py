from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.82


def questions_too_similar(new_question: str, previous_question: str) -> bool:
    def normalize(value: str) -> str:
        return "".join(char.lower() for char in value if char.isalnum())

    left = normalize(new_question)
    right = normalize(previous_question)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= SIMILARITY_THRESHOLD
