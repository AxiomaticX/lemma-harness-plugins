"""Failures worded for the agent: each says what happened and what to do next."""


class LemmaError(Exception):
    """A Lemma call failed; the message is safe to show as is."""


class NotLoggedInError(LemmaError):
    pass


class BusyError(LemmaError):
    def __init__(self) -> None:
        super().__init__(
            "Lemma is still working on this conversation. Wait for that run to finish, "
            "or start a new conversation."
        )


class UsageLimitError(LemmaError):
    def __init__(self) -> None:
        super().__init__(
            "This Lemma account has used all of its plan's tokens. The user can see their "
            "usage and plan in Lemma."
        )


class NotFoundError(LemmaError):
    pass
