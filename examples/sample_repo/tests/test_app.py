def test_compute():
    from app import compute
    answer = compute()
    assert answer == 42, f"expected 42, got {answer}"

