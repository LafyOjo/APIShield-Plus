from app.core.rate_limit import is_banned, register_abuse_attempt, reset_state


def test_register_abuse_attempt_bans_subject():
    reset_state()
    subject = "iphash:test123"
    assert register_abuse_attempt(subject, threshold=2, ban_seconds=60, window_seconds=60) is None
    ban_for = register_abuse_attempt(subject, threshold=2, ban_seconds=60, window_seconds=60)
    assert ban_for is not None
    banned, _retry = is_banned(subject)
    assert banned is True
