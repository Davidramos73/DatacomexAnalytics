from chatkit.history import clean_history, MAX_HISTORY_TURNS


def test_drops_non_user_assistant_and_empty():
    turns = [{"role": "system", "content": "x"},
             {"role": "user", "content": " "},
             {"role": "user", "content": "hi"},
             {"role": "assistant", "content": "yo"}]
    assert clean_history(turns) == [{"role": "user", "content": "hi"},
                                    {"role": "assistant", "content": "yo"}]


def test_caps_to_max_turns():
    turns = [{"role": "user", "content": f"m{i}"} if i % 2 == 0
             else {"role": "assistant", "content": f"a{i}"} for i in range(20)]
    assert len(clean_history(turns)) <= MAX_HISTORY_TURNS
