from klientenverwaltung.ui.dialogs import summarize_names


def test_summarize_names_lists_a_few_and_counts_the_rest() -> None:
    names = [f"datei{index}.jpg" for index in range(1, 18)]

    summary = summarize_names(names)

    assert summary.startswith("datei1.jpg, datei2.jpg")
    assert summary.endswith("und 12 weitere")
    assert "datei6.jpg" not in summary


def test_summarize_names_keeps_a_short_list_complete() -> None:
    assert summarize_names(["a.jpg", "b.mp3"]) == "a.jpg, b.mp3"
