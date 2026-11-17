from typing import Optional, TypedDict


class ChatState(TypedDict, total=False):
    customer_id: int
    question: str
    history: list
    standalone: str
    intent: str
    todo: list
    evidence: list
    action_result: Optional[dict]
    pending_action: Optional[dict]
    answer: str
    sources: list
    attempts: int
    feedback: str
    verified: Optional[bool]
    trace: list
    stream: bool
